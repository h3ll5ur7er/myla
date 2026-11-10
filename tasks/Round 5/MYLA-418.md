---
id: MYLA-418
title: "P4 The test harness: failing reports agree across runners"
type: bug
status: review
priority: high
labels: [test-runner, harness, round-5]
---
Work package P4 of [[Project/Review-2026-11-09]] (wave A1), with round 4's additions from [[Project/Review-2026-11-10]]. Files: `selfhost/harness.my`, `lib/std/test.my`, `selfhost/driver.my`, `selfhost/loader.my`, `tests/burn/test_test_native.py`, `tests/burn/test_std_modules.py`. Reopens [[MYLA-361]] and [[MYLA-397]].

- [x] M6: `exit(0)` in a case is not a pass natively; `[exit(0)]` passes
- [x] M7: a failing float is reported as the interpreter does (`2.0`)
- [x] M8: a test function returning `Result<(), E>` with a scalar `E` builds its harness natively ([[MYLA-361]])
- [x] M9 and D183: an expected `[panic(…)]` matches exactly, natively as interpreted
- [x] A case's stderr is reported the same way by both runners
- [x] Burn tests that hold failing reports to both runners: a float, `exit(0)`, a scalar `Err`, stderr, expected panics
- [x] S3: `native_tests` and `for_target` key the override on a normalized path (`./lib/std/…`, `--stdlib lib/`, `MYLA_STDLIB=$PWD/lib`), with a burn test per spelling ([[MYLA-397]])
- [x] `myla test lib/std/<m>.my` without `--stdlib lib` loads one copy of each module (option, bench, log, net, time, yaml loaded two)
- [x] `test_std_modules` asserts case counts, and runs `platform_aarch64` and `platform_wasm`'s 36 cases interpreted ([[MYLA-325]])
- [x] The lazy parity test fails on a `lib/std` file that reports `same 0` ([[MYLA-359]])
- [x] A module-id collision is reported with a location
- [x] A burn test that times out leaves a core dump or the child's stack, for the rare aarch64 hang under qemu ({R2} §1.6)
- [x] D183: the parity tests compare stderr

## How it works

- **The child's report** ([[lib/std/test.my]]): a case that returns writes a mark on stderr and its verdict after it (`case_end`, the same for a child, `--case <n>`, and a wasm32 run, `--from <n>`). No mark: the case ended the process, by a runtime error (status 1, the runtime's report last on stderr: the last `runtime error: ` that starts a line, else the last one, after a line the case left open) or an `exit`, `exit(0)` included. What comes before is the case's own stderr, passed on by `myla test --native` (it dropped it) and on wasm32, as the interpreter lets it through. An expected `[panic(…)]` matches exactly (D183).
- **Values**: a float through `std.test.repr_float` (std.num's `format_float`, the interpreter's `py_repr`); a test function's `Err` of a number, `char` or `bool` as `f"{e}"`.
- **Paths** ([[selfhost/driver.my]], [[selfhost/loader.my]]): `native_tests` keys the harness of a target's platform module where `for_target` reads it, and `for_target` finds an override under any spelling (`override_text`). `own_library`: with the embedded library, an entry that is a module of a copy of `std` on disk (`in_std_tree`) is loaded with that copy as its root (`std_tree_root`), written as the file is, or both absolute; with a named root written another way than the file (relative against absolute), both absolute. The host's `lib/std/platform.my` for a target with its own platform module is an error naming that module.
- **Collisions**: `check_ids` reports at the import that loads the second module (`import_of`).
- **Hangs**: `tests/burn/_hang.py`'s `run_watched` (gdb stacks, SIGQUIT with core dumps allowed, kept in `MYLA_HANG_DIR` or `$TMPDIR/myla-hangs`), used by the concurrency stress programs natively and under qemu.

## Evidence

Reproducers of the review (`repro/harness/h1`, `h2`, `h3`, `h5`, `h6`, `repro-r4/streams/paths.sh`), interpreted against `--native`, before and after (`--stdlib lib`):

| Case | Interpreted | Native before | Native after |
| --- | --- | --- | --- |
| h1 `two`, `big`, `negzero` | `got 2.0`, `got 1e+16`, `got -0.0` | `got 2`, `got 1e16`, `got -0` | as interpreted |
| h2 `leaves #1` (`exit(0)`, `[1]`) | `FAIL … exited with status 0` | `PASS` | as interpreted |
| h2 `leaves #2` (`[exit(0)]`) | `PASS` | `FAIL … expected exit status 0, exited with status 0` | `PASS` |
| h2 `never_checks` | `FAIL … exited with status 0` | `PASS` | as interpreted |
| h3 `Result<(), uint64>` | `FAIL  big: 18446744073709551615` | harness doesn't build: `type 'uint64' has no method 'format'` | as interpreted |
| h3 `Result<(), [int]>` | `FAIL  list: ERR: VList()` (MYLA-414's) | (didn't build) | `FAIL  list: [1]` |
| h5 `boom #1` `("bo")[panic("boom")]`, `#2` `("x")[panic("")]` | `FAIL … got runtime error 'bo'`, `'x'` | `PASS`, `PASS` | as interpreted |
| h5 `at` (index errors) | `#1` PASS, `#2` FAIL | `#1` FAIL, `#2` PASS | unchanged: native's text is MYLA-415's |
| h6 `myla test: fake verdict`, `runtime error: fake` on stderr, `progress... ` then `panic` | 3/3, the lines on stderr | 0/3 (`FAIL fake verdict`, `FAIL runtime error: fake`, `exited with status 1`), stderr dropped | 3/3, the same stderr byte for byte |

