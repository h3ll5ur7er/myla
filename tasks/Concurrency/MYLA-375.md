---
id: MYLA-375
title: "Interpreter: awaiting input on no descriptor waits forever"
type: bug
status: done
priority: medium
labels: [interpreter, concurrency, parity]
---
Found by wave 3's MYLA-340 lane. `await __wait_readable(-1)` returned at once natively and never under `myla run`. An async read through `Buffered` of a closed `ChildStdout`, or of `std.io`'s `fd_stream(-1)`, hung in the interpreter instead of giving its error.

Natively, `wait_fds` ([[lib/std/rt.my]]) counts a descriptor the poller can't watch as ready. The interpreter asked `poll(2)`, which ignores a negative descriptor (no event, ever), so the task stayed parked.

- [x] `__wait_readable` and `__wait_either` in [[selfhost/interp.my]] treat a negative first descriptor as ready (and `__wait_either`'s negative second as "only the first", as natively)
- [x] A parity program
- [x] The same on every target: wasm32's poller watched `-1` and never woke (PR #47's wasm32 suite hung on the parity program); `wait_fds` in [[lib/std/rt.my]] takes a negative descriptor as ready before the poller

## Evidence

- Test first: `wait_with_no_descriptor` in `test_compiler_parity` printed `before` and was killed after 10 s under `myla run`, and printed `before after 2` natively. Now both print the same.
- `test_compiler_parity`, `test_process`, `test_stdio`, `test_time`, `test_task_yield`, `test_selfhost_interp`: OK.
- `scripts/bootstrap.sh`: byte-identical fixed point.
- The wasm32 burn suite of PR #47 hung on `wait_with_no_descriptor` (cancelled after 30 min). Reproduced: the program built for wasm32 printed `before` and hung under Node. After `wait_fds`' check, it prints `before after 2` on x86-64, aarch64 (qemu) and wasm32 (Node). `scripts/test-target.py wasm32-wasi` and `aarch64-linux`: 18 of 18 suites each. `test_compiler_parity`, `test_process`, `test_stdio`, `test_time`, `test_task_yield`, `test_native_runtime`, `test_std_modules`: 237 tests, OK.

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]].
