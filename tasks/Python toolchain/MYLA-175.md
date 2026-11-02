---
id: MYLA-175
title: A positive literal one past the signed maximum is accepted and wraps
type: bug
status: done
priority: medium
labels: [checker, literals]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). `let c = 2147483648; print(c)` prints `-2147483648`, and `let d: int8 = 128` prints `-128`, in the interpreter and natively alike, so the parity tests can't see it; `2147483649` is rejected. `int_fits` ([[src/myla/types.py]]) allows the magnitude 2^(w-1) so that `-128i8` works, and `_infer_unary` never tightens the check for a literal that isn't negated. The self-hosted checker has the same hole (it must keep agreeing).

- [x] A `negated` flag from `_infer_unary` into the literal check, in both checkers
- [x] Error-corpus files for `2147483648`, `128i8` and `let d: int8 = 128`; `-128i8` and `-2147483648` still accepted
- [x] `test_literal_too_large` tests the boundary values, not 999

## Evidence

- Both checkers: a signed literal takes magnitudes up to the maximum, and one more only under a unary minus. `2147483648`, `128i8`, `let d: int8 = 128` and `9223372036854775808i64` are rejected; `-2147483648`, `-128i8`, `-9223372036854775808` still accepted. Error corpus: `type_literal_past_int32_max.my`, `type_literal_past_int8_max_suffix.my`, `type_literal_past_int8_max_annotated.my`; `test_literal_too_large` checks the boundaries both ways; two checker-gate snippets at the int64 boundary.
- Unit 622, integration 2, burn 826 (5 skipped) and the extension's 54 tests pass on commit 12f6e94; the bootstrap reaches its byte-identical fixed point (6,153,392 bytes).
