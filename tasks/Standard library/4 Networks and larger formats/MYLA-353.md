---
id: MYLA-353
title: "Decision: iterators and for over a trait"
type: chore
status: done
priority: low
labels: [decision, language, stdlib, wave-4]
---
Wave 4 of [[Project/Standard-library-roadmap]], roadmap #21. Whether Myla gets an `Iterator` trait, and with it `for x in it` over any type implementing it and lazy adapters (`map`, `filter`, `take`), so a pipeline doesn't build a list at each step. A language decision first: what `for` desugars to, how an adapter holds the closure and the iterator it wraps by value, and what that costs natively.

- **Needs:** nothing; it can start as soon as its wave does

- [x] Options and a recommendation written here for the owner
- [x] The decision recorded: D171, built as [[MYLA-380]] and [[MYLA-381]]

## Options (for the owner, 2026-11-08)

What it is about. Today a pipeline builds a list at every step:

```myla fragment
let total = xs.map((x) => x * 3).filter((x) => x % 2 == 0).sum()   // two lists of n
```

An iterator is a value with a `next`. Each adapter wraps the iterator before it, and nothing is built until something consumes the pipeline:

```myla fragment
trait Iterator<T> {
    fun next(var self) -> Option<T>
}

struct Map<I, T, U> {
    inner: I,
    f: (T) -> U,
}

impl<I: Iterator<T>, T, U> Iterator<U> for Map<I, T, U> {
    fun next(var self) -> Option<U> {
        return match self.inner.next() {
            Some(v) => Some(self.f(v))
            None => None
        }
    }
}
```

### What works today, and what doesn't

Tried on master `1dd86a6`:

- Generic traits (D55), generic impls of them (`impl<T> Iterator<T> for Wrap<T>`), and a bounded impl that calls a `var self` method on a field of the bound's type (`impl<I: Next> Next for Doubled<I>`) all work, interpreted and natively.
- **A bound can't name a generic trait:** `impl<I: Iterator<T>, T, U>` and `fun sum<I: Iterator<int64>>(it: I)` are a parse error ("expected '>' to close type parameters, found '<'"). That is the one missing language piece for adapters. D55 allows one impl of a trait per type, so `I` fixes `T`, as an associated type would.
- `for x in it` over a struct is "`for ... in` requires a list or map".

### Measured

The sum of `3x` over the even `3x` for `x` in `0..n`, `int64`, best of three. The machine was shared with five agents, so read the ratios, not the absolute times.

| | Plain `while` loop | Lazy: `Range` → `Map` → `Filter`, hand-written | Eager: `xs.map(…).filter(…)` |
| --- | --- | --- | --- |
| Native, n = 10 M | 36 ms, 11 MB | 88 ms, 11 MB | 330 ms, 238 MB |
| Interpreted, n = 300 k | 0.9 s | 12.8 s | 4.0 s |

Natively, lazy is about 4 times faster than eager, in constant memory, and 2.5 times slower than the hand-written loop (one indirect call per closure per step, and the `Option` each `next` returns). Interpreted, lazy is 3 times *slower* than eager. Each `next` is an interpreted method call with a `var self` copy-back of the nested struct, where the eager `map` loops inside one call. For `#test` and `myla repl` this matters ([[MYLA-317]]).

### The questions

1. **The trait.** `trait Iterator<T> { fun next(var self) -> Option<T> }` in the prelude (it has to be there for `for`), plus bounds with type arguments (`I: Iterator<T>`) in the parser, the checker and the impl bounds.
2. **What `for` desugars to.** `for x in e`, where `e`'s type implements `Iterator<T>`, becomes `var it = e; while let Some(x) = it.next() { … }`. Lists, maps, strings and ranges keep their built-in loops, so nothing that works today gets slower. An iterator is a value, so `let b = a` copies the position: `a.next()` doesn't move `b` (Rust moves, Swift copies; this is Swift's behaviour).
3. **Where the adapters live, and how they're called.**
   - **A. Module functions in `std.iter`, chained with `|>`** (recommended):
     ```myla fragment
     import std.iter as iter

     let total = xs.iter() |> iter.map((x) => x * 3) |> iter.filter((x) => x % 2 == 0) |> iter.sum()
     ```
     Needs no language feature beyond the bounds. It is D164's rule: what isn't an operation on a built-in type is a module function. `xs.iter()` goes in `std.list` (implicit), `m.iter()` in `std.map`. A user's iterator gets every adapter as soon as it implements `next`.
   - **B. Default method bodies in traits**, so `it.map(f)` works on any iterator (Rust's shape). This is a bigger change: traits are signatures only today. It can come later, with A's functions as the bodies.
   - **C. A wrapper type with methods**, `iter.of(xs).map(f).filter(p).sum()`. It needs no default bodies, but every adapter wraps its result again, and a user's own iterator has to be wrapped before it gets the methods.
4. **The adapters of a first version:** `map`, `filter`, `take`, `skip`, `take_while`, `skip_while`, `enumerate`, `zip`, `chain`, `flat_map`; and the consumers `to_list`, `count`, `sum`, `fold`, `any`, `all`, `find`, `min`, `max`. Plus `iter.range(a, b)`, `iter.repeat(v)` and `iter.from_fn(state, step)`. A closure can't change what it captures (D48, D93), so a generator with state is either a struct or `from_fn`'s explicit state.

### Limits whichever option is chosen

- A pipeline's type is a nest of generics: `Filter<Map<ListIter<int>, int, int>, int>`. A local variable needs no annotation, but a function that returns a pipeline must spell that type, since Myla has no `impl Iterator<int>` result type. One could be added later; Swift's `some Sequence` is the model.
- No dynamic dispatch (no trait objects): a list of iterators of different kinds stays impossible.
- Async iteration (`for await`) is a separate decision.

### Recommendation

Yes: A, with the trait, generic-trait bounds and `for` over an `Iterator`. Build it as a compiler task in its own pull request, since the prelude and the checker change and it needs a seed (D156), then `std.iter` as a library lane. Measure the interpreter's cost of `next` before `std.list`'s own methods start to use iterators: they should stay eager.

Alternatives:

- B instead of A: nicer call sites, but a new trait feature first.
- No iterators at all: keep the eager list methods, which are faster interpreted, 4 times slower natively, and build every intermediate list.

## Decided (D171, 2026-11-08)

The owner chose the recommendation, A: the trait in the prelude, generic-trait bounds, `for` over an `Iterator`, and `std.iter`'s functions chained with `|>`. In the owner's words, an additional thin wrapper type (C) "should be easy to add if someone requests it". The compiler part is [[MYLA-380]], with a seed of its own; `std.iter` is [[MYLA-381]], after it.
