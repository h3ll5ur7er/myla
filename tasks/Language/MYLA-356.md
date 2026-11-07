---
id: MYLA-356
title: "A lambda's parameter types from a generic call whose result type is still open"
type: bug
status: review
priority: high
labels: [checker, generics, inference, lambdas]
---
Found by the `std.option` lane ([[MYLA-324]]). `o.map((x) => x * 2)` on an `Option<int>` fails with "cannot infer the type of lambda parameter 'x'", although `T` is known from the receiver. The same happens for a free `apply<T, U>(x: T, f: (T) -> U)` called as `apply(3, (x) => x * 2)`. `same<T>(x: T, f: (T) -> T)` infers, because its parameter's type has no open type parameter once `T` is bound. Every `map`, `and_then`, `flat_map` and `fold` of the new modules ([[MYLA-323]], [[MYLA-324]]) takes a function whose result is a type parameter of its own, so without the fix each lambda needs its parameter type written.

## Cause

`infer_generic_call` and `infer_generic_method` in [[selfhost/checker.my]] give an argument no expected type at all while its parameter's type still contains a type parameter (`(int) -> U` here). The lambda then has no parameter types to take.

- [x] A lambda argument gets the parameter's function type with its parameter types (when they are all known) and its result left open, so the lambda infers its result and that binds the rest
- [x] `test_compiler_parity`'s `lambda_parameters_from_known_arguments`: a free function and a generic method, expression and block bodies, a chain, in both runners
- [x] [[Language/Generics]]'s inference rules say so

## Done (2026-11-07)

- `lambda_param_hint` in [[selfhost/checker.my]]: for a lambda argument whose parameter's type still names a type parameter, the hint is the function type with its parameter types, when none of them names one, and no result. The lambda then infers its result from its body (`infer_lambda` already does this when no result is expected), and unifying it binds the rest. Other arguments still get no hint. It is used by `infer_generic_call` and `infer_generic_method`, and has three cases of its own.
- Test first: `lambda_parameters_from_known_arguments` in `test_compiler_parity` stopped with "cannot infer the type of lambda parameter 'x'" before. After the fix it prints `6 3 5 true 3`, interpreted and natively. It covers a free function, a generic method, an expression body, a block body, and a chain of two `map`s.
- `scripts/bootstrap.sh`: byte-identical fixed point (9,865,260 bytes). `test_error_corpus`, `test_selfhost_checker` and the checker's own cases pass, except `variant_leaves_params` #1 and #3, which fail without this change too.
