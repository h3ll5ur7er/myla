---
id: MYLA-826
title: "The aarch64 and wasm32 tools' checker takes far more stack a level than x86-64's"
type: bug
status: todo
priority: low
labels: [checker, aarch64, wasm, round-7]
---
Found by [[MYLA-793]] while setting the chain limit (M10 of [[Project/Review-2026-11-17]]). The checker walks an expression recursively, so `MAX_CHAIN` in [[selfhost/parser.my]] bounds how deep a chain may go. With the limit raised (a parser built with `MAX_CHAIN = 1000000`) the checker of each build of the tools overflowed at:

| tools built for | `&&` in one expression | method calls `.abs()` | `\|> f` |
| --- | --- | --- | --- |
| x86-64 (120 MiB stack) | 12,625 | 4,144 | 4,781 |
| aarch64 (qemu-aarch64 `-s 125829120`, as Linux gives 120 MiB) | 4,187 | 1,388 | 1,593 |
| wasm32 (`node tools/wasm/run.mjs`) | 534 | 242 | |

So a level costs the aarch64 tools three times the stack it costs the x86-64 tools (the ratio is the same for every form), and the wasm32 tools' stack holds about 530 levels. [[MYLA-793]] lowered `MAX_CHAIN` from 8,192 to 2,048 (weighted: a call 2, a `|>` 3), which leaves both Linux builds twice the room; on wasm32 (the playground's compiler) a chain of 600 `&&` is still `runtime error: stack overflow`, not the parse error.

Reproduction: `python3 -c 'print("fun main() {\n    let x = true\n    let t = x" + " && x" * 600 + "\n    print(t)\n}")' > t.my`, `build/myla build --target wasm32-wasi selfhost/main.my -o myla.wasm`, then `node tools/wasm/run.mjs myla.wasm check t.my`: `runtime error: stack overflow` (`ok` natively).

- [ ] Find what makes an aarch64 frame of `infer`, `infer_node`, `infer_call`, `expect_value` three times x86-64's (spilled cells, the frame's layout in [[selfhost/ir_a64.my]])
- [ ] Give the wasm32 tools' shadow stack room for `MAX_CHAIN`'s levels, or have the limit follow the target the tools run on
- [ ] A test that runs `tests/burn/test_selfhost_parser.py`'s long chains with the aarch64 tools (qemu) and the wasm32 tools
