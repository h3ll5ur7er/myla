---
id: MYLA-802
title: "Checker: a type parameter only an operator bound names isn't fixed by the argument's impl (`C: Index<int, T>`)"
type: bug
status: review
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

- [x] The call's inference solves `T` from the impl the argument's type has for the bound's trait and its known arguments (`Index<int, ?>` on `B<int32>` gives `int32`; a list's, map's or string's indexing likewise), as `trait_args_of` does for `Iterator<T>`
- [x] Tests: a parity program (`sum3` over a struct and a list, interpreted and natively), and the error where two impls would give `T` two types
- [x] Docs: [[Language/Generics]] and [[Language/Methods-and-traits#operator-overloading]] say which bounds fix a parameter

## Evidence

- `solve_bounds` (`selfhost/checker.my`) now solves an operator trait's bound too, once its right operand's (or index's) type is known (`params_known`): `op_trait_args_of` gives the arguments of the impl that operand picks (a type parameter's bound's, an impl in `op_impls`, a number's own operators, a list's, map's or string's indexing, a signed number's or float's `-`), and they are unified with the bound's as `trait_args_of`'s are for `Iterator<T>`. A bound whose right operand is still open fixes nothing. `check_call_bounds`' message for an unmet operator bound names the bound with what is known (`D: Index<int32, int32>`, where it said `Index<int32, T>`) and, where the operand picks an impl with another result, what that impl gives (`: it implements 'Index<int32, str>'`); the pinned messages of `T: Add` and `T: Mul<float64>` are unchanged.
- Before: the task's program, `build/myla check`: `cannot infer type parameter(s) T for 'sum3' from the arguments`. After: `ok`; it prints `6` and `6` interpreted and natively.
- Parity program `type_parameters_an_operator_bound_fixes` (`tests/burn/test_compiler_parity.py`): `sum3` over a struct, an `[int32]`, a `[float64]` and a `str` (its `uint8`s), `at<C: Index<K, T>, K, T>` over a map and a struct, a generic function passing its own bounded parameter on (`again<D: Index<int, U>, U: Add>` calling `sum3(d)`), `times<A: Mul<R, O>, R, O>` with two impls of `Mul` on one struct and with numbers, `negated<N: Neg<O>, O>` on a struct and a float. Before: `cannot infer type parameter(s) T for 'sum3'`. After: the same 13 lines interpreted, natively, on aarch64 (qemu) and on wasm32 (Node).
- Error corpus `examples/errors/type_op_bound_impls_disagree.my` (and its `.stderr`): two bounds whose impls give `T` two types, `type 'B<str>' does not satisfy the bound 'D: Index<int32, int32>' required by 'first': it implements 'Index<int32, str>'`.
- `#test` cases of `op_trait_args_of` (a list's, a map's and a string's indexing, a number's `*` and `-`, a struct's impl by its index's type) and of `params_known`.
- Suites: see [[MYLA-826]]'s evidence, run on the branch with both.
