---
id: MYLA-842
title: "static_files checks a file before the server opens it: one swapped for a FIFO in between still blocks a worker"
type: bug
status: in-progress
priority: low
labels: [stdlib, http, fs, security]
---
Found by [[MYLA-795]]. `static_files` (D260) looks at each part of a path with `symlink_metadata`, without opening it, so a FIFO, a device or a link below the root is 404 and never opened. The server opens the file later, when it sends the response (`opened_file` in `lib/std/http.my`), and only then checks it is a regular file (`f.metadata()`). Whoever can write in the served directory can replace the file between the two steps: with a FIFO the `open` blocks the worker until something writes to it, with a link the file opened is the link's target.

std.fs's open can't close the gap: `OpenOptions` has no non-blocking open (`O_NONBLOCK`, which makes the open of a FIFO return at once) and no open that refuses a link (`O_NOFOLLOW`; `FILE_FLAG_OPEN_REPARSE_POINT` on Windows, which std.platform has for its own use). With both, `opened_file` could open first and check the descriptor (`fstat`), as nginx does.

Reproduction (a race, so a loop): serve a directory with `a.txt`; in another process, `while true; do mkfifo f.tmp; mv -f f.tmp a.txt; echo x > r.tmp; mv -f r.tmp a.txt; done` in that directory; `GET /assets/a.txt` in a loop with `MYLA_THREADS=1` stops answering once an open lands on the FIFO.

- [ ] `OpenOptions.nonblocking(on)` and `OpenOptions.no_follow(on)` (Myla's own open bits, D209: every platform module and the interpreter's `__open`)
- [ ] `opened_file` opens with both and checks the open file is a regular file; `file_response` keeps its walk for the directories
- [ ] A burn test that opens a FIFO through `opened_file` and gets 404 at once
