---
id: MYLA-396
title: "Don't parse an imported module's #test cases"
type: improvement
status: done
priority: medium
labels: [loader, performance, check-time]
---
Found by [[MYLA-376]]. Since [[MYLA-360]] only the tested file's cases are the program's, but the loader still parses every imported module's cases and drops them afterwards (`without_tests` in [[selfhost/loader.my]]); only the implicit modules are parsed with their cases skipped. A `std` module that imports `std.int` explicitly makes every program that imports it parse `std.int`'s 2,042 cases (1,826 since [[MYLA-395]]): a hello world importing `std.bitset` with `std.int` took 58 ms to check instead of 46. So `std.bitset` and `std.bigint` keep their own bit counts.

- [x] Parse every module other than the entry with its cases skipped (`skip_tests`, as the implicit modules are), measured on a hello world importing `std.text`, `std.http`, `std.compress` and on the compiler's own build
- [x] `std.bitset` and `std.bigint` on `std.int`'s `count_ones`/`leading_zeros`/`trailing_zeros` then, if the native backend's call per word costs nothing measurable (it doesn't inline across modules: [[MYLA-368]])

## What changed

- **The loader** ([[selfhost/loader.my]]): `load` parses every module but the entry with `skip_tests` (the parser skips a case's brackets unparsed), not only the implicit ones; the `Loader.skip_tests` flag `load_implicit` set and the merge's `without_tests`/`fun_without_tests` went, as no module but the entry has cases left to drop. A broken case in an imported module (`#test(1 +)[2]`) is no longer an error of its importers; `myla test` of its own file still reports it.
- **std.bigint**: its private `leading_zeros` went for std.int's (`v[n - 1].leading_zeros()`, called once per long division). **std.bitset**: `highest` and `lowest` went for std.int's `leading_zeros` and `trailing_zeros`; `ones` stays, as `popcount`'s whole loop and the native backend doesn't inline another module's method ([[MYLA-368]]): through `count_ones` 2^26 words took 156 ms against 125 (min of 11; callgrind 2.737 G against 2.409 G instructions). The module's comment and [[Language/Standard-library/Bitset]] say so.

## Evidence

- Test first: `tests/burn/test_imported_cases.py`'s new `test_an_imported_module_s_cases_are_not_parsed` (a module whose only case is `#test(1 +)[2]`, imported by the file tested) failed before (`parse error: expected an expression, found ')'` in `broken.my`), passes after; the module's own `myla test` still reports the parse error. `test_imported_cases` (6) and `test_implicit_imports` (16) OK.
- **Check time** (CPU time of `build/myla check`, embedded library, min of 21 runs, the two compilers alternating), before (7b328dd) → after: hello world 58.9 → 56.7 ms; importing std.int 66.6 → 59.4; std.bitset 63.3 → 60.3; std.bigint 78.4 → 73.2; std.text 70.1 → 65.2; std.http 138.0 → 136.3; std.compress 79.1 → 76.6; one program importing std.int, std.bitset, std.bigint, std.text, std.http and std.compress 166.3 → 153.6 ms. The compiler's own: `check selfhost/main.my` 717 → 704 ms (min of 7), `build selfhost/main.my` 2,831 → 2,841 ms (min of 5: noise; its modules have few cases).
- **The import is free now** (the same, with `MYLA_STDLIB` on the library before and after the swap, min of 21): a hello world importing std.bitset, before the loader change 65.1 ms with the private helpers and 70.3 ms importing std.int; after it 67.0 and 67.3. std.bigint: 83.3 / 89.2 before, 80.2 / 81.9 after.
- **Native cost** (the same compiler, the library before and after; wall time min of 11 to 15, callgrind exact): std.bitset's word loops (400 popcounts, 10 `items` and 10 `next_from` walks of a set of 2^20 integers, 20,000 unions): 79.7 → 80.8 ms, 1,323,186,299 → 1,323,286,299 instructions (the unions' `leading_zeros` call); `items`/`next_from` alone 3,587,456,154 instructions before and after (the private `lowest` was a call too). std.bigint's 20,000 long divisions: 461.7 → 454.8 ms, 5,189,216,079 → 5,187,367,579 instructions (std.int's `leading_zeros` is branch-free where the private one looped).
- Cases: std.bitset 67/67, std.bigint 138/138, interpreted and `--native` (the removed helpers' cases gone).
- `python3 -m unittest tests.burn.test_compiler_parity tests.burn.test_selfhost_cases tests.burn.test_error_corpus tests.burn.test_selfhost_checker tests.burn.test_lsp tests.burn.test_std_modules tests.burn.test_imported_cases tests.burn.test_implicit_imports tests.burn.test_project_commands tests.burn.test_doc_blocks`: 749 tests, OK.
- `scripts/bootstrap.sh`: byte-identical fixed point (18,846,936 bytes).
- `scripts/test.sh fast`: 764 tests, failures `test_embedded_std` (expected: `selfhost/embedded_std.my` is behind `lib/` until the seed commit) and `test_time.test_an_async_read_lets_the_other_tasks_run`, a timing test that failed under the load of a parallel callgrind run and passes alone (12/12).

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]], with a follow-up in [[MYLA-416]]: an imported module's case with unbalanced brackets gives the importer a wrong error at end of file.
