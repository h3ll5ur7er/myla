---
id: MYLA-538
title: "Checker: an impl's bound that names a generic trait (`I: Iterator<int>`) isn't checked where the impl is used"
type: bug
status: todo
priority: low
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

- [ ] `impl_bound_failing` checks a bound of a generic trait: the argument implements the trait with the bound's arguments, substituted by the target's (`int32` isn't `Iterator<int32>`)
- [ ] `impl_lacks` (the derive's field check) does the same
- [ ] A case in `examples/errors/` with its pinned `.stderr`
