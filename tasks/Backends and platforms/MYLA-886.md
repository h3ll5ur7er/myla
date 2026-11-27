---
id: MYLA-886
title: "Windows: the polling worker still allocates while the program waits (the poller's lists and words)"
type: bug
status: todo
priority: low
labels: [platforms, windows, memory]
---
Found by [[MYLA-861]]. A program that only waits (`HELPER sleep 3000` on 16 workers) no longer commits heap for every worker that reads the clock (`clock_ns` uses the thread's `__win_memory_info` now), but the worker that polls still allocates on each wait: std.rt's `poll_events` builds a list of the frames woken, and `std.platform`'s `poller_wait` takes its count word from the heap (`__alloc(8)`) and passes its arguments to `win_call` as a list. Since MYLA-861 that commits a 256 KiB step of that worker's arena, not a 16 MiB chunk, but which worker polls changes from wait to wait, so a long wait commits a step on most of them.

To reproduce: build `test_windows.HELPER` for x86_64-windows, run `sleep 3000` under Wine with `MYLA_THREADS=16`, and count the `rw-p` mappings of 256 KiB in `/proc/<pid>/maps` (or break on `std$rt$chunk_reserved` natively with a copy whose `HEAP_COMMIT` is set).

- [ ] `poller_wait` and the poll's path take no cell of the heap (the thread's own words, a list kept by the poller)
- [ ] A count of the chunks an idle 16-worker program reserves, before and after
