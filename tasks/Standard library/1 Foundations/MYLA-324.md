---
id: MYLA-324
title: "std.option and std.map: combinators and map helpers"
type: feature
status: review
priority: high
labels: [stdlib, functional, maps, wave-1]
---
Wave 1 of [[Project/Standard-library-roadmap]], roadmap #20, #23. Methods on `Option<T>`, `Result<T, E>` and maps.

- **Owns:** `lib/std/option.my`, `lib/std/map.my`, `docs/Language/Standard-library/Option.md`, `docs/Language/Standard-library/Map.md`
- **Needs:** [[MYLA-319]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] `Option`: `map`, `and_then`, `or_else`, `unwrap_or`, `unwrap_or_else`, `ok_or`, `is_some`, `is_none`, `expect`
- [x] `Result`: `map`, `map_err`, `and_then`, `unwrap_or`, `ok`, `err`, `is_ok`, `is_err`, `expect`
- [x] Maps: `get_or(k, default)`, `update(k, default, f)`, `values()`, `items()`, `merge`, and a function counting how often each element of a list occurs
- [x] AoC's `get` uses with a default (14 of 29, [[MYLA-318]]) read as `m.get_or(k, d)`
- [x] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [x] Its page below [[Language/Standard-library]], with a doc block that runs

## Done

Built in `lib/std/option.my` and `lib/std/map.my`, with the pages [[Language/Standard-library/Option]] and [[Language/Standard-library/Map]] and their rows on [[Language/Standard-library]]. Every name is the task's: none was reserved or clashed (the builtins on maps are only `len`, `contains`, `keys`, `remove`, D151).

- `impl<T> Option<T>`: `map<U>`, `and_then<U>`, `or_else`, `unwrap_or`, `unwrap_or_else`, `ok_or<E>`, `is_some`, `is_none`, `expect(msg)`.
- `impl<T, E> Result<T, E>`: `map<U>`, `map_err<F>`, `and_then<U>`, `unwrap_or`, `ok`, `err`, `is_ok`, `is_err`, `expect(msg)`. `expect` panics with `msg` alone, as `E` may have no `Format`.
- `impl<K, V> [K: V]`: `get_or(k, default)`, `update(k, default, f)` (`var self`), `values()`, `items() -> [(K, V)]`, `merge(other)` (`var self`, `other`'s values win, its new keys go last); `pub fun counts<T>(xs: [T]) -> [T: int]`.
- AoC's lookups with a default: the solutions live outside the repository, so the box is met by the method itself; the Map page shows `match get(m, k) { Some(v) => v, None => 0 }` as `m.get_or(k, 0)`.

Tests first: before the impls, `myla test lib/std/option.my` failed to check (`type 'Option<int32>' has no method 'map'`, …) and `map.my` too (`type '[str: int32]' has no method 'items'`, 10 errors). After:

| Run | option | map |
| --- | --- | --- |
| `build/myla test lib/std/<m>.my --stdlib lib` | 17/17 passed | 9/9 passed |
| the same with `--native` | 17/17 passed | 9/9 passed |

`python3 -m unittest tests.burn.test_std_modules tests.burn.test_doc_blocks`: 6 tests OK (`test_std_modules` finds `option` and `map`; both pages' blocks check, run and print their output, interpreted and natively). With the modules embedded by `scripts/bootstrap.sh` (then `selfhost/embedded_std.my` restored), the pages' programs run without `--stdlib`. A mutation of `merge` (keep the old value) fails `map_merge`.

Found on the way:

- **Native `assert` with a computed message** (also found by the `std.str` lane): `fun main() { assert(true, name()) }` with `name()` returning `"x" + "y"`, or `assert(n == 3, f"n={n}")`, fails natively with `internal error: main: IR verifier: L2: drop of $0 (__temp), which holds no value`; the interpreter is fine. `Lower.intrinsic` in [[selfhost/lower.my]] lowers the message inside the failing branch, and the temporary's drop lands where it holds no value. The tests use literal messages.
- **Lambda parameters aren't inferred through an open type parameter**: `o.map((x) => x * 2)` and `apply(3, (x) => x + 1)` with `apply<T, U>(x: T, f: (T) -> U)` are `cannot infer the type of lambda parameter 'x'`, though `T` is known; `same<T>(x: T, f: (T) -> T)` infers. `infer_generic_call` and `infer_generic_method` in [[selfhost/checker.my]] drop the whole hint when the parameter type still holds a type parameter (`if contains_type_param(want) { hint = None }`). So `map`, `and_then` and `map_err` need `(x: int) => …`; `update`'s lambda infers, its `V` being the receiver's. A lambda of the wrong parameter type there reads `cannot infer type parameter(s) U for method 'map'` instead of a mismatch.
- `counts<T>` has no bound on `T`; once D163 needs `K: Eq + Hash` for a generic `[K: V]` ([[MYLA-313]]), it becomes `counts<T: Eq + Hash>`.
