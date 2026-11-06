---
id: MYLA-288
title: Hard expectations instead of the recorded Python answers
type: improvement
status: backlog
priority: high
labels: [tests, oracle]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]). With the Python toolchain retired ([[MYLA-219]]), the recorded answers decayed within five days: every `selfhost/`, `tools/` and `lib/std/` file has changed, so the lexer and parser corpus gates skip all 57 toolchain files, the `myla test` parity gate compares 33 of 92 files, and 15 of the 17 MB of recordings can never be consulted again; 20 new error-corpus files are held to the self-hosted CLI's own output, and the checker gate skips them. The suite is still a real check because 49 of 69 modules compare the interpreter with native code or use hard expectations, but the README and [[Development/Testing]] describe recordings as the oracle.

- [ ] Say what the oracle is in [[Development/Conventions]]: the interpreter for native code and the other targets; hard expectations for diagnostics
- [ ] The error corpus pins the full rendered diagnostic (a `//~ expect:` block or a sibling `.stderr` file), so a new file isn't held to the CLI's own output
- [ ] Token and AST expectation files for the examples (`recorded_corpus/`), then `_golden.py` and the stores go
- [ ] Meanwhile: the gates' floors count files compared and print the skip ratio (done with the review for the CLI and checker gates)
