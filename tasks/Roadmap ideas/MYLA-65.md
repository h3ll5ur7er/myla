---
id: MYLA-65
title: Better error messages
type: improvement
status: backlog
priority: medium
labels: [diagnostics, tooling]
---
Diagnostics that help, in both the Python and the self-hosted toolchain.

- [x] The file each error comes from ([[MYLA-10]]; the self-hosted side: [[MYLA-28]])
- [ ] Spans instead of single positions, so the caret underlines the whole expression
- [ ] Notes and hints: where a binding was declared immutable, the conflicting declaration, the expected type's origin, "did you mean …" for misspelled names and fields
- [ ] More than one error per run: recover after a parse error at the next statement or declaration, keep checking other functions after a type error
- [x] Runtime errors from native binaries with a message ([[MYLA-17]]), ideally with the source position (see [[MYLA-66]]): both backends print `runtime error: <message>` and the interpreter's `  --> file:line:col`, in every build, from a static position record passed to the trap (D75); the error corpus, `tests/burn/test_native_runtime.py` and the self-hosted codegen gate check it
- [ ] The error corpus checks the new notes, so messages can't regress silently
