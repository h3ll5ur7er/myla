---
id: MYLA-507
title: "Checker: a derived `eq` that can't compare a field is reported in `std/hash.my`, with a fix that can't be written"
type: bug
status: todo
priority: low
labels: [checker, derive, diagnostics]
---
Found by [[MYLA-436]]'s lane. `#derive(Eq)` on a generic struct gives `impl<T: Eq> Eq for P<T>`; when a field's type has `==` only under another bound (here `W<T>`'s written `eq` needs `T: Ord`), the derived `eq` doesn't check, and the error is reported at a position of the standard library, not at the `#derive` or the field:

```myla
struct W<T> {
    v: T,
}

impl<T: Ord> Eq for W<T> {
    fun eq(self, other: W<T>) -> bool {
        return !(self.v < other.v)
    }
}

#derive(Eq)
struct P<T> {
    w: W<T>,
}

fun main() {
    print(P { w: W { v: 1 } } == P { w: W { v: 2 } })
}
```

```
type error: operator '==' is not defined for 'W<T>': 'T' isn't Ord (it needs the bound 'T: Ord')
  --> <myla>/std/hash.my:3:23
```

The synthesized impl's positions are read in the wrong file (line 3, column 23 is no expression of the program either), and the help asks for a bound a struct can't carry (`type-parameter bounds are not supported on a struct`) and a derive can't add.

- [ ] The error points at the `#derive(Eq)` (or the field `w`) of the user's file
- [ ] The text says what to do instead: write `impl<T: Ord> Eq for P<T>` by hand (or, a decision: a derive takes the bounds its fields' impls need)
- [ ] A case in `examples/errors/` with its pinned `.stderr`
