---
id: MYLA-304
title: "Test functions, failures that unwind, std.test and selection (step 1 of MYLA-303)"
type: feature
status: done
priority: high
labels: [testing, language, interpreter, std]
---
Step 1 of [[MYLA-303]], decided as D162: the interpreter's half of the test system.

- [x] A bare `#test` on a function without parameters is a test function (sugar for `#test()[()]`): a result of none or `Result<(), E>`; reported as `PASS  name`, an `Err(e)` as `FAIL  name: e` with `e` rendered as `{}` shows it
- [x] `[panic("message")]` and `[exit(n)]` as expected values: the case passes when the call ends in that runtime error (the message exact) or that exit status
- [x] A failed case unwinds its deferred blocks, innermost first (D141 amended); a deferred block that fails is reported with the case
- [x] `std.test`: `expect`, `expect_eq`, `expect_ne`, `fail`, `temp_dir` (a fresh directory per call, removed when the case ends however it ends), `program` (step 3's)
- [x] `myla test --only <text>` and `--list`, in file and project mode
- [x] A case's standard output shown only when it fails, under the FAIL line
- [x] The error corpus, burn tests, the Language page, Testing, the skill

## Done (2026-11-07)

- The checker ([[selfhost/checker.my]], `check_test_attr`): a bare `#test` is a test function (no parameters; no result or `Result<(), E>`, `is_test_result`); `[panic("…")]` and `[exit(n)]` read from the expected value's shape ([[selfhost/ast.my]]'s `expected_failure`, shared with the interpreter and the harness), their literals required. The printable primitives count as `Format` for a bound (`primitive_default_trait`), so `expect_eq(3, 4)` checks.
- The interpreter ([[selfhost/interp.my]]): `run_test_cases(sel)` and `run_case`: the outcome of a call (`Outcome`: returned, failed, exited) against its expectation, the report's wordings; `testing` on during a case: `run_defers` runs the deferred blocks on a failure too (`note_defer_failure` keeps a deferred block's own failure for the report), `close_scope` likewise for async code; `emit` and `__write` on fd 1 keep the output (`captured`), shown under a FAIL line as `      | line`; the primitives `__test_dir` (the case's scratch root, made on the first call under `$TMPDIR`, removed after the case) and `__test_program`.
- `lib/std/test.my`: `expect`, `expect_eq`, `expect_ne`, `fail`, `temp_dir`, `program`. Natively the two primitives read `MYLA_TEST_DIR` and `MYLA_TEST_PROGRAM` ([[selfhost/lower.my]], `io_call`).
- The CLI: `myla test [file] --only <text> --list` ([[selfhost/main.my]], `TestOptions` in the interpreter, `cmd_test` in [[selfhost/driver.my]], `project_test` in [[selfhost/project_cmd.my]]); `no #test cases match '<text>'.` with status 1.
- Evidence: `tests/burn/test_test_functions.py` (the report of 15 cases of every form, unwinding through nested blocks and `exit` with a file written by a deferred block, a deferred block's failure noted, scratch directories gone after passed and failed cases, a program's failure still running no deferred block, `--only`/`--list`, `temp_dir` outside a case in the interpreter and natively): before, `type error: '#test' requires an expected result`; after, 5 tests pass. The error corpus: `type_test_bare_params.my`, `type_test_bare_result.my`, `type_test_panic_literal.my`, `type_test_exit_literal.my` with their pinned diagnostics. `test_selfhost_cli.test_failures`'s expectation moved the printed line under its FAIL line (D162). Docs: [[Language/Attributes-and-testing]] (test functions, when a case fails, expected failures, selection and output), [[Language/Standard-library#stdtest]], [[Language/Statements]] (`defer`), [[Development/Testing]], the skill.
