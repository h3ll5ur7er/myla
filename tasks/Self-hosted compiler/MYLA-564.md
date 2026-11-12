---
id: MYLA-564
title: "Checker: an impl whose type parameter only a bound names is told to apply to an impossible type"
type: bug
status: todo
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

- [ ] The message says what is wrong: `T` is a type parameter of the impl that `W<I, J>` doesn't take (only its own type parameters, in order, D55), with a hint (a function, or a type parameter of `W`)
- [ ] A case in `examples/errors/` with its pinned `.stderr`
