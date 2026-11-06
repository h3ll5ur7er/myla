---
id: MYLA-287
title: A write error on stdout other than a broken pipe is invisible
type: improvement
status: backlog
priority: medium
labels: [stdlib, io, decision]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]). D146 gave `std.io.write` a `Result` and left `print`, `println` and `eprintln` without one, ending the program quietly on a broken pipe (`| head -0`: status 141, correct). Any other failure of a write to stdout is lost: `prog > /dev/full` exits 0 and prints nothing, where every Unix tool reports `No space left on device` on stderr and exits 1.

- [ ] A decision: `print` and the others end the program with `runtime error: write failed: <cause>` (exit 1) on any error but EPIPE
- [ ] Both runners, every target; a test with `/dev/full`
