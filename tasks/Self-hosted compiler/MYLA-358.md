---
id: MYLA-358
title: "Native: a literal left of an unsigned operator was lowered with the literal's first type"
type: bug
status: done
priority: high
labels: [checker, codegen, integers, miscompile]
---
Found by the `std.int` lane ([[MYLA-322]]): a silently wrong result, natively only. With `m: uint64 = 2^64 - 1`, `10 / m` printed `18446744073709551606` and `10 % m` printed `0`, where the interpreter prints `0` and `10`. Any unsuffixed literal on the left of an operator whose right operand has another integer type was affected. The right operand's type decides the operation's type (D4), and the literal is typed again to match, but the lowering read the literal's first type, `int32`, and divided as signed.

## Cause

`unify` in [[selfhost/checker.my]] types a flexible literal again (`infer_int_lit` with the other operand's type), but only `infer_node` recorded a node's type, so the lowering's `cg.type_of` still saw the literal's first type. The other places that type a literal again (a generic call's arguments, match arms, list elements) had the same gap.

- [x] `infer_int_lit` and `infer_float_lit` record the type they give
- [x] `test_compiler_parity`'s `literal_left_of_unsigned_division`: `/`, `%`, `+` and `<` with an unsigned right operand of 8, 32 and 64 bits, interpreted and native

A related limit is left as it is: a literal on the left that doesn't fit `int32` (`4000000001 - n` with `n: uint32`) is rejected before the right operand is typed. It is an error, not a wrong result. Suffixing the literal works.

## Done (2026-11-07)

- `infer_int_lit` and `infer_float_lit` record the type they give, so the last typing of a literal is the one the lowering reads.
- Test first: `literal_left_of_unsigned_division` printed `18446744073709551606` and `0` natively for `10 / m` and `10 % m`. Now it gives the interpreter's `0 10 0 100 0 4000000005 1 true`.
- `scripts/bootstrap.sh`: byte-identical fixed point. The checker's own cases (556/556), `test_selfhost_checker`, `test_error_corpus` and `test_std_modules` pass.

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]].
