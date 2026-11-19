---
id: MYLA-842
title: "static_files checks a file before the server opens it: one swapped for a FIFO in between still blocks a worker"
type: bug
status: review
priority: low
labels: [stdlib, http, fs, security]
---
Found by [[MYLA-795]]. `static_files` (D260) looks at each part of a path with `symlink_metadata`, without opening it, so a FIFO, a device or a link below the root is 404 and never opened. The server opens the file later, when it sends the response (`opened_file` in `lib/std/http.my`), and only then checks it is a regular file (`f.metadata()`). Whoever can write in the served directory can replace the file between the two steps: with a FIFO the `open` blocks the worker until something writes to it, with a link the file opened is the link's target.

std.fs's open can't close the gap: `OpenOptions` has no non-blocking open (`O_NONBLOCK`, which makes the open of a FIFO return at once) and no open that refuses a link (`O_NOFOLLOW`; `FILE_FLAG_OPEN_REPARSE_POINT` on Windows, which std.platform has for its own use). With both, `opened_file` could open first and check the descriptor (`fstat`), as nginx does.

Reproduction (a race, so a loop): serve a directory with `a.txt`; in another process, `while true; do mkfifo f.tmp; mv -f f.tmp a.txt; echo x > r.tmp; mv -f r.tmp a.txt; done` in that directory; `GET /assets/a.txt` in a loop with `MYLA_THREADS=1` stops answering once an open lands on the FIFO.

- [x] `OpenOptions.nonblocking(on)` and `OpenOptions.no_follow(on)` (Myla's own open bits, D209: every platform module and the interpreter's `__open`)
- [x] `opened_file` opens with both and checks the open file is a regular file; `file_response` keeps its walk for the directories
- [x] A burn test that opens a FIFO through `opened_file` and gets 404 at once

## What changed

- **`OpenOptions.nonblocking(on)` and `no_follow(on)`** ([[lib/std/fs.my]]), Myla's open bits 64 and 128 (D209), which [[lib/std/rt.my]] `open` takes now (another bit is still INVALID_INPUT): on Linux O_NONBLOCK and O_NOFOLLOW (`linux_open_flags`; O_NOFOLLOW's number is the architecture's, 0x20000 on x86-64 and 0x8000 on aarch64, in std.linux_calls); on WASI FDFLAGS_NONBLOCK and a lookup without SYMLINK_FOLLOW (`open_file`; the shim's `path_open` reads both, `node_fs.mjs` opens with O_NOFOLLOW and O_NONBLOCK); on Windows not waiting changes nothing (its file system has no FIFOs) and with no link at the end the reparse point is opened itself (FILE_FLAG_OPEN_REPARSE_POINT) and refused when it is a link, so a link at the end is ELOOP's `Other(40)` on every target. The interpreter's `__open` is the host's std.rt.
- **`opened_file`** ([[lib/std/http.my]]) opens a response's file with both and keeps its check of what it opened (`f.metadata()`, an fstat of the descriptor): a FIFO swapped in after `file_response` looked opens at once and is 404, a link swapped in is 404. `file_response` hands the server a link's target (MYLA-841), so the path's end is no link; it keeps its walk for the directories, as the task says.

## Proposals

Accepted by the owner on 2026-11-19 as D309.

- **A link at the end is an error on every target** (built), Windows' open of the reparse point itself turned into ELOOP's `Other(40)`. The alternative, Windows' own behaviour (the link opened, its metadata `Symlink`), would make the same program see a file on one target and an error on another; std.http refuses either.
- No decision row needed: D260 already says no FIFOs and no links out of the root; this keeps it at the open.

## Evidence

- **Before**: `test_http.TimeLimits.test_what_the_server_opens_is_what_it_checks` with the old `fs.open` in `opened_file`: both forms `TimeoutError: timed out` (the FIFO's request, a one-worker server, `MYLA_THREADS=1`, 3 s).
- **After**: the FIFO and the link (through a handler's `Response.file`) are 404 within the test's 2 s bound and a regular file is 200, interpreted and built. `test_fs.DirectoryParity.test_opens_that_neither_wait_nor_follow` (a FIFO opened at once, a link at the end `Other(40)`, one before it followed). std.fs's cases of the two options and std.platform's case of the Linux bits; `test_platform_primitives`' invalid bit is 256 now (64 is a bit of its own).
- **Targets**: as MYLA-841's (aarch64 and wasm32 run the fs test; under Wine it is excused with the link tests, `_WINE_LINKS`). Windows' refusal of a link at the end is in the Windows runner's `files/links` case (`no_follow` of a symbolic link: `Other(40)`), which only CI's `windows-latest` job runs.
