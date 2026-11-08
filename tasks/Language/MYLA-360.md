---
id: MYLA-360
title: "myla test: an imported module's cases on built-in-type methods count as the entry's"
type: bug
status: review
priority: medium
labels: [testing, modules]
---
Found by [[MYLA-320]]. The interpreter's `run_test_cases` and the native harness take a case to be the file's own when its function's name has no module id. A method on a built-in type is named `str.trim` or `int32.double` in every module, so the `#test` cases of an imported user module's `impl str` or `impl [int]` run as the entry file's. MYLA-320 left them out for the implicit std modules by skipping their cases at parsing. A user module still has the problem.

A variant, found by the `std.glob` lane ([[MYLA-326]]): a file under `lib/std/` that imports `std.list` runs `std.list`'s `[str].join` cases as its own, and with `--native` its harness doesn't build ("expected an expression" past the file's end). `std.path` and `std.glob` avoid `std.list` until this is fixed; swap their private helpers for it then.

The `std.args` lane ([[MYLA-333]]) saw the same with `std.str`: a file importing it ran `std.str`'s 106 cases as its own. So every implicit module imported explicitly brings its cases along, not only `std.list`.

- [x] The runners decide a case's file by its declaration's file, not by its name, interpreted and in the native harness
- [x] A burn test: a program importing a module with `impl str` methods that have cases runs only its own

Wave 3 found the native form in four lanes (MYLA-341, MYLA-342, MYLA-344, MYLA-345): a `lib/std` module importing `std.str`, `std.char`, `std.list` or `std.hash` couldn't run its cases with `--native` at all. The harness copied the imported module's case arguments by byte spans out of the entry file's text ("unexpected character", "expected an expression" past the file's end). The lanes wrote private copies of `split`, `join`, `pad_start`, CRC-32 and the like instead.

## What changed

The loader ([[selfhost/loader.my]], `load_program_opts`) keeps the `#test` attributes of the entry file only: every other module's declarations go through `without_tests`, as the implicit modules' already did (MYLA-320). Both runners and the native harness see the entry's cases and nothing else, whatever their names. An imported module's cases are no longer type-checked as part of another program either; they are when that module is the file tested.

## Evidence

- Test first: `tests/burn/test_imported_cases.py` (new, 4 tests) failed before the change, all four: a user module's `impl str` cases ran as the entry's (`str.bang #1`, `#2`: "4/4 passed" for a file with 2), natively "unterminated string literal"; a `lib/std` module importing `std.str`, `std.list`, `std.hash` and `std.char` ran their cases (`str.find #1` …) and natively didn't build. After it: OK, and the module's own cases still run when it is the file tested (`3/3`).
- `test_implicit_imports`, `test_std_modules`, `test_test_functions`, `test_selfhost_cases`, `test_project_commands`, `test_error_corpus`: 319 tests, OK.
- `scripts/bootstrap.sh`: byte-identical fixed point.

Follow-up for the integrator: the lanes' private helpers can be swapped for the std methods now (`std.text`, `std.grid`, `std.bitset`, `std.compress`'s checksums, `std.bigint`'s `filled`, `std.fs`'s helpers, `std.path`, `std.glob`).
