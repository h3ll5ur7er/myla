---
id: MYLA-367
title: "Native: an operator on a generic struct with a generic trait impl doesn't link"
type: bug
status: todo
priority: medium
labels: [codegen, generics, traits, monomorphization]
---
Found by the collections lane ([[MYLA-330]]). `impl<T> Eq for Box<T>` then `Box { v: 1 } == Box { v: 2 }` gives "undefined reference to 'myla_Box.eq'" on `myla build`; the interpreter prints the answer. `impl<T: Ord> Ord for Rev<T>` with `<` fails the same way. Calling `.eq(...)` or `.cmp(...)` directly links: the operator's lowering (`overloaded_scalar` in [[selfhost/lower.my]]) names the method by the type's key without its type arguments, so no instance is made. This is why `std.heap` has a max flag rather than a `Reverse<T>` wrapper.

- [ ] An operator on a generic struct calls the instance of its trait method for the struct's type arguments, on every target
- [ ] A parity program: `==` and `<` on a generic struct with generic `Eq` and `Ord` impls
