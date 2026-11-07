---
id: MYLA-307
title: "myla test --native and --target: the native test harness (step 4 of MYLA-303)"
type: feature
status: done
priority: high
labels: [testing, codegen, targets]
---
Step 4 of [[MYLA-303]] (D162): `myla test --native` (and `--target <t>`) builds a harness program per file that runs every case, compares the result with the expected value, prints the interpreter's report and exits 1 on a failure; test programs are built and run with their expected output.

- [x] The harness: a generated entry that runs the cases in source order, with `[panic]`/`[exit]` expectations, a case's output shown on failure, `temp_dir` removed after each case
- [x] `--only` and `--list` natively; `--target aarch64-linux` and `wasm32-wasi` through the emulators the burn tests use
- [x] The interpreter's report equal to the native one on every corpus file that has cases; what differs documented (value rendering in FAIL lines, deferred blocks of a failed case)
- [x] Burn tests, Testing, the Project-tool page

## Done (2026-11-07)

- [[selfhost/harness.my]]: the harness program for a file: its text (the entry point blanked, positions kept) with, per case, `__myla_case_<k>` calling the function with the case's arguments (their source text by span, columns in characters) and comparing through `__myla_eq_<n>` and `__myla_repr_<n>` generated per type (the interpreter's `value_eq` and `py_repr`: `True`, chars as code points, `'text'` through `std.test.repr_str`, `P { x: 1 }`, `E.B(1)`, maps in insertion order, a `uint64` as its signed bits as the interpreter shows it); a type of another module imported by an alias (`from std.fs import IoError as __myla_t1`, a module above the root relatively); an `Err(e)` shown as the interpreter shows it; async cases awaited from an async `#main`; and the entry handing `std.test.Case`s to the runner.
- `std.test`'s runner (`run_in_children`, `case_detail`, `report_inline`, `summary`): one child process per case (`<harness> --case <n>`, under `MYLA_TEST_EMULATOR` for another target), MYLA_TEST_DIR per case and removed, the child's verdict on stderr (`myla test: <detail>`) or its runtime error read, the interpreter's wordings; where the first child can't start, the cases run in the harness itself and the report says where it stopped (`harness_report` in [[selfhost/driver.my]]).
- The CLI: `myla test [file] --native`, `--target <t>` (`cmd_test_native`, `native_tests`; `emulator`: `qemu-aarch64` for aarch64, else `MYLA_EMULATOR`); in a project the program, the test files and the test programs built for the target (`run_test_program_natively`). A harness that doesn't build is kept in the scratch directory.
- Evidence: the interpreter's and the native report compared on every corpus file with cases (`scratchpad/step1/parity.sh` of the session): 93 files, all the same but `lib/std/rt.my`, the runtime, which doesn't build as a program even without a harness (`runtime error: index out of bounds --> selfhost/codegen.my:2000:69` on `myla build lib/std/rt.my`, a pre-existing limit). `tests/burn/test_test_native.py`: the test-function and async programs (the async one without the deferred blocks of failed cases), what differs natively, `--only`/`--list`, a kept harness, every example and `lib/std` module with cases agreeing, aarch64 under qemu (the full report: the children run under the emulator too), wasm32 under Node (the cases in the harness itself, the run ended at the first failure); `test_project_commands.test_natively`: the project's report the same natively. Docs: [[Language/Attributes-and-testing#native-runs]], [[Architecture/Project-tool]], [[Language/Targets]], [[Development/Testing]].

What stays interpreter-only, by design: a failed case's deferred blocks (the child ends, D97), the values in a native runtime error's message (an expected `[panic("…")]` compared by prefix), a `StringBuilder` or function result (shown as `<StringBuilder>` / `<function>`, never equal, as `value_eq` has it).
