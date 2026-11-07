---
id: MYLA-307
title: "myla test --native and --target: the native test harness (step 4 of MYLA-303)"
type: feature
status: todo
priority: high
labels: [testing, codegen, targets]
---
Step 4 of [[MYLA-303]] (D162): `myla test --native` (and `--target <t>`) builds a harness program per file that runs every case, compares the result with the expected value, prints the interpreter's report and exits 1 on a failure; test programs are built and run with their expected output.

- [ ] The harness: a generated entry that runs the cases in source order, with `[panic]`/`[exit]` expectations, a case's output shown on failure, `temp_dir` removed after each case
- [ ] `--only` and `--list` natively; `--target aarch64-linux` and `wasm32-wasi` through the emulators the burn tests use
- [ ] The interpreter's report equal to the native one on every corpus file that has cases; what differs documented (value rendering in FAIL lines, deferred blocks of a failed case)
- [ ] Burn tests, Testing, the Project-tool page
