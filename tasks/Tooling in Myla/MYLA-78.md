---
id: MYLA-78
title: Read from stdin in the standard library
type: feature
status: backlog
priority: medium
labels: [stdlib, runtime, selfhost]
---
Part of the "everything in Myla" direction ([[Project/Roadmap]]); a language server ([[MYLA-80]]) and a REPL ([[MYLA-82]]) need it. `std.io` can only write today.

- [ ] A `read` primitive (the `read` syscall on a file descriptor, blocking) in the interpreter, both native runtimes and the self-hosted interpreter
- [ ] `std.io`: read a line, read exactly n bytes (for `Content-Length` framing), read to the end; EOF and errors as `Result`/`Option`
- [ ] Parity tests that pipe input into each implementation
