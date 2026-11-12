---
id: MYLA-564
title: "Checker: an impl whose type parameter only a bound names is told to apply to an impossible type"
type: bug
status: review
priority: low
labels: [checker, diagnostics, traits]
---
Found by round 6's checker lane ([[MYLA-538]]). A function may have a type parameter that only a bound names (`fun count<I: Iterator<T>, T>(it: I)`, D171), an impl may not, which is fine, but the message names a type that can't exist: `W` has two parameters, and `W<I, J, T>` is what it asks for.

```myla error
struct W<I, J> { a: I, b: J }
impl<I: Iterator<T>, J: Iterator<T>, T> Eq for W<I, J> {
    fun eq(self, other: W<I, J>) -> bool { return true }
}
fun main() { print(1) }
```

```
$ myla check i1.my
type error: a generic impl must apply to 'W<I, J, T>' with its type parameters in order
  --> i1.my:2:1
```

- [x] The message says what is wrong: `T` is a type parameter of the impl that `W<I, J>` doesn't take (only its own type parameters, in order, D55), with a hint (a function, or a type parameter of `W`)
- [x] A case in `examples/errors/` with its pinned `.stderr`

## What was built

- [[selfhost/checker.my]]'s `check_impl_target`: before the old test of the impl's type (its type parameters, in order), an impl type parameter that the type's arguments don't name at all is its own error (`impl_param_unused`, with a `#test`):

```
type error: the impl's type parameter 'T' is not one of 'W<I, J>': a generic impl takes its type's own type parameters, in order
  --> i1.my:2:1
help: only a generic function may have a type parameter that only a bound names ('fun f<…, T>(…)'); or add 'T' to the type parameters of 'W'
```

  An impl whose type parameters are its type's in another order, or mixed with a concrete type (`impl<A, B> W<B, A>`, `impl<T> W<T, int>` for a two-parameter `W`), keeps the old message, which is right there.
- `examples/errors/type_impl_param_only_a_bound_names.my` and its pinned `.stderr`; [[Language/Generics]] says it after the example of a type parameter only a bound names.

## Evidence

- **Failing first**: the corpus case against the base's CLI gave `a generic impl must apply to 'W<I, J, T>' with its type parameters in order` (its `//~` line and `help` missing); with the change `test_error_corpus` passes (355 tests, the `.stderr` pinned by `MYLA_PIN_DIAGNOSTICS=1`). `build/myla test selfhost/checker.my` 990/990 (`impl_param_unused` among them).
- **Check time** (callgrind, `myla check`, millions of instructions; 07445ab's CLI, then the lane's tip, whose library is the lane's too): a hello world without imports 21.19 → 21.21, with `from std.io import println` 37.49 → 37.51, `repro-r5/http/server.my` (std.http, std.net, std.task, std.process) 210.86 → 211.11. A loop over the impl's type parameters only for a generic impl on a struct, an enum or an actor.
