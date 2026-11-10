---
id: MYLA-370
title: "wasm32: the native test harness stops at the first case that expects a panic"
type: bug
status: done
priority: medium
labels: [testing, wasm, harness]
---
Found by the `std.args` lane ([[MYLA-333]]). `myla test --target wasm32-wasi` ran 20 of `std.args`'s 26 cases: the first case expecting a runtime error (`[panic("…")]`, D162) ended the run there, where x86-64 and aarch64 run all 26. wasm32 has no way to catch a trap inside the module, so the harness needs another way to run such a case: each expected-failure case as a run of its own (the harness started once per case), or the expected panic checked by the host from the exit and the message.

- [x] Every case runs on wasm32, expected failures included; a failing case doesn't end the run: `myla test --target wasm32-wasi` runs the harness `--from <k>` itself (the harness runs the cases from `k` on in its process, each between markers on stdout and stderr, `std.test`'s `case_begin`/`case_end`); `myla test` cuts the output into the cases' (`cut_run`), reports each as a child's would be, and starts the next run after the case that ended one (`driver.resumed_tests`). A run per case that ends one, and one more
- [x] `test_test_native`'s wasm32 tests cover a `[panic(…)]` case followed by ordinary ones (`TestWasm32`: the native report of the test-function, async and receiver programs, a `[panic]` and an `[exit]` case among ordinary ones, the scratch directories removed, `--only`; `test_std_modules` runs on wasm32 under `scripts/test-target.py`, and `_targets.py` lists it)

## Evidence

- Before: `myla test lib/std/text.my --target wasm32-wasi` (MYLA_EMULATOR=`node tools/wasm/run.mjs`) reported 89/144, `ints #17` failing with its expected runtime error and the next 55 cases "not run (an earlier failure ended the run)"; `lib/std/args.my` 20/26. `test_test_native.TestWasm32` pinned that inline report.
- After: every standard library module with cases gives the same report on wasm32 as natively (51 of 51, `std.platform` aside, which is the x86-64 module; 2026-11-09), and `test_test_native.TestWasm32` (4 tests) passes; `python3 scripts/test-target.py wasm32-wasi test_std_modules`: OK in 40 s.
- Cost (4 CPUs, Node 22, the same machine): `std.str` 134 cases 0.38 s on wasm32 (one run) against 0.28 s natively; `std.text` 144 cases 0.58 s (4 runs) against 0.32 s; `std.regex` 1944 cases 2.1 s against 1.8 s; `std.int` 1826 cases with 44 expected failures 4.3 s (45 runs) against 1.7 s. Starting the harness once per case instead costs about 33 ms a case: 4.8 s for `std.text`, 4.5 s for `std.str`.
- Found on the way: with the dispatcher one function of 1826 `if`s and the case list in `main`, each run of `std.int`'s harness took Node 2.2 s from case 174 on (V8 tiers a large function up to TurboFan once it has run through enough of it: 0.3 s with `--liftoff-only`), 116 s for the module. The harness now dispatches in two steps (groups of 32 cases) and builds the case list in a function of its own: 0.1 to 0.2 s a run.
- Suites: `scripts/test.sh fast`: 715 tests, 3 failures, none from these changes: `test_embedded_std` and `test_project_commands.TestTestsDirectory.test_natively` because `selfhost/embedded_std.my` stays at its committed state (the rules: no seed or embedded library in this batch; both pass with it regenerated), and `test_time.Time.test_an_async_read_lets_the_other_tasks_run` (the interpreter's first line, timing on a loaded machine: the main checkout's interpreter fails it the same way). `tests.burn.test_test_native`, `test_test_functions`, `test_std_modules`, `test_selfhost_cases`: 23 tests OK. Bootstrap fixed point reached.

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]].
