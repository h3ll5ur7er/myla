---
id: MYLA-306
title: "Integration tests in a project: tests/, test programs and test.program() (step 3 of MYLA-303)"
type: feature
status: in-progress
priority: high
labels: [testing, project-tool]
---
Step 3 of [[MYLA-303]] (D162): `myla test` in a project runs `tests/*.my` after `src/`.

- [ ] A file under `tests/` whose trailing comment block has `// output:` (with `// input:`, `// exit:`, `// stderr:`) is a test program: run in the interpreter, its output and exit status compared; reported as `PASS  tests/greets.my`
- [ ] Any other file under `tests/` is a file of `#test` cases, run as a `src/` file is
- [ ] `std.test.program()` gives the path of the project's program, built to `build/<name>` by `myla test` before the tests run (when the project has one and `tests/` exists)
- [ ] `--only` and `--list` cover the test programs
- [ ] Burn tests (`test_project_commands.py`), the Project-tool page, Testing
