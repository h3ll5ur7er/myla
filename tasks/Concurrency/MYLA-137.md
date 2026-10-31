---
id: MYLA-137
title: The native concurrency runtime
type: feature
status: todo
priority: medium
labels: [concurrency, runtime, codegen, selfhost]
---
D89 (3, 4), after [[MYLA-138]] (D91): the self-hosted backend's runtime, without libc, made multi-threaded under the parity programs of [[MYLA-138]]; the Python backend keeps refusing concurrency (D91).

- [ ] OS threads (`clone`), parking with `futex`, one worker per CPU (`sched_getaffinity`)
- [ ] A heap per thread (arena and free lists), a cell freed on another thread than the one that made it
- [ ] The executor: a run queue (work stealing later), actors' mailboxes and their running flag
- [ ] Deep copies at crossings; `print` writing each line at once
