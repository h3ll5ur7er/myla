---
id: MYLA-283
title: "aarch64, wasm32: calls in tail position jump"
type: improvement
status: backlog
priority: low
labels: [platforms, aarch64, wasm, codegen, performance]
---
On x86-64 a direct call whose result is returned at once jumps instead of calling ([[MYLA-126]], [[MYLA-130]]), so a plain recursion through tail calls runs in constant stack. That's an optimisation, not a guarantee: D87 guarantees `become`, which every target keeps. On aarch64 and wasm32 a plain call in tail position takes a frame, so the programs of `test_calls_in_tail_position_reuse_the_frame` and `test_tail_calls_hand_over_owned_arguments` (recursing millions deep) overflow the stack there, and `tests/burn/_targets.py` excuses both tests.

aarch64 can do what x86-64 does (the frame goes, then `b`); wasm32 has `return_call` (the tail-call proposal, which the backend already uses for `become`).

- [ ] aarch64
- [ ] wasm32
- [ ] The two exceptions out of `_targets.py`
