---
id: MYLA-287
title: A write error on stdout other than a broken pipe is invisible
type: improvement
status: review
priority: medium
labels: [stdlib, io, decision]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]). D146 gave `std.io.write` a `Result` and left `print`, `println` and `eprintln` without one, ending the program quietly on a broken pipe (`| head -0`: status 141, correct). Any other failure of a write to stdout is lost: `prog > /dev/full` exits 0 and prints nothing, where every Unix tool reports `No space left on device` on stderr and exits 1.

- [x] A decision: `print` and the others end the program with `runtime error: write failed: <cause>` (exit 1) on any error but EPIPE
- [x] Both runners, every target; a test with `/dev/full`

## Done (2026-11-07)

- D153. `std.rt.print_str` (native `print`), `std.io`'s `println`, `eprint` and `eprintln` (`put`), and the interpreter's `print` end the program with `runtime error: write failed: <cause>` and status 1 on a write error other than a closed pipe, which keeps D146's quiet end; `std.io.write` still returns the error. The cause is named for ENOSPC, EIO, EBADF, EFBIG and EDQUOT, `errno N` otherwise.
- `test_stdio.BrokenPipe.test_a_write_to_a_full_disk_ends_with_an_error`: `print` and `println` to `/dev/full` give the message and status 1, and a program whose stderr is `/dev/full` ends with status 1 (its message can't be written either), interpreted and natively; both exited 0 silently before.
