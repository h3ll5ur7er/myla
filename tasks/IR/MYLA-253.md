---
id: MYLA-253
title: "`become` passing a function-value parameter on to a function fails to lower"
type: bug
status: review
priority: low
labels: [ir, lowering, tail-calls]
---
Found while testing [[MYLA-250]]. The checker accepts a `become` that passes a function-value parameter on to a function ("a function or method takes … a function value by its address", `check_become` in [[selfhost/checker.my]]), but the lowering refuses it, so the compiler stops with an internal error instead of compiling the program or reporting a type error. The interpreter runs it.

```myla
fun relay(n: int, f: (int) -> int, a: int) -> int {
    if n == 0 {
        return f(a)
    }
    become relay(n - 1, f, a + 1)
}
```

`build/myla build` ends with `internal error: relay can't be lowered to the IR: a 'become' passing a value to a borrowed parameter` ([[selfhost/lower.my]], the call's arguments: `tail && !owned && !byval && … (is_aggregate || owns_heap)`). It did before MYLA-250 too.

A function value parameter lives in the caller's storage (its address is the argument word), so passing it on in place needs nothing from the frame; the lowering should accept a borrowed aggregate argument that is (a part of) a parameter, as the checker does, or the checker should reject what the lowering can't do.

- [x] A test: the program above, natively against the interpreter, with a million steps
- [x] The lowering and the checker agree

Still reproduces on 2026-11-04 on x86-64, aarch64 and wasm32: the failure is in the lowering, which every target shares.

## Fixed (2026-11-05)

The lowering now lets a `become` pass on, borrowed, a parameter that the caller holds, or a field or tuple element of one (`caller_holds`: its slot came as an argument word and the function doesn't own it), which is what the checker accepts; the frame being left keeps nothing of it. [[tests/burn/test_register_args.py]] `test_become_passes_its_parameters_on` (a function value, a string and a struct passed on a million times, a field of a parameter), and the same program on aarch64 and wasm32 (`PROGRAMS["become_params"]`).
