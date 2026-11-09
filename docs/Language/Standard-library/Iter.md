# std.iter

Lazy adapters and consumers over the prelude's `Iterator<T>` ([[MYLA-381]], D171). They are functions that take the iterator first, so a pipeline chains them with `|>` (`x |> f(y)` is `f(x, y)`). An adapter wraps the iterator before it and asks it for a value only when it needs one, so nothing is built until a consumer such as `to_list` or `sum` runs the pipeline. The sources of the built-in types are methods of the implicit modules: `xs.iter()` of [[Language/Standard-library/List]] and `m.iter()` of [[Language/Standard-library/Map]]. `range`, `repeat` and `from_fn` are here. Any type with `impl Iterator<T>` gets every adapter as soon as it has `next` ([[Language/Methods-and-traits#iterators]]).

```myla
import std.iter as iter

fun main() {
    let xs = [5, 3, 8, 1, 9, 2]
    print(xs.iter() |> iter.map((x) => x * 3) |> iter.filter((x) => x % 2 == 0) |> iter.sum(0))

    // nothing is built until a consumer asks: `take_while` ends the infinite source
    let powers = iter.from_fn(1, (p) => Some((p, p * 2)))
    let small = powers |> iter.take_while((p) => p < 100) |> iter.map((p) => f"{p}") |> iter.to_list()
    print(small.join(" "))

    var ages: [str: int] = [:]
    ages["ann"] = 31
    ages["bob"] = 27
    ages["cy"] = 35
    let older = ages.iter() |> iter.filter((kv) => kv.1 > 30) |> iter.map((kv) => kv.0) |> iter.to_list()
    print(older.join(","))

    for p in iter.zip(iter.range(1, 4), ["a", "b", "c"].iter()) |> iter.skip(1) {
        print(f"{p.0}{p.1}")
    }
    let lines = ["one two", "", "three"]
    print(lines.iter() |> iter.flat_map((l) => l.words().iter()) |> iter.count())
    print(iter.repeat("ab") |> iter.take(3) |> iter.fold("", (acc, s) => acc + s))
    print(xs.iter() |> iter.max() |> show())
    print(xs.iter() |> iter.find((x) => x > 20) |> show())
}

fun show(o: Option<int>) -> str {
    return match o {
        Some(v) => f"{v}"
        None => "none"
    }
}
// output:
// 30
// 1 2 4 8 16 32 64
// ann,cy
// 2b
// 3c
// 3
// ababab
// 9
// none
```

A lambda's parameter types can be left out: the iterator's element type gives them. In `iter.map(it, f)` the type of `it` fixes `I`, and `I`'s impl of `Iterator<T>` fixes `T` for the lambda after it ([[Language/Generics]]). An iterator is a value: `let b = a` copies its position, and a pipeline in a variable that two consumers use runs twice, from the start each time.

[TOC]

## Sources

| Item | Meaning |
| --- | --- |
| `xs.iter() -> ListIter<T>` | The elements of a list, first to last (`std.list`, implicit) |
| `m.iter() -> ListIter<(K, V)>` | The entries of a map as `(key, value)` pairs, in insertion order (`std.map`, implicit) |
| `range(start: int, end: int) -> Range` | `start`, `start + 1`, … up to but not including `end`; none when `end` isn't greater. `for i in a..b` is the loop; this is the iterator that starts a pipeline |
| `repeat<T>(v: T) -> Repeat<T>` | `v` again and again, without end: follow it with `take`, a consumer that stops (`find`, `any`, `all`), or `zip` it with a finite iterator |
| `from_fn<S, T>(state: S, step: (S) -> Option<(T, S)>) -> FromFn<S, T>` | The values `step` gives from a state: `step(s)` is `Some((value, next state))`, or `None` to end. A closure can't change what it captures (D48, D93), so the state goes in and comes back out: `iter.from_fn((0, 1), (s) => Some((s.0, (s.1, s.0 + s.1))))` are the Fibonacci numbers |

