---
id: MYLA-283
title: "aarch64, wasm32: calls in tail position jump"
type: improvement
status: review
priority: low
labels: [platforms, aarch64, wasm, codegen, performance]
---
On x86-64 a direct call whose result is returned at once jumps instead of calling ([[MYLA-126]], [[MYLA-130]]), so a plain recursion through tail calls runs in constant stack. That's an optimisation, not a guarantee: D87 guarantees `become`, which every target keeps. On aarch64 and wasm32 a plain call in tail position takes a frame, so the programs of `test_calls_in_tail_position_reuse_the_frame` and `test_tail_calls_hand_over_owned_arguments` (recursing millions deep) overflow the stack there, and `tests/burn/_targets.py` excuses both tests.

aarch64 can do what x86-64 does (the frame goes, then `b`); wasm32 has `return_call` (the tail-call proposal, which the backend already uses for `become`).

- [x] aarch64
- [x] wasm32
- [x] The two exceptions out of `_targets.py`

## Evidence (2026-11-06)

- Both backends now run `hoist_tail_drops` before `expand_ownership`, as x86-64 does, and take a call that `tail_call_at` finds (its result returned at once, the drops after it moved before it, no argument an address in the frame: `drops_after_free`, `passes_frame_address`, shared with x86-64) in place of the function: aarch64 by `a64_tail_call` when its arguments fit the eight argument registers, wasm32 by `return_call` (every function's result is one i64, so any call fits). Not in a frame function (an async one's suspensions are its tail calls already).
- Test first: `test_aarch64`'s `tail_calls_jump` (a million-deep plain recursion, mutual recursion, a string built by a tail call, a function without a result ending in a call whose result it drops), which `test_wasm` runs too, overflowed the stack on both targets before; now both print what x86-64 does.
- `scripts/test-target.py`: 15 of 15 suites on both targets without the two exceptions (`test_calls_in_tail_position_reuse_the_frame`, `test_tail_calls_hand_over_owned_arguments`).
