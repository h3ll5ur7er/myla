---
id: MYLA-272
title: "D119 and what the backends do: one internal convention, or each platform's C convention"
type: chore
status: backlog
priority: medium
labels: [ir, backend, design, ffi]
---
Found by [[Project/Reflection-2026-11]]. D119 says Myla's own functions use each target's C calling convention: System V, AAPCS64, Win64, wasm's. The closure environment goes in the platform's static-chain register, or as "an extra first parameter on wasm". What was built differs:

- **wasm:** every signature is `(i64, …) -> i64`, floats included. The environment goes through a memory word, `myla_env`, which also stands in the way of threads on wasm.
- **aarch64:** floats travel in x registers, not d registers, and an aggregate result's address is the first word, not x8.
- **x86-64:** floats are still in general-purpose registers (D119 put the vector registers off to the FFI), and the stack isn't kept 16-byte aligned.
- **The checker:** `become`'s limit is a fixed six words (`checker.my`), x86-64's count. AAPCS64 has eight and Win64 four.

The choice for the owner:
- [ ] Either Myla keeps one internal convention per target, with the platform's C convention only at C boundaries ([[MYLA-166]], [[MYLA-241]]); or the backends move to D119 as written, and `myla_env` becomes a parameter on wasm. Recorded as a decision changing or confirming D119.

Then:
- [x] The backends and the checker's rule as decided

Also track [[MYLA-250]]'s follow-ups:
- [ ] A parameter kept in the register it came in
- [ ] A generic `become` counting a type parameter as one word, which could end in an internal error (a latent bug, [[MYLA-250]])

## Decided (2026-11-05)

The owner chose the recommendations:
- **D130:** Myla's own convention per target, with each platform's C convention only at C boundaries. This changes D119.
- **D131:** `become` passes six words freely on every target.

- [x] The decision: D130 and D131

Then:
- [x] wasm32: the closure environment as a parameter instead of the memory word `myla_env` (D130)
- [x] [[Architecture/Native-backend]] and [[Architecture/IR]] describe each target's internal convention as the contract; D119's wording on those pages follows D130

## Done (2026-11-05)

- The backends keep their conventions (D130) and the checker its six words (D131), so "the backends and the checker's rule as decided" needed no change beyond wasm's environment.
- wasm32: a function value's environment is the last argument of its `call_indirect`; lambdas' bodies, async lambdas' `__new`, partial applications' functions, the `__fnval` adapters and `__compose_call` take it as their last parameter, and the memory word `myla_env` is gone. [[tests/burn/test_wasm.py]] `test_a_closure_gets_its_environment_as_a_parameter` runs lambdas, partials, compositions, plain functions, a `become` through a function value and async lambdas under `task.all` against x86-64, and checks that the assembly never names `myla_env`.
- [[Architecture/Native-backend]] and [[Architecture/IR]] name each target's own convention as the contract.

The two follow-ups of [[MYLA-250]] stay open (performance and a latent bug, not the decision).
