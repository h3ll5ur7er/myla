---
id: MYLA-393
title: "Retire the prelude's free get(m, k) for a map method m.get(k)"
type: improvement
status: done
priority: low
labels: [language, stdlib, prelude]
---
Found by the `std.http` lane ([[MYLA-347]]). The prelude declares a free function `get<K: Eq + Hash, V>(m: [K: V], k: K) -> Option<V>` at the top level of every program. An imported module's names are qualified (`http.get` is `std$http$get`), but the file being checked or tested keeps its own unqualified, so its `pub fun get` is "duplicate top-level declaration 'get'". `myla test lib/std/http.my` could never run, and the lane named the function `fetch`.

- [x] `m.get(k) -> Option<V>` in `std.map` (implicit, D164), the free `get` gone from the prelude (`prelude_src` in [[selfhost/checker.my]]); the about 15 uses in `examples/`, `lib/std/` and the docs moved; the language server's `<prelude>` path for it (MYLA-372) removed
- [x] `http.get(url)` beside `http.fetch(url)`, and `get_async`; `test_http`'s client calls `http.get` (added at the integration of wave 4 part 2)

## Decided (2026-11-08)

The owner chose the method: `m.get(k)` in `std.map`, and the prelude's free `get` goes.

## What changed

- [[lib/std/map.my]]: `fun get(self, k: K) -> Option<V>` in `impl<K: Eq + Hash, V> [K: V]`; `get_or` calls it. The test function `map_get` tries int, str, tuple and list keys, a removed key and an empty map.
- `prelude_src` ([[selfhost/checker.my]]) has no `get`. A call of the free form is `unknown function 'get'` with the help `a map's lookup is the method 'm.get(k)', not a function` (`unknown_function_notes`; pinned by `examples/errors/type_free_get.my`).
- 111 calls moved, found token-aware (code only, not strings or comments; a `get` after `.` or `fun` left alone): `selfhost/` 67, `tools/` 29 (language server 28, the grammar sample 1), `lib/std/` 8 (`args` 3, `toml` 3, `regex` 1, `map` 1; the first three now import `std.map`, as a module of `std` imports what it uses), `examples/maps.my` 3, the programs in `test_compiler_parity` 3 and the Maps doc block. The docs (Map, Collections-and-strings, Standard-library, Types, Type-checker) and the `myla` skill (both copies) say `m.get(k)`; archived pages, the review and the tasks keep their history.
- The language server's `<prelude>` path for `get` ([[MYLA-372]]) is gone; `test_lsp` checks that a file's own `get` resolves, hovers and has its references.
- The bootstrap needed no shim: the seed compiles the compiler with `lib/` from the disk, and the compiler is a program, so `std.map` is implicit there and `m.get(k)` resolves to the new method with the seed of today.
- `check_main`, the checker gate's checker without a loader, has std.map's `get` besides the prelude (`map_get_src`), as the recorded corpus called the prelude's.
- The recorded answers for the texts that changed (examples/maps.my, its declaration mutants, two parity programs) have aliases, the [[MYLA-240]] way: the old key's answer, or MYLA-221's alias composed, the changed lines' columns moved. The recorded corpus copy of maps.my stays as it was.

## Evidence

- Test first: `tests/burn/test_map_get.py` failed before std.map had the method (`type '[int32: int32]' has no method 'get'`), and passes interpreted and natively after; `test_error_corpus` failed on `type_free_get.my` ("expected a type error") before the prelude lost `get`, and passes after.
- `build/myla test lib/std/map.my`: 11/11 passed, and 11/11 with `--native`.
- A file with its own `pub fun get(url: str)` and a `#test` case runs and tests (`1/1 passed`).
- `scripts/bootstrap.sh` from the committed seed: byte-identical fixed point (17,091,882 bytes).
- `scripts/test.sh` (all): 1263 tests, OK (skipped=314). The first full run, before the aliases and `check_main`'s `get`, had 12 failures: the gates over the recorded answers of maps.my and the two parity programs, and the doc block's output.
- Not run: the seed. `scripts/update-seed.sh` and `selfhost/embedded_std.my` are the integrator's (D156); the commits between this task's first and last weren't bootstrapped one by one.

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]].
