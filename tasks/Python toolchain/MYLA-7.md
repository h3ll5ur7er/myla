---
id: MYLA-7
title: "Literal patterns outside the scrutinee's range match differently natively"
type: bug
status: done
priority: medium
labels: [checker, native-backend, parity]
---
## Steps to reproduce

```myla
fun main() {
    let b: uint8 = 255
    match b {
        -1 => print("minus one")
        _ => print("other")
    }
    let c: int8 = -128
    match c {
        128 => print("hit")
        _ => print("miss")
    }
}
```

## Actual

The interpreter prints `minus one` and `hit` (it wraps the literal to the type); native prints `other` and `miss`, because `_const_scalar` compares the raw value against the canonical one ([[src/myla/compiler/codegen_x86.py#L5193-L5201]]).

## Cause

The checker accepts both patterns: `-1` types as `uint8` because unary minus takes the expected type, and `int_fits` deliberately lets `128` fit `int8` so that `-128i8` works ([[src/myla/types.py#L284-L293]]).

## Done when

- [x] Literal patterns are range-checked as signed values against the scrutinee type (a pattern `-1` on `uint8` or `128` on `int8` is a type error), or both backends wrap the same way
- [x] Error-corpus entry or parity test

## How

The first option: an integer literal pattern is checked as the value it denotes against the scrutinee type, and one outside its range is a type error, `integer literal -1 does not fit in 'uint8'`, at the pattern. Expressions keep their permissive rule (`let b: uint8 = -1` wraps to 255, since unary minus is arithmetic there), but a pattern has no arithmetic: it could only ever be a pattern that never matches, or one whose meaning depends on the backend.

- Python: `_in_range` next to `int_fits`, used in the `PatLiteral` branch of `_check_pattern` ([[src/myla/types.py]]).
- Self-hosted: `pattern_misfit` / `negated_misfit` in [[selfhost/checker.my]], using the literal's `big` text for values of 2^63 and above. Same message and position.
- A literal whose magnitude is already too big (`-129` on `int8`) keeps the existing literal error (`integer literal 129 does not fit in 'int8'`).

Since every pattern now holds a value of the scrutinee type, the native comparison with the raw value is correct.

## Evidence

- `test_literal_patterns_must_fit_the_scrutinee` ([[tests/unit/test_enums_match.py]]): five rejected and seven accepted patterns at the bounds. Failed before (no error), passes after.
- Six new `TYPE_ERRORS` cases in [[tests/burn/test_selfhost_checker.py]] (including `9223372036854775808` on `int64`, `-9223372036854775808` on `uint64` and the bounds that fit): before, the self-hosted checker said `ok`; after, it matches Python.
- Bootstrap fixed point holds (5,936,708 bytes); unit, integration and burn suites pass.
