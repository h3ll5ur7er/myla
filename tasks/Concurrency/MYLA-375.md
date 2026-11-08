---
id: MYLA-375
title: "Interpreter: awaiting input on no descriptor waits forever"
type: bug
status: review
priority: medium
labels: [interpreter, concurrency, parity]
---
Found by wave 3's MYLA-340 lane. `await __wait_readable(-1)` returned at once natively and never under `myla run`. An async read through `Buffered` of a closed `ChildStdout`, or of `std.io`'s `fd_stream(-1)`, hung in the interpreter instead of giving its error.

Natively, `wait_fds` ([[lib/std/rt.my]]) counts a descriptor the poller can't watch as ready. The interpreter asked `poll(2)`, which ignores a negative descriptor (no event, ever), so the task stayed parked.

- [x] `__wait_readable` and `__wait_either` in [[selfhost/interp.my]] treat a negative first descriptor as ready (and `__wait_either`'s negative second as "only the first", as natively)
- [x] A parity program

## Evidence

- Test first: `wait_with_no_descriptor` in `test_compiler_parity` printed `before` and was killed after 10 s under `myla run`, and printed `before after 2` natively. Now both print the same.
- `test_compiler_parity`, `test_process`, `test_stdio`, `test_time`, `test_task_yield`, `test_selfhost_interp`: OK.
- `scripts/bootstrap.sh`: byte-identical fixed point.
