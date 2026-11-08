---
id: MYLA-380
title: "Iterators in the language: the Iterator trait, generic-trait bounds, for over an iterator"
type: feature
status: todo
priority: medium
labels: [language, checker, generics, traits, iterators]
---
The compiler part of D171 ([[MYLA-353]]). Its own pull request, with its seed (D156). [[MYLA-381]] (`std.iter`) builds on it.

```myla fragment
struct Countdown {
    n: int,
}

impl Iterator<int> for Countdown {
    fun next(var self) -> Option<int> {
        if self.n == 0 { return None }
        self.n -= 1
        return Some(self.n + 1)
    }
}

fun total<I: Iterator<int>>(it: I) -> int {
    var s = 0
    for x in it { s += x }
    return s
}
```

- [ ] `trait Iterator<T> { fun next(var self) -> Option<T> }` in the prelude
- [ ] A bound names a generic trait with its arguments, `I: Iterator<T>`, in a function's, a method's and an impl's type parameters: the grammar (`grammar/myla.ebnf`, tree-sitter), the parser, the checker (the bound checked at the call against the type's one impl, D55; inside the body the trait's methods with `T` substituted)
- [ ] `for x in e` over a type implementing `Iterator<T>`: `var it = e; while let Some(x) = it.next() { … }`, in the checker, the interpreter (sync and async loops) and the lowering; `break` and `continue` work; lists, maps, strings and ranges are unchanged
- [ ] Parity programs, interpreted and native on every target: a user iterator, a generic adapter struct with a bounded impl (`impl<I: Iterator<T>, T, U> Iterator<U> for Map<I, T, U>`), `for` over both, a copied iterator keeping its own position
- [ ] The error corpus: a bound not satisfied, a wrong argument count on a bounded generic trait, `for` over a type that implements no `Iterator`
- [ ] [[Language/Methods-and-traits]], [[Language/Generics]], [[Language/Statements]] (loops), [[Language/Grammar]], the `myla` skill
- [ ] Measured: the lazy `Range → Map → Filter` sum of [[MYLA-353]] natively and interpreted, against the hand-written loop
