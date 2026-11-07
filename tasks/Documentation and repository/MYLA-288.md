---
id: MYLA-288
title: Hard expectations instead of the recorded Python answers
type: improvement
status: in-progress
priority: high
labels: [tests, oracle]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]). With the Python toolchain retired ([[MYLA-219]]), the recorded answers decayed within five days: every `selfhost/`, `tools/` and `lib/std/` file has changed, so the lexer and parser corpus gates skip all 57 toolchain files, the `myla test` parity gate compares 33 of 92 files, and 15 of the 17 MB of recordings can never be consulted again; 20 new error-corpus files are held to the self-hosted CLI's own output, and the checker gate skips them. The suite is still a real check because 49 of 69 modules compare the interpreter with native code or use hard expectations, but the README and [[Development/Testing]] describe recordings as the oracle.

- [x] Say what the oracle is in [[Development/Conventions]]: the interpreter for native code and the other targets; hard expectations for diagnostics
- [x] The error corpus pins the full rendered diagnostic (a `//~ expect:` block or a sibling `.stderr` file), so a new file isn't held to the CLI's own output
- [ ] Token and AST expectation files for the examples (`recorded_corpus/`), then `_golden.py` and the stores go
- [ ] Meanwhile: the gates' floors count files compared and print the skip ratio (done with the review for the CLI and checker gates)

## Evidence (first two boxes)

- [[Development/Conventions]] says what holds the toolchain: the interpreter for native code and the other targets, hard expectations for the examples' output and for diagnostics, the recordings only for the files they cover; [[Development/Testing]] and the README say the same.
- `TestPinnedDiagnostics` in `tests/burn/test_error_corpus.py`: every corpus file without a recording (25) has its whole rendered diagnostic in `examples/errors/<name>.stderr`, compared byte for byte with `myla check` (`myla run` for a runtime error) run from the repository; a pin of a file that has a recording, or of none, fails (`test_no_stray_pins`); `MYLA_PIN_DIAGNOSTICS=1` writes a missing one. The 25 were read: each starts with its file's `//~` message.
- `test_examples_compile` compares native output with `test_examples_run.EXPECTED`, the interpreter's hard expectation, instead of the recorded interpreter; the gates that ask the recordings about every example (garbled sources, declaration mutants, `myla test` parity, the server's members) walk `RECORDED_EXAMPLES`, the 32 examples of the retirement ([[MYLA-299]]'s examples are new).
- Open: token and AST expectation files for the examples, so `_golden.py` and the stores can go; the floors of the remaining gates.
