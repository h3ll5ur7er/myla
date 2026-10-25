---
id: MYLA-7
title: "Literal patterns outside the scrutinee's range match differently natively"
type: bug
status: backlog
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

- [ ] Literal patterns are range-checked as signed values against the scrutinee type (a pattern `-1` on `uint8` or `128` on `int8` is a type error), or both backends wrap the same way
- [ ] Error-corpus entry or parity test
