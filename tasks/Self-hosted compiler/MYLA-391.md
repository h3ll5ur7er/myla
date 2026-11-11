---
id: MYLA-391
title: "Interpreter: a method on a temporary whose type is a type parameter"
type: bug
status: review
priority: medium
labels: [interpreter, generics, parity]
---
Found by the MYLA-384 lane. Interpreted, `x.scaled(2).area()` with `x: T` (`T: Shape`) printed `ERR: VUnit` and the program exited 0; natively it printed `36`. The interpreter erases types, so `recv_key` keys a method call by its receiver's type, or for a type parameter by the receiver's value read again without effects (`eval_pure`: a name or a field of one). A call has neither, and gave `VUnit`.

- [x] `eval_method_call` ([[selfhost/interp.my]]): when `key_by_type` finds no key without evaluating (a type parameter's temporary), the receiver is evaluated once and the method keyed by its value
- [x] A parity program

## Evidence

- Test first: `method_on_a_generic_temporary` in `test_compiler_parity` (`x.scaled(2).area()` in a generic function, and `twice(…).scaled(5).area()` on the result of a generic call) failed interpreted (`ERR: VUnit`); now both runners print `36 100`.
- `key_by_type`'s case; `build/myla test selfhost/interp.my`; `test_compiler_parity`; `scripts/bootstrap.sh`: byte-identical fixed point.

## Review 2026-11-09

Not ready ([[Project/Review-2026-11-09]]): `mk(x).inner.step()` prints `ERR: VUnit` and exits 0; a `var self` method on `xs[i]` or `m[k]` loses its mutation silently (H6, M4). The fix is in [[MYLA-414]].

- [x] The review's blocker, fixed with [[MYLA-414]]

The receiver is keyed by its checked type, a type parameter's from its frame, else evaluated once as a place, and a method nothing defines is a runtime error: `mk(x).inner.step()` gives `3`, a `var self` method on `xs[i]` and `m[k]` changes the element (the parity program `receivers_of_type_parameter_type`); evidence in [[MYLA-414]].
