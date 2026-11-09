---
id: MYLA-403
title: "std.bench: time a closure over repeated runs"
type: feature
status: todo
priority: low
labels: [stdlib, benchmarking]
---
Roadmap row #67 ([[Project/Standard-library-roadmap]]).

- [ ] `bench.run(name, f)` (and a form with a count or a time budget): warm-up runs, then repeated runs of the closure, timed with `std.time`'s monotonic clock
- [ ] A result with the runs, the minimum, the median and the spread, printed as one line (`name  min 1.23 ms  median 1.30 ms  (25 runs)`)
- [ ] A way to keep the closure's result alive, so the work isn't optimised away (a `black_box`-like sink)
- [ ] Cases interpreted and natively; a page below [[Language/Standard-library]] and the roadmap row
