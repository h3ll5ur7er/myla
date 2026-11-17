---
id: MYLA-802
title: "Checker: a type parameter only an operator bound names isn't fixed by the argument's impl (`C: Index<int, T>`)"
type: bug
status: todo
priority: low
labels: [checker, generics, round-7]
---
Found in the review's bundle of 2026-11-17 (`repro-r6/checker/op_bound_only_param_not_inferred.my`, not in its report); filed by [[MYLA-790]]. A type parameter that only a bound names is fixed by the argument's impl for a generic trait (`fun count<I: Iterator<T>, T>(it: I)`, D171), but not for an operator trait with type arguments (D200):

```myla error
struct B<T> {
    v: T,
}

impl<T> Index<int, T> for B<T> {
    fun index(self, i: int) -> T {
        return self.v
    }
}

fun sum3<C: Index<int, T>, T: Add>(c: C) -> T {
    return c[0] + c[1] + c[2]
}

fun main() {
    print(sum3(B { v: 2 }))
    print(sum3([1, 2, 3]))
}
```

`myla check`: `cannot infer type parameter(s) T for 'sum3' from the arguments; add a type annotation to guide inference`, for the struct and for the list alike (a list meets `Index<int, T>` by its own indexing). Base `fe30af6` and [[MYLA-790]]'s branch.

- [ ] The call's inference solves `T` from the impl the argument's type has for the bound's trait and its known arguments (`Index<int, ?>` on `B<int32>` gives `int32`; a list's, map's or string's indexing likewise), as `trait_args_of` does for `Iterator<T>`
- [ ] Tests: a parity program (`sum3` over a struct and a list, interpreted and natively), and the error where two impls would give `T` two types
- [ ] Docs: [[Language/Generics]] and [[Language/Methods-and-traits#operator-overloading]] say which bounds fix a parameter
