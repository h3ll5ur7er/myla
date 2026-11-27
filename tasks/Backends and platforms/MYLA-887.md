---
id: MYLA-887
title: "Linux: every worker maps a 16 MiB chunk of address space to read the clock"
type: bug
status: todo
priority: low
labels: [platforms, linux, memory]
---
Found by [[MYLA-861]] (gdb on `test_windows.HELPER sleep 500`, `MYLA_THREADS=16`, natively, 2026-11-18 at `3add216`): std.platform's `clock_ns` (and `wall_ns`, `sleep_ns`) on x86-64 and aarch64 Linux takes its `timespec` from the heap (`__alloc(16)`), and every worker reads the clock while a timer waits (`exec_run`'s turn → `timers_fire`), so each maps a chunk of its own: 4 to 14 mappings of 16 MiB, 4 KB of each resident. Linux overcommits, so it costs address space and a page each, not commit; Windows' did the same until MYLA-861.

- [ ] The clock read into the thread's own words (as Windows' `__win_memory_info`), not a cell: an idle worker maps no chunk (in the one Linux module the Linux platform lane makes)