S3 (`paths.sh`, plus `--stdlib ./lib` and no `--stdlib`): before, every spelling but `lib/std/platform_aarch64.my --stdlib lib` gave `FAIL  linux_open_flags #1: the harness ended with status -11` on aarch64 and `runtime error: internal error: wasm: myla_main (myla_main) takes 2 words, called with 0` on wasm32; after, `23/23 passed.` and `13/13 passed.` for all seven and four spellings; `lib/std/platform.my --target wasm32-wasi` gave the same internal error and now says `myla: lib/std/platform.my is std.platform for x86_64-linux; for wasm32-wasi it is lib/std/platform_wasm.my, whose cases run there`.

Two copies: `myla test lib/std/yaml.my` without `--stdlib` failed with 20 type errors (`duplicate method 'to_json' for type 'int8'` in `<myla>/std/json.my`), as did `--stdlib $PWD/lib` with the relative file; both now `126/126 passed.`, from `lib/std` too (`yaml.my`); option, bench, log, net and time give the same report with and without `--stdlib lib` (17, 22, 26, 93, 149).

Burn tests, each failing before its change:
- `test_test_native.TestNative.test_failing_reports_agree`: one program (floats, `exit(0)` and `[exit(0)]`, `[exit(0)]` of a call that exits 3, scalar `Err`s of four types, five expected panics, three cases whose own stderr looks like a verdict or a runtime error, a failing case's stdout under its line): stdout, stderr and status equal interpreted and natively; `TestAarch64.test_failing_reports_under_qemu`, `TestWasm32.test_failing_reports` the same under qemu-aarch64 and Node.
- `TestAarch64`/`TestWasm32.test_its_platform_module_however_the_paths_are_written` (five spellings each), `TestNative.test_the_hosts_platform_module_for_another_target`, `TestNative.test_a_module_of_the_library_without_stdlib` (the six modules, and a library on disk with a module the tools' copy hasn't, from the root and from inside `std/`).
- `test_test_native.TestNative.test_the_corpus_agrees` compares stderr too.
- `test_modules.TestModuleIdCollision`: `module error: module id collision 'up$a' between proj/up/a.my and a.my` now `--> proj/main.my:2:6` (was the second module's file, without a position).
- `test_std_modules`: every module's report ends `N/N passed.` with N its `#test` lines, interpreted with `platform_aarch64` (23) and `platform_wasm` (13) too, natively without them (counts checked by hand against `--list` for all modules first: equal).
- `test_selfhost_parser.test_bodies_read_later_are_the_same`: with a `lib/std/zz_broken.my` holding a lex error it now fails (`0 not greater than 0 : same 0`), it passed before; passes on the tree.
- `test_concurrency_stress.test_a_hang_leaves_its_stacks_and_a_core`: a spinning program under a 1 s limit raises `Hung`, its `stacks.txt` names `myla_main`, a core is kept. Checked by hand under qemu: SIGQUIT leaves `qemu_<name>_<date>_<pid>.core` (8 MB for a spinning program); this machine's gdb can't read an aarch64 core (gdb-multiarch can).
- `test_compiler_parity`: every program's stderr compared (230 tests OK); `test_runtime_errors_are_reported_alike` holds ten programs ending in a runtime error to the interpreter's report without its source lines; four (`list_index`, `negative_list_index`, `string_index`, `missing_map_key`) differ only in the text native code is to carry (MYLA-415) and are listed in `AWAITING_MYLA_415`, their output and status compared.

Waiting for the other lanes (each in a test method of its own): `test_test_native.TestNative.test_runtime_errors_are_expected_alike` (MYLA-415: `list index 5 out of bounds (len 2)`, `map key 'b' not found` natively) and `TestNative.test_a_compound_err_is_shown_alike` (MYLA-414: the interpreter's `ERR: VList()`).

Suites (4 cores shared with four other lanes): bootstrap a byte-identical fixed point (19,579,101 bytes); the own cases of `selfhost/driver.my` 35/35, `loader.my` 134/134, `harness.my` 33/33, `lib/std/test.my` 68/68; `scripts/test.sh fast` 789 tests, 3 failures; the slow suites `test_selfhost_cases`, `test_error_corpus`, `test_lsp`, `test_concurrency_stress`, `test_aarch64.Aarch64Tasks`, `test_overflow`, `test_selfhost_checker` 527 tests OK; `test_compiler_parity` 230 OK; `test_std_modules` 3 OK (216 s); `scripts/test.sh` 1,413 tests, 3 failures, 336 skipped. The three failures are the expected ones: `test_embedded_std` (the embedded library behind `lib/` until the seed commit) and the two tests waiting for MYLA-414 and MYLA-415 above.

What stays different by design or by limit: a failed case runs no deferred block natively; a case that writes a line `runtime error: …` on stderr and then calls `exit(1)` reads natively as that runtime error (interpreted: `exited with status 1`), since the child can't tell its own report from the case's.

## Proposals (open decisions)

1. **The child's report** — built: a mark and the verdict after it on stderr, a runtime error found as the last report on stderr. Alternatives: the verdict on a descriptor of its own (needs a `dup2` the platform modules don't have), or the runtime marking its own report when a case runs (a runtime variable in `std.rt`, P2's file, and a staged seed). The mark costs nothing and covers every case met; the one confusion left is above.
2. **A library module run with the tools' library** — built: loaded with the copy of `std` it is in, as `--stdlib` would name it. Alternatives: resolve its relative imports into the embedded copy (then the file tested isn't the file on disk), or refuse without `--stdlib`. The comment of `in_std_tree` already said `myla check lib/std/fs.my` checks "as `--stdlib lib` would".
3. **The host's platform module for another target** — built: an error naming the target's own. Alternative: build it as a module of its own name, which can't work, as its primitives are the host's.
