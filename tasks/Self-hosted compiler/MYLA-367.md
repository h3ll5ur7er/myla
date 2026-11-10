---
id: MYLA-367
title: "Native: an operator or a format hole on a generic struct with a generic trait impl doesn't link"
type: bug
status: todo
priority: medium
labels: [codegen, generics, traits, monomorphization]
---
Found by the collections lane ([[MYLA-330]]). `impl<T> Eq for Box<T>` then `Box { v: 1 } == Box { v: 2 }` gives "undefined reference to 'myla_Box.eq'" on `myla build`; the interpreter prints the answer. `impl<T: Ord> Ord for Rev<T>` with `<` fails the same way. Calling `.eq(...)` or `.cmp(...)` directly links: the operator's lowering (`overloaded_scalar` in [[selfhost/lower.my]]) names the method by the type's key without its type arguments, so no instance is made. This is why `std.heap` has a max flag rather than a `Reverse<T>` wrapper.

- [x] An operator on a generic struct calls the instance of its trait method for the struct's type arguments, on every target
- [x] A parity program: `==` and `<` on a generic struct with generic `Eq` and `Ord` impls

The Format form, found by wave 3's MYLA-342 lane: `impl<T: Format> Format for Box<T>`, then `f"{b}"` or `print(b)`, gave "undefined reference to 'myla_Box.format'" the same way (`user_format`). This is why `Grid` has a `text()` method instead of `Format`.

## What changed

`method_instance` in [[selfhost/lower.my]]: an operator's `eq` or `cmp` (`overloaded_scalar`) and a format hole's `format` (`user_format`) name the method by the type's key. A generic impl's method is generic, so the type arguments are solved from the operands' types, as a call's are (`solve_targs`), its instance is requested and called. `call_owning_as` calls that instance with the generic method's signature.

## Evidence

- Test first: the parity program `operators_of_generic_impls` (`==`, `!=` on `Box<int>`, `Box<str>`, inside a generic `same<T: Eq>`; `<`, `>=` on a `Rev<T: Ord>`; `Format` in f-string holes and `print`) ran interpreted and failed to link natively ("undefined reference to `myla_Box.format'", "`myla_Box.eq'"). After the change all three targets print the same as the interpreter (x86-64, aarch64 under qemu, wasm32 under Node: identical output).
- `test_compiler_parity`: OK (with the new program pinned).
- `scripts/bootstrap.sh`: byte-identical fixed point.
- `build/myla test selfhost/lower.my`: 113/114, the one failure (`Lower.map_lookup #1: expected 2, got 1`) the same on the unchanged source.

Follow-up: `std.heap` could now offer a `Reverse<T>` wrapper instead of its max flag ([[MYLA-330]]), and `std.grid`'s `Grid` its `Format` ([[MYLA-342]]).

## Review 2026-11-09

Not ready ([[Project/Review-2026-11-09]]): `+ - * / %` on `impl<T: Add> Add for Box<T>` don't link natively ([[MYLA-415]]) and the checker types the result `Box<T>` (M2). The fix is in [[MYLA-417]].

- [ ] The review's blocker, fixed with [[MYLA-417]]
