---
id: MYLA-399
title: "A list literal's element type isn't taken from its later elements"
type: improvement
status: backlog
priority: low
labels: [language, types, checker]
---
Found by the gaps lane ([[MYLA-379]]). A list literal types its elements by the first one, so a generic variant whose first element leaves a type parameter open fails, though a later element fixes it:

```myla error
enum Either<L, R> {
    Left(L),
    Right(R),
}

fun main() {
    let es = [Either.Left(1), Either.Right("a")]
    print(es.len())
}
```

`type error: cannot infer type parameter(s) R; add a type annotation to guide inference` at `Either.Left(1)`. With the list's type written (`let es: [Either<int, str>] = …`) it checks. The same holds for a struct literal's field holding such a list, `Page { items: [Tagged.One(p)], next: None }` as a `Page<Tagged<Point, bool>>`.

- [ ] A list (and map) literal's element type unifies its elements' types, a variant's open type parameters taken from a later element, as Rust does; or the message says that the list's type fixes it
