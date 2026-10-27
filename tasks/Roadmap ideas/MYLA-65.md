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
- [ ] Runtime errors from native binaries with a message ([[MYLA-17]]), ideally with the source position (see [[MYLA-66]])
- [ ] The error corpus checks the new notes, so messages can't regress silently
