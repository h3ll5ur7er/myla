---
id: MYLA-351
title: "std.task: channels, pools and timeouts"
type: feature
status: backlog
priority: low
labels: [stdlib, concurrency, wave-4]
---
Wave 4 of [[Project/Standard-library-roadmap]], roadmap #66. Built on actors and the reactor ([[Language/Concurrency]]).

- **Owns:** `lib/std/task.my` (additions), `docs/Language/Standard-library/Task.md`
- **Needs:** nothing; it can start as soon as its wave does
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] `Channel<T>` between tasks, bounded and unbounded
- [ ] A worker pool
- [ ] A timeout around any await and waiting for the first of several
- [ ] The concurrency stress tests extended to them ([[Development/Concurrency-stress-tests]])
- [ ] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [ ] Its page below [[Language/Standard-library]], with a doc block that runs
