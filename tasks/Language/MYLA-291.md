---
id: MYLA-291
title: "A bound `T: Format` can't be formatted"
type: improvement
status: review
priority: low
labels: [checker, traits, generics]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]). D139's `Format` trait is implemented for a struct and used by a format spec, but `fun show<T: Format>(x: T) -> str { return f"<{x}>" }` fails with "cannot render a value of type 'T'": D104 (6) left bounds that admit trait calls for later, so the trait's main use, a generic printer, is closed. `print(x)` also refuses a `Format` type while `print(f"{x}")` takes it.

- [x] Bounds that admit the trait's methods and the operations the trait enables (`Format` in a hole, `Ord` in comparisons), checked at the call site as operators are
- [ ] `print(x)` of a `Format` value, or the page saying why not

## Evidence

- `bound_method_call` in [[selfhost/checker.my]]: on a receiver of type `T`, the methods of the user traits (and `Format`) among `T`'s bounds, `Self` read as `T`, a `var self` method needing a mutable place as for any type; an operator trait's methods stay its operators (`x.add(y)` has no method form on a primitive: "none of its bounds ('Add') declares one (an operator trait gives its operators)"). `infer_format` takes a `T: Format` in a hole. The bound itself is checked at the call site as before (`check_call_bounds`), through generic callers too (`relay` below). Nothing changes in lowering or the interpreter: lowering names the method by the receiver's type under the instantiation's substitution, as for an operator on a bounded `T`, and the interpreter by the value.
- `test_a_bound_gives_its_traits_methods` in `tests/burn/test_format_specs.py` (interpreter and native, byte for byte): `f"<{x}> <{x:>6}>"` and `x.format("")` on a `T: Format`, a list of them, `Self` in a trait method's parameter, a user trait on `int` and on a struct, `T: Area + Format` passed on to other generic functions. `test_errors` gains the unmet bound, no bound, no bound in a hole and the operator trait. The page block in [[Language/Methods-and-traits#bounds]] runs in `test_doc_blocks`.
- Left open, for the owner: `print(x)` of a `Format` value. The review lists it among the design notes; it would be three small changes (the checker's `print`, `print` in lowering through `format_call`, the interpreter's through `format_spec_value`). Until then [[Language/Collections-and-strings]] says `print` takes the scalars and `str`, and a struct goes through `print(f"{x}")`.
