---
id: MYLA-381
title: "std.iter: adapters and consumers over Iterator"
type: feature
status: done
priority: medium
labels: [stdlib, iterators]
---
The library part of D171 ([[MYLA-353]]), after [[MYLA-380]]. Functions of `std.iter`, chained with `|>`:

```myla fragment
import std.iter as iter

let total = xs.iter() |> iter.map((x) => x * 3) |> iter.filter((x) => x % 2 == 0) |> iter.sum()
```

- **Owns:** `lib/std/iter.my`, `docs/Language/Standard-library/Iter.md`, and `xs.iter()` in `lib/std/list.my`, `m.iter()` in `lib/std/map.my`, `s.chars_iter()` or the like in `lib/std/str.my` (decide the name; decided: none, see Evidence)

- [x] Sources: `xs.iter()`, `m.iter()` (key-value pairs in insertion order), `iter.range(a, b)`, `iter.repeat(v)`, `iter.from_fn(state, step)`
- [x] Adapters: `map`, `filter`, `take`, `skip`, `take_while`, `skip_while`, `enumerate`, `zip`, `chain`, `flat_map`
- [x] Consumers: `to_list`, `count`, `sum`, `fold`, `any`, `all`, `find`, `min`, `max`
- [x] `std.list`'s own methods stay eager (D171)
- [x] Test functions (generic, D162), interpreted and with `--native`; a page with a doc block that runs
- [x] Measured natively and interpreted against the eager list methods
- [x] A thin wrapper type with methods (`iter.of(xs).map(f)`) only if someone asks for it (D171): not built, no one asked

## Evidence

Built on `64458a7` (master after wave 3 and [[MYLA-380]]). Tests written first: the module's eleven test functions failed to check ("type '[int32]' has no method 'iter'") before `xs.iter()` and `m.iter()` existed. The page is [[Language/Standard-library/Iter]].

**What was built.**

- [[lib/std/iter.my]]: the sources `range(start, end) -> Range`, `repeat<T>(v) -> Repeat<T>`, `from_fn<S, T>(state, step: (S) -> Option<(T, S)>) -> FromFn<S, T>`; the adapters `map`, `filter`, `take`, `skip`, `take_while`, `skip_while`, `enumerate`, `zip`, `chain`, `flat_map` (`flat_map`'s `f` gives an iterator, `J: Iterator<U>`), each a `pub struct` with a bounded impl; the consumers `to_list`, `count`, `sum(it, zero)` (`T: Add`), `fold`, `any`, `all`, `find`, `min`, `max` (`T: Ord`, `Option<T>`, the first of equal least, the last of equal greatest). All take the iterator first and chain with `|>`; a lambda's parameter takes its type from the bound (`iter.map((x) => x * 3)` after any iterator of `int`).
- `xs.iter() -> ListIter<T>` in [[lib/std/list.my]]: `ListIter<T>` lives in `std.list`, beside the method that makes it, so the implicit module imports nothing for it. `m.iter() -> list_m.ListIter<(K, V)>` in [[lib/std/map.my]] is `self.items().iter()` (the map's runtime has no way to walk its slots by rank from Myla); `std.map` now imports `std.list`.
- `sum`'s zero is an argument, `iter.sum(0)`, as `xs.sum(0)` takes it: Myla has no zero of a generic `T`, and a `Zero` trait would need impls on the built-in types, which only the implicit modules may give (D164).
- **No string source.** `for c in s` loops without a list (D165) and a pipeline starts from `s.chars().iter()`. A lazy one would decode UTF-8 again in Myla in `std.str`, which every program checks (the runtime's `decode_at` isn't reachable), and would be slower interpreted than `s.chars()`.
- No wrapper type (`iter.of(xs)`): no one asked (D171).

**A cost found on the way (MYLA-380).** One `for x in it` over an iterator anywhere in a program makes the checker's `fill_in` rebuild every function body, the standard library's too: a hello world's check went from 47 to 55 ms (best of 20) when `std.list`'s test function looped with `for x in xs.iter()`. Reduced: the same program with `for x in (Upto { i: 0, stop: 3 })` checks in 55 ms, with `while let Some(x) = it.next()` in 47 ms. So `std.list`'s and `std.map`'s tests and all of `std.iter` loop with `while let`; with that, the hello world's check is 46 to 48 ms before and after (best of 20, twice), and a program that imports `std.iter` checks in 52 ms.

Tests:

- `build/myla test lib/std/iter.my --stdlib lib`: 11/11 interpreted, `--native`, `--target aarch64-linux` (qemu) and `--target wasm32-wasi` (node). A `Strict` iterator fails when asked for one value more than it has, so the cases see that `take`, `skip`, `take_while`, `zip`, `chain`, `any` and `find` ask for no value they don't need; breaking `Take` to ask first failed two cases.
- `lib/std/list.my` 13/13 (new `iterates`) and `lib/std/map.my` 10/10 (new `map_iter`), each interpreted, `--native`, aarch64 and wasm32.
- `test_compiler_parity`: a new `std_iter_pipelines` program (in `PROGRAMS` and `PINNED`) uses `std.iter` from a program with `|>`, `xs.iter()`, `m.iter()`, a user iterator, a user `Add` type, functions returning `iter.Filter<iter.Range, int>` and `iter.Map<list.ListIter<int>, int, int>`, `for` over a pipeline; `-k iter`: 12 tests OK on x86-64, the new one OK with `MYLA_TEST_TARGET=aarch64-linux` and `wasm32-wasi`.
- After a bootstrap: `test_std_modules`, `test_doc_blocks` (6 tests), `test_implicit_imports` (16), `test_lsp` and `test_modules` (159): OK.
- A native stress run of string pipelines (a million `f"w{x}"` through `filter`, `flat_map` over `chars().iter()`, `zip` with `repeat`, `skip`, `take_while`, `chain`, `max`): 10.7 MB peak, the same output as the interpreter.

Measured, best of five, MYLA-353's pipeline (`0..n` → `map(x * 3)` → `filter(even)` → `sum`, `int64`):

| | Hand-written loop | `iter.range(0, n) \|> …` | `xs.iter() \|> …` | Eager `xs.map(…).filter(…).sum(0)` | Building `xs` |
| --- | --- | --- | --- | --- | --- |
| Native, n = 10 M | 38 ms, 9 MB | 90 ms, 9 MB | 215 ms, 144 MB | 346 ms, 233 MB | 118 ms, 144 MB |
| Interpreted, n = 300 k | 1.09 s | 21.3 s | 23.6 s | 4.99 s | 1.94 s |

Natively the library's pipeline is 2.4 times the loop, as MYLA-380's hand-written one was; over a list it takes 97 ms beyond building it against the eager methods' 228 ms. Interpreted it is 20 times the loop and 4.3 times the eager methods.

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]].
