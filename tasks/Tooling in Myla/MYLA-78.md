---
id: MYLA-78
title: Read from stdin in the standard library
type: feature
status: review
priority: medium
labels: [stdlib, runtime, selfhost]
---
Part of the "everything in Myla" direction ([[Project/Roadmap]]); a language server ([[MYLA-80]]) and a REPL ([[MYLA-82]]) need it. `std.io` can only write today.

- [x] A `read` primitive (the `read` syscall on a file descriptor, blocking) in the interpreter, both native runtimes and the self-hosted interpreter
- [x] `std.io`: read a line, read exactly n bytes (for `Content-Length` framing), read to the end; EOF and errors as `Result`/`Option`
- [x] Parity tests that pipe input into each implementation

## How

Decision D64 on [[Project/Decisions]]; the API is on [[Language/Standard-library]].

- One primitive, `__read(fd, n) -> str`: one `read(2)` of at most n bytes, retried on EINTR, `""` at the end of the input, errno through the existing `__io_errno()`. It's in both checkers (same messages), the Python interpreter (`os.read`, or a `stdin=` byte stream for tests), the self-hosted interpreter (which calls `__read` itself), and both native backends (a 40-line helper that reads into a fresh str cell of capacity n). The Python backend's errno global now has its own flag, so `__io_errno` no longer pulls in the file-reading helper.
- `std.io` gained a buffered `Reader` written in Myla: `stdin()`, `reader(fd)`, `read_line` (without `"\n"`, a `"\r"` kept, a last line without `"\n"` counted), `read_exact(n)` (None if the input ends first) and `read_to_end`. Errors are `std.fs.IoError` (`from_errno` is now public). The buffer lives in the struct, since Myla has no globals; since there are no references, protocol code keeps the reader in a struct field and reads in `var self` methods (the `FRAMED` test shows this for Content-Length framing).
- The interpreter flushes stdout and stderr before each read: Python buffers a piped stdout, and a request/response program (the language server) would deadlock. The native and self-hosted implementations write unbuffered.
- Chunks are 4 KB (`read_exact` asks for the whole remaining body at once).
- Follow-up [[MYLA-85]]: interpreted code copies strings byte by byte, so the interpreters read slowly; a builtin for byte ranges would fix that.

## Evidence

- `tests/unit/test_stdio.py`: 17 new tests (the primitive's type rules and behaviour, EBADF; lines, a last line without newline, no input, CRLF, lines longer than a chunk, "ö" split across chunks, `read_to_end` after a line and again at the end, framed messages, a cut-off message, `read_exact` of zero or a negative count, `IoError.Other(9)` from a bad fd). They were red before the change (22 errors, including the old tests, from the new `stdin=` parameter) and run in 0.8 s.
- `tests/burn/test_stdin.py`: 7 tests, each run in all four implementations through a real pipe, with identical output. The interactive exchange fails for the Python interpreter (`b'' != b'got first\n'`) when the flush is removed; it had passed by accident before, because this environment sets `PYTHONUNBUFFERED`, so the test now runs without it.
- The checker gate compares the new `__read` messages: the snippet corpus was re-harvested (3 `__read` snippets, plus 21 older ones the corpus had been missing; all pass).
- Throughput, counting the lines of 15 MB (250,000 lines): 0.16 s native from the Python backend, 0.30 s from the self-hosted one. 1 MB through the interpreters: 31 s (Python), 10 s (self-hosted), see [[MYLA-85]].
- Full run: 483 unit, 4 integration and 408 burn tests pass; the bootstrap reaches its fixed point at 7,597,725 bytes (7,536,102 before).
