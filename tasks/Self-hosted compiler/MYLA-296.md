---
id: MYLA-296
title: The interpreter's memory per sleeping task
type: improvement
status: backlog
priority: low
labels: [interpreter, concurrency, performance]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]). 10,000 tasks sleeping at once take 2.5 s and 1.18 GB in the interpreter (about 115 KB per task) against 127 ms and 27 MB natively. Natively, with many workers, every loop top takes `__timer_lock` in `timers_fire` while any timer exists, a contention cost not yet measured.

- [ ] Find what a suspended task keeps in the interpreter (its evaluator's frames? copies of the environment?) and shrink it; a test with 10,000 sleepers under a memory bound
- [ ] Measure `timers_fire` on 16 workers with many timers; a per-worker timer wheel or one timer owner if it shows
