---
id: MYLA-384
title: "Trait functions without self: T.f(x) on a type or a type parameter"
type: feature
status: todo
priority: medium
labels: [language, traits, generics, checker]
---
The language part of D172 ([[MYLA-354]]). Its own pull request, with its seed (D156). [[MYLA-385]] (`#derive(Json)`) builds on it.

```myla fragment
trait Zero {
    fun zero() -> Self
}

impl Zero for int {
    fun zero() -> int { return 0 }
}

struct Money {
    cents: int64,
}

impl Zero for Money {
    fun zero() -> Money { return Money { cents: 0 } }
}

fun total<T: Zero + Add>(xs: [T]) -> T {
    var s = T.zero()
    for x in xs { s = s + x }
    return s
}
```

- [ ] A trait declares, and its impls define, functions without a receiver; `Self` in their signatures is the implementing type
- [ ] `Type.f(args)` on a type that implements the trait (a struct, an enum, a built-in type: `int.zero()`), and `T.f(args)` on a type parameter bounded by it; the call resolves statically (D55: one impl per type), in the checker, the interpreter and the lowering on every target, generic instances included
- [ ] Only trait functions: an inherent `impl P { fun f() }` without `self` stays an error (no static methods outside traits), unless the task finds a reason to allow it — say so if so
- [ ] What a name means: `T.f` where `T` is a type parameter, `P.f` where `P` is a type, `m.f` a module's function (D170's `m.T` in types); a clash (a type and a module of one name) has a clear message
- [ ] The grammar, tree-sitter, the language server (hover, definition), the wiki ([[Language/Methods-and-traits]], [[Language/Generics]]), the `myla` skill
- [ ] Parity programs on every target, the error corpus (a function without `self` called on a value, on a type that doesn't implement the trait, an unbounded type parameter, an inherent one)
