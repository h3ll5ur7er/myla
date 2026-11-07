---
id: MYLA-315
title: "Generic constructors: an empty generic value, and a call's expected type in inference"
type: bug
status: todo
priority: medium
labels: [checker, generics, inference]
---
Found by Advent of Code ([[Project/AoC-2015-2021]], F6). Generic types such as `Queue<T>` and `Heap<T>` can't have a constructor function, so each use spells out a literal. That blocks a clean standard library API ([[MYLA-314]]).

```myla fragment
struct B<T> { items: [T] }

fun mk<T>() -> B<T> {
    return B { items: [] }    // (1)
}

fun main() {
    let a: B<int> = mk()      // (2)
}
```

1. "cannot infer the element type of an empty list `[]`; annotate it (e.g. `: [int]`)". This is a bug. [[Language/Generics]] says the expected type (here the return type `B<T>`) seeds struct literals, and it does for a concrete `B<int>`, but not when the type argument is a type parameter: the field's expected type `[T]` should type the empty list.
2. "cannot infer type parameter(s) T for 'mk' from the arguments; add a type annotation to guide inference". This is documented: a call's type parameters are inferred from its arguments only, and Myla has no explicit type arguments on a call. A type parameter that no argument fixes should be taken from the expected type (`B<int>` here), as Swift and Rust do.

- [ ] (1): the expected type seeds a struct literal's fields when its type arguments are type parameters; a test in the checker's cases and a program in every runner
- [ ] (2): a call's expected type fixes the type parameters its arguments leave open (a decision in passing: whether explicit type arguments, `mk<int>()`, come too)
- [ ] [[Language/Generics]] updated
