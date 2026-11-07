---
id: MYLA-306
title: "Integration tests in a project: tests/, test programs and test.program() (step 3 of MYLA-303)"
type: feature
status: review
priority: high
labels: [testing, project-tool]
---
Step 3 of [[MYLA-303]] (D162): `myla test` in a project runs `tests/*.my` after `src/`.

- [x] A file under `tests/` whose trailing comment block has `// output:` (with `// input:`, `// exit:`, `// stderr:`) is a test program: run in the interpreter, its output and exit status compared; reported as `PASS  tests/greets.my`
- [x] Any other file under `tests/` is a file of `#test` cases, run as a `src/` file is
- [x] `std.test.program()` gives the path of the project's program, built to `build/<name>` by `myla test` before the tests run (when the project has one and `tests/` exists)
- [x] `--only` and `--list` cover the test programs
- [x] Burn tests (`test_project_commands.py`), the Project-tool page, Testing

## Done (2026-11-07)

- [[selfhost/test_programs.my]]: the trailing comment block read as a test program (`test_program_of`: `// input:`, `// output:` (the marker), `// exit:`, `// stderr:`), and the report of a run against it (`test_program_report`: `output differs` with the expected and the actual lines, `exited with status 1, expected 0` with its stderr, `stderr differs`, `killed by signal n`).
- `project_test` ([[selfhost/project_cmd.my]]) walks `tests/` after `src/`: a test program is run through the tool itself (`myla run <file> --root src --package …`, its input on stdin; the new `--root` option carries the project root into file mode, [[selfhost/main.my]]), the other files' cases as `src/`'s, under `== tests/` one line per program; a project with a program and a `tests/` is built first and `std.test.program()` names `build/<name>` (`TestOptions.program` → the interpreter's `__test_program`). `--only` matches a program's path, `--list` names them.
- Evidence: `tests/burn/test_project_commands.TestTestsDirectory`: a project with two source files, four test programs (input and output, wrong output, `exit: 3`, a runtime error with `stderr:`) and a test file driving the built program through `test.program()` and `std.process.command`: the report of 9 cases in 7 files, `--list` and `--only greets`, a library project (no program: nothing built, `test.program()` a runtime error, the test programs still run). Docs: [[Architecture/Project-tool]] (layout, the `test` row), [[Language/Attributes-and-testing#integration-tests-in-a-project]].
