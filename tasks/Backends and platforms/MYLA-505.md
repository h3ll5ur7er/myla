---
id: MYLA-505
title: "myla build of a file without an entry point builds a library"
type: feature
status: backlog
priority: low
labels: [build, ffi, libraries]
---
The owner's decision on [[MYLA-415]]'s proposal 3 (2026-11-11): for now `myla build` of a file with no `#main` and no `main` is `error: no entry point: define '#main' or a function named 'main'` (exit 1, nothing written). Once Myla has a foreign function interface ([[MYLA-166]]), such a file builds into a library instead: an object or archive whose `pub` functions other languages, or other Myla programs, can link against.

- [ ] Decide the library's form per target (a static archive, a shared object, a wasm module with exports) and its calling convention at the boundary, with [[MYLA-166]]
- [ ] `myla build` of a file without an entry point writes it; `myla run` keeps saying there is no entry point