There is no lazy iterator over a string's characters. `for c in s` loops over them without a list (D165), and a pipeline starts from `s.chars().iter()`, which makes the list of `char`s once. A lazy one in `std.str` would decode UTF-8 again in Myla, which the runtime does already for `for c in s` and `s.chars()`, and `std.str` is checked with every program ([[MYLA-359]]). Interpreted it would also be slower than `s.chars()`, which decodes in one call.

## Adapters

Each gives a struct of this module that implements `Iterator` (the element type it gives in the last column).

| Item | Meaning | Gives |
| --- | --- | --- |
| `map(it, f: (T) -> U)` | `f` of each value | `Map<I, T, U>`, `U` |
| `filter(it, keep: (T) -> bool)` | The values for which `keep` holds | `Filter<I, T>`, `T` |
| `take(it, n: int)` | The first `n` values (all of them when there are fewer). It asks `it` for no more than `n`, so it ends an infinite iterator | `Take<I, T>`, `T` |
| `skip(it, n: int)` | The values after the first `n`; the first `next` skips them | `Skip<I, T>`, `T` |
| `take_while(it, pred: (T) -> bool)` | The values up to the first for which `pred` doesn't hold (which it takes from `it` but doesn't give) | `TakeWhile<I, T>`, `T` |
| `skip_while(it, pred: (T) -> bool)` | The values from the first for which `pred` doesn't hold on; `pred` isn't asked after that | `SkipWhile<I, T>`, `T` |
| `enumerate(it)` | Each value with its index from 0, `(0, a)`, `(1, b)`, … | `Enumerate<I, T>`, `(int, T)` |
| `zip(a, b)` | Pairs of a value of `a` and one of `b`, until either ends (`b` isn't asked once `a` has ended) | `Zip<A, B, T, U>`, `(T, U)` |
| `chain(a, b)` | The values of `a`, then those of `b`: two iterators of the same element type, of different kinds if need be (a list's and a range's) | `Chain<A, B, T>`, `T` |
| `flat_map(it, f: (T) -> J)` | The values of the iterators `f` gives, one after the other, where `J: Iterator<U>`: `iter.flat_map(words, (w) => w.chars().iter())` | `FlatMap<I, T, J, U>`, `U` |

`it`, `a` and `b` are any iterators: `I: Iterator<T>` (`A: Iterator<T>`, `B: Iterator<U>` for `zip`). A struct's type parameters must all appear in its impl's target, so an adapter that gives the inner iterator's own values names their type too (`Take<I, T>`), though only its `inner: I` holds them.

## Consumers

They run the iterator to its end, or until they know the answer.

| Item | Meaning |
| --- | --- |
| `to_list(it) -> [T]` | The values, in a list |
| `count(it) -> int` | How many values there are (`iter.filter(p) \|> iter.count()` counts those `p` holds for) |
| `sum(it, zero: T) -> T`, `T: Add` | The values added to `zero`: `iter.sum(0)`, `iter.sum(0.0)`, `iter.sum(V2 { x: 0, y: 0 })`. Myla has no zero of a generic `T`, so the caller gives it, as for `xs.sum(0)` |
| `fold(it, init: A, f: (A, T) -> A) -> A` | `f(… f(f(init, x0), x1) …, xn)`; `init` when there are no values |
| `any(it, pred: (T) -> bool) -> bool` | Whether `pred` holds for some value (false when there are none); it stops at the first |
| `all(it, pred: (T) -> bool) -> bool` | Whether `pred` holds for every value (true when there are none); it stops at the first it doesn't hold for |
| `find(it, pred: (T) -> bool) -> Option<T>` | The first value for which `pred` holds |
| `min(it) -> Option<T>`, `max(it) -> Option<T>`, `T: Ord` | The least value (the first of equal ones), the greatest (the last of equal ones), as Rust's; `None` when there are none |

## Types

A local needs no annotation, but a pipeline's type is a nest of generics, and a function that returns one spells it, through the modules' names (D170):

```myla fragment
import std.iter as iter
import std.list as list

fun evens(n: int) -> iter.Filter<iter.Range, int> {
    return iter.range(0, n) |> iter.filter((x) => x % 2 == 0)
}

fun squares(xs: [int]) -> iter.Map<list.ListIter<int>, int, int> {
    return xs.iter() |> iter.map((x) => x * x)
}
```

There are no trait objects, so a list can't hold iterators of different kinds. A list or a map isn't an iterator itself: `xs |> iter.map(f)` is an error (for now "cannot infer the type of lambda parameter 'x'"): write `xs.iter()`. `std.list`'s own methods stay eager (D171), and a thin wrapper type with methods (`iter.of(xs).map(f)`) can be added if someone asks for it.

## How it works

An adapter is a generic struct that holds the iterator it wraps and its closure, with a bounded impl, `impl<I: Iterator<T>, T, U> Iterator<U> for Map<I, T, U>`; its `next` calls the inner `next`. A closure can't keep state of its own, so what an adapter counts (`Take`'s `left`, `Enumerate`'s index, `FlatMap`'s current inner iterator) is a field of its struct. Natively each instance is compiled for its concrete types ([[Architecture/Monomorphization]]), so a pipeline is a nest of direct calls, one indirect call per closure per value.

