---
id: MYLA-365
title: "Interpreter: a method called on a field whose type is a type parameter isn't found"
type: bug
status: review
priority: high
labels: [interpreter, generics, parity]
---
Found by the stream lane ([[MYLA-338]]). In `impl<R: Step> Wrap<R> { fun go(self) -> int { return self.inner.step() } }` the interpreter gave `()` (printed `ERR: VUnit`); native code gave the method's result. `recv_key` falls back to `eval_pure` for a receiver whose checked type has no key (a type parameter), and `eval_pure` handled only a name.

- [x] `eval_pure` follows a field access ([[selfhost/interp.my]])
- [x] `test_compiler_parity`'s `method_on_a_type_parameter_field`, interpreted and native
