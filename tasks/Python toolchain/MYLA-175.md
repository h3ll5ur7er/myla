---
id: MYLA-175
title: A positive literal one past the signed maximum is accepted and wraps
type: bug
status: todo
priority: medium
labels: [checker, literals]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). `let c = 2147483648; print(c)` prints `-2147483648`, and `let d: int8 = 128` prints `-128`, in the interpreter and natively alike, so the parity tests can't see it; `2147483649` is rejected. `int_fits` ([[src/myla/types.py]]) allows the magnitude 2^(w-1) so that `-128i8` works, and `_infer_unary` never tightens the check for a literal that isn't negated. The self-hosted checker has the same hole (it must keep agreeing).

- [ ] A `negated` flag from `_infer_unary` into the literal check, in both checkers
- [ ] Error-corpus files for `2147483648`, `128i8` and `let d: int8 = 128`; `-128i8` and `-2147483648` still accepted
- [ ] `test_literal_too_large` tests the boundary values, not 999
