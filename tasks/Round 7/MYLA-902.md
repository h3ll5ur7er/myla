---
id: MYLA-902
title: "The checker's walk of a chain takes 10 to 30 KB of stack a level (`infer_call`'s frame is 21 KB)"
type: improvement
status: todo
priority: low
labels: [checker, wasm, round-7]
---
Found by [[MYLA-826]]. The checker walks an expression recursively, and each level of a chain is a cycle of five frames: `infer_node` → `infer` → `expect_value` → `expect_type` → `infer_binary` → `infer_node` for `a && b && …` (gdb's backtrace of `build/myla check` on 3,000 `&&`), with `infer_call` in it for a method call. Their frames on x86-64 (`build/stage3 selfhost/main.my lib`, 2026-11-18 at `3add216` with [[MYLA-826]]): `infer_node` 4,080 bytes, `infer_call` 21,440, `expect_value` 544, `infer` 192. So a level costs about 10 KB (120 MiB held 12,507 `&&`) and a method call about 30 KB (4,122 `.abs()`), and on wasm32 the 8 MiB shadow stack holds 273 method calls and V8's own stack (about 1 MB) 532 `&&`: the reason the tools built for wasm32 allow `MAX_CHAIN_WASM` (256) where the others allow D279's 2,048.

Not measured yet: whether most of `infer_node`'s and `infer_call`'s frames are the slots of arms the recursion never passes through (a frame holds the largest of the scopes never open at once, [[Architecture/Native-backend]]). If so, moving the big arms into functions of their own, or making the walk of a left-nested chain a loop, would make a level far cheaper on every target.

Reproduction: `python3 -c 'print("fun main() {\n    let x = -1\n    let t = x" + ".abs()" * 300 + "\n    print(t)\n}")' > t.my`, then with the tools built with `MAX_CHAIN` raised (`selfhost/parser.my`) for wasm32, `node tools/wasm/run.mjs myla.wasm check t.my`: `runtime error: stack overflow` from 273 calls on.

- [ ] Measure which arms make `infer_node`'s and `infer_call`'s frames (`build/stage3 … --emit-ir`, the slots of each scope)
- [ ] A level of `&&`, of a method call and of `|>` costs a fraction of its stack now, on x86-64, aarch64 and wasm32 (the bisection of [[MYLA-826]]'s evidence)
- [ ] With room for 2,048 levels on wasm32 under V8's own stack, `MAX_CHAIN_WASM` goes (D279 holds on every host)
