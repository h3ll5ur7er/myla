---
id: MYLA-826
title: "The aarch64 and wasm32 tools' checker takes far more stack a level than x86-64's"
type: bug
status: review
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

- [x] Find what makes an aarch64 frame of `infer`, `infer_node`, `infer_call`, `expect_value` three times x86-64's (spilled cells, the frame's layout in [[selfhost/ir_a64.my]])
- [x] Give the wasm32 tools' shadow stack room for `MAX_CHAIN`'s levels, or have the limit follow the target the tools run on
- [x] A test that runs `tests/burn/test_selfhost_parser.py`'s long chains with the aarch64 tools (qemu) and the wasm32 tools

## Evidence

**What made aarch64's frames three times x86-64's.** [[selfhost/ir_a64.my]] gave every temporary a cell of its own and laid every slot one after the other, where x86-64 shares the cells of temporaries never live at once (`alloc_temps`) and the slots of scopes never open at once (`slot_positions`, [[MYLA-183]]). wasm32 shared its temporaries' locals (`wasm_locals`, [[MYLA-543]]) but laid its shadow frame's slots one after the other too. Now aarch64's temporaries share cells by `wasm_locals` (made `pub`), and both aarch64's and wasm32's slots are laid out by `cell_positions` in [[selfhost/ir_x86.my]] (`slot_positions` with each slot at least a word, as their stores to a slot are a word's; x86-64 calls it as before). Frames of the checker's recursion, `build/stage3 selfhost/main.my lib --target aarch64-linux` before → after (x86-64's): `infer` 432 → 256 (192), `infer_node` 10,144 → 4,560 (4,080), `infer_call` 67,600 → 22,368 (21,440), `expect_value` 1,216 → 656 (544) bytes. x86-64's assembly is the same byte for byte (39 examples compiled by the stage before the change and after). The aarch64 binary of `selfhost/main.my` went from 10,926,304 to 10,852,344 bytes.

**Depth the tools' checker holds** (`build/c/bisect.sh` over `MAX_CHAIN = 1000000` builds of `selfhost/main.my`, `check` of `let t = x && x && …`, `x.abs().abs()…`, `1 |> f |> f …`; 2026-11-18 at `3add216` with this branch):

| tools built for | `&&` | `.abs()` | `\|> f` | `else if` |
| --- | --- | --- | --- | --- |
| x86-64 (120 MiB) | 12,507 | 4,122 | 4,778 | |
| aarch64 before (qemu, 120 MiB) | 4,178 | 1,383 | 1,582 | |
| aarch64 after | 11,198 | 3,893 | 4,507 | |
| wasm32 before (`node tools/wasm/run.mjs`) | 533 (V8's stack) | 239 (shadow) | | |
| wasm32 after | 531 (V8's stack) | 272 (shadow) | 315 (shadow) | 611 (V8's stack) |

`run` overflows at the same depths as `check` on wasm32 (533, 272, 315, 618). With V8's stack raised (`node --stack-size=60000`), the 8 MiB shadow stack held 705 `&&` (about 12 KB a level, as x86-64's frames are).

**wasm32.** The task assumed the shadow stack; V8's own call stack (about 1 MB, Node's default and a browser's) runs out first for `&&` and `else if`, the shadow stack first for calls and `|>`, both near the same depth, and a page can't raise V8's. So the limit follows the target the tools are built for: `MAX_CHAIN_WASM` (256) in the tools built for wasm32 (`chain_limit` in [[selfhost/parser.my]], by `target.host()`), which leaves them twice the room the Linux tools have under 2,048. Nothing changed in `tools/wasm/` or `selfhost/runtime_wasm.my`. See the proposal below.

**Tests.** `test_selfhost_parser`'s long chains are `check_long_chains(tool, limit)`, run natively (2,048), with the aarch64 tools under qemu with Linux's 120 MiB (`test_the_aarch64_tools_hold_a_long_chain`, 2,048: passes, in 29 s) and with the wasm32 tools under Node's own stack (`test_the_wasm32_tools_hold_a_long_chain`, 256: passes, in 20 s). Before, with the wasm32 tools' limit 2,048: 11 of its 23 cases `runtime error: stack overflow`.

**Suites** (the branch with [[MYLA-802]]): `scripts/bootstrap.sh` reaches the fixed point; `scripts/check-seed.sh` passes for the x86-64 seed and, under qemu (`MYLA_ARCH=aarch64 AS=aarch64-linux-gnu-as LD=aarch64-linux-gnu-ld MYLA_RUN=qemu-aarch64`), for the aarch64 seed: its stage 1 with the new backend builds stages 2 and 3 byte for byte alike, so the aarch64 compiler built with shared cells compiles itself as the x86-64 one does; the Windows seed's output (x86-64's) is unchanged. `scripts/test-target.py aarch64-linux`: 39 of 39 suites; `wasm32-wasi`: 39 of 39. `scripts/test.sh fast`; `test_compiler_parity`, `test_selfhost_cases`, `test_error_corpus`, `test_selfhost_checker`, `test_lsp`, `test_std_modules`, `test_overflow`, `test_test_native`, `test_selfhost_parser`, `test_aarch64`, `test_wasm`, `test_operator_traits`, `test_doc_blocks`; `test_windows` and `test_debug_info` under Wine (with `TMPDIR` unset, as this container needs); `scripts/test.sh` (all): 1,859 tests, OK (390 skipped).

## Proposals

Accepted by the owner on 2026-11-19 as D301.

- **The wasm32 tools' chain limit (amends D279).** Built: 256 in the tools built for wasm32 (the playground's), 2,048 elsewhere; a program with a chain of 257 to 2,048 checks with the native tools and is the parse error in the playground's. Alternatives: (a) raise wasm32's shadow stack (`-z stack-size` in [[selfhost/target.my]], for every wasm32 program: about 48 MiB for 2,048 levels with room) and give Node a larger V8 stack in `run.mjs`: the CLI tools under Node would hold 2,048, the playground still not (a page can't raise V8's stack), so it would still need the lower limit; (b) keep 2,048 and accept a `stack overflow` past about 530 levels on wasm32, as before; (c) make the checker's walk cheaper a level ([[MYLA-902]]) so that 2,048 holds on V8's own stack, and drop `MAX_CHAIN_WASM` then.
