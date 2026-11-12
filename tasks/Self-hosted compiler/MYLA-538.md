---
id: MYLA-538
title: "Checker: an impl's bound that names a generic trait (`I: Iterator<int>`) isn't checked where the impl is used"
type: bug
status: review
priority: high
labels: [checker, traits, soundness]
---
Found by [[MYLA-507]]'s lane. A generic impl's bounds are checked where the impl is used, such as `==` on its type, a map key or a bound's argument (`impl_bound_failing`, [[MYLA-379]]). A bound that names a generic trait with its arguments is skipped there ("a generic trait's arguments are its impl's to solve", D171). So `W<int>` counts as `Eq` under `impl<I: Iterator<int>> Eq for W<I>`, and the interpreter then fails inside itself:

```myla
struct W<I> {
    v: I,
}

impl<I: Iterator<int>> Eq for W<I> {
    fun eq(self, other: W<I>) -> bool {
        var a = self.v
        return a.next() == None
    }
}

fun main() {
    print(W { v: 1 } == W { v: 2 })
}
```

```
$ myla check w.my
ok
$ myla run w.my
runtime error: internal error: no method 'next' found for a value of type 'int32'
  --> w.my:8:22
```

The derive check of [[MYLA-507]] (`impl_lacks`) skips such bounds the same way.

- [x] `impl_bound_failing` checks a bound of a generic trait: the argument implements the trait with the bound's arguments, substituted by the target's (`int32` isn't `Iterator<int32>`)
- [x] `impl_lacks` (the derive's field check) does the same
- [x] A case in `examples/errors/` with its pinned `.stderr`

## Review 2026-11-12

Raised to `high` ([[Project/Review-2026-11-12]]): the unchecked bound is a hole in the type system, not only an internal error of the interpreter. With `impl<I: Iterator<str>> Eq for W<I>`, `W { v: [123456789].iter() } == W { v: [2].iter() }` checks, and the `eq` then reads an `int` as a `str`: the interpreter prints `0` and `123456789` as the string's length and text, and native code segfaults (`repro-r5/checker/bug3_m538_type_confusion.my`). The same through `+`, a map key and a `T: Eq` argument (`repro-r5/checker/w2.my`).

```myla
struct W<I> { v: I }
impl<I: Iterator<str>> Eq for W<I> {
    fun eq(self, other: W<I>) -> bool {
        var a = self.v
        let s = a.next().unwrap_or("")
        print(s.len())
        print(s)
        return true
    }
}
fun main() {
    print(W { v: [123456789].iter() } == W { v: [2].iter() })
}
```

- [x] Every use of an impl checks its bounds, not only `==` (the review's ask): the list under "What changed"

## What changed

- `meets_bound` (new): `c` meets a bound `tr` with the arguments `want` (the bound's, substituted by the impl's target) when it implements `tr`, as its own bounds say for a type parameter, and `trait_args_of(c, tr)` is `want` (its one impl's arguments, D55, or a type parameter's bound's, D171). `impl_bound_failing` and `impl_lacks` use it for every bound; a failing generic bound is reported with its arguments, `Iterator<str>`.
- `not_trait_why` says why for a generic bound: `'list.ListIter<int32>' isn't Iterator<str> (it implements 'Iterator<int32>')`, `'J' isn't Iterator<str> (its bound is 'J: Iterator<int32>')`. `bound_why` adds the reason to the `for` loop's, `format`'s and a generic-trait bound's (`check_generic_bounds`) errors, which gave none. `unqualified` strips only a bound text's head (`m$Conv<geo$P>` is `Conv<geo$P>`).
- The uses that check an impl's bounds, each `ok` before and an error after (all through `type_implements`, which `impl_bound_failing` serves): `==` and `!=` (`w.my`, `bug3`, `w5`, `w6`), `<`, `+` (`w2`), a map key (`w2`, through an annotation too), another bound's argument (`w2`'s `same`, a user trait's `T: Show`), a list's, tuple's and option's `==`, the bounded list methods `contains` and `sort`, `set.new<W<int>>()`, a `for` loop over an iterator whose `Iterator` impl is bounded, `iter.count` over one, a format hole (`f"{w}"`), a derive's field (`#derive(Eq) struct P { w: W<int> }`, and `struct P<I> { w: W<I> }`), a written impl's body (`impl<I: Eq> Eq for P<I>` comparing a `W<I>`: `'I' isn't Iterator<str>`), generic code (`W<J>` with `J: Iterator<int>`), a nesting (`B<W<…>>` under `impl<T: Eq> Eq for B<T>`) and a user generic trait (`C: Conv<int>` given a `Conv<str>`). A direct method call (`w.eq(x)`, `w.hash(h)`, `w.add(x)`, `w.show()`, `W.zero()`, `w3`'s inherent impl) was already checked (`check_call_bounds`).

## Evidence

- **Tests first**, failing at `6e699ca` and passing after:
  - `examples/errors/type_impl_bound_generic_trait.my` (the review's `bug3`, `==`), `type_impl_bound_generic_trait_argument.my` (a `T: Eq` argument), `type_derive_field_generic_trait_bound.my` (the derive's field check, with its help), each with its pinned `.stderr`. Before, `myla check` said `ok` to the first two; on the third only the later `==` failed (`'list.ListIter<str>' isn't Eq`).
  - `selfhost/checker.my` cases: `meets_bound` ×4, `trait_head` ×2, `unqualified` +1, `bound_why` ×1.
  - The parity program `impl_bounds_of_generic_traits_met` (`tests/burn/test_compiler_parity.py`, pinned): the bounds met, directly, in generic code (`J: Iterator<str>`; `J: Iterator<T>, T: Eq`), through `T: Eq`, a list's `==`, an adapter with a bounded `Iterator` impl in a `for` loop and in `iter.sum`, a user generic trait, a written impl comparing a bounded field: the same output before and after, interpreted and natively.
- **Reproducers** (`repro-r5/checker/`): `bug3_m538_type_confusion.my` and `w6.my` were `ok`, printing `0` and `123456789` interpreted and segfaulting natively; now `operator '==' is not defined for 'W<list.ListIter<int32>>': 'list.ListIter<int32>' isn't Iterator<str> (it implements 'Iterator<int32>')`. `w.my`, `w2.my` (at the `+`), `w5.my`: errors (`'int32' isn't Iterator<int32>`, `'str' isn't Iterator<int32>`, `'list.ListIter<str>' isn't Iterator<int32> (it implements 'Iterator<str>')`); `w3.my`, `w4.my` unchanged (errors already). 27 more variants (each use above, and programs that meet their bounds and must still check and run) in the lane's scratch directory, all as expected.
- **Check time** (callgrind, `myla check`, instructions; the base and each stage built the same way): hello world 21,205,285 at the base → 21,205,261 with this commit; a std.http server (`repro-r5/http/server.my`) 209,215,133 → 209,217,417 (+0.001 %). With all four of the lane's tasks: 21,232,453 (+0.13 %) and 209,713,254 (+0.24 %), nearly all of it MYLA-544's typing of left literals.
- **Suites**: see [[MYLA-544]]'s evidence (one run for the lane).