An adapter's `next` loops with `while let Some(v) = self.inner.next()`, since a `for` would work on a copy of `self.inner` and leave it where it was. A `for` over an iterator costs only the function it is in: the checker rebuilds the bodies holding one, after the check, and leaves the rest as they are (`fill_in`, [[MYLA-382]]), so the tests of `std.list` and `std.map`, which every program checks, use `for`.

## Speed

MYLA-353's pipeline, the sum of `3x` over the even `3x` for `x` in `0..n`, `int64`, best of five on x86-64 (4 cores, 2026-11-08):

```myla fragment
iter.range(0, n) |> iter.map((x) => (x as int64) * 3) |> iter.filter((x) => x % 2 == 0) |> iter.sum(0)
```

| | Hand-written `while` loop | `iter.range(0, n) \|> …` | `xs.iter() \|> …` | Eager `xs.map(…).filter(…).sum(0)` | Building `xs` alone |
| --- | --- | --- | --- | --- | --- |
| Native, n = 10 M | 38 ms, 9 MB | 90 ms, 9 MB | 215 ms, 144 MB | 346 ms, 233 MB | 118 ms, 144 MB |
| Interpreted, n = 300 k | 1.09 s, 45 MB | 21.3 s, 45 MB | 23.6 s, 75 MB | 4.99 s, 118 MB | 1.94 s, 75 MB |

The two columns over `xs` include building the list of `n` `int64`s. Natively the pipeline over a list takes 97 ms beyond building it, the eager methods 228 ms (2.4 times as long) and 89 MB more for their two lists; from `range` it needs no list at all and is 2.4 times the hand-written loop. Interpreted it is the other way round: the pipeline from `range` takes 20 times the loop and 4.3 times the eager methods with their list built; over the list, beyond building it, the pipeline takes 21.7 s and the eager methods 3.0 s. Each `next` is an interpreted method call with its `var self` copied back, once per adapter, where the eager `map` and `filter` loop inside one call each. So `std.list`'s methods stay eager (D171), and a pipeline pays off in compiled code, or where the lists would be large or a consumer stops early.

## Tests

`#test` can't take a generic function (D116), so the module's cases are test functions (D162) that run the adapters on concrete iterators: `myla test lib/std/iter.my`, interpreted and with `--native`, on x86-64, aarch64 and wasm32. A `Strict` iterator of the tests gives 1 to `n` and fails when it is asked for one more, so `take`, `skip`, `take_while`, `zip`, `chain`, `any` and `find` are seen to ask for no value they don't need. The module imports `std.list`, `std.map` and `std.option` for its tests, all three implicit anyway, and not `std.test`.
