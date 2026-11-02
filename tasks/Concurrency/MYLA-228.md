---
id: MYLA-228
title: "A `yield` builtin"
type: feature
status: todo
priority: low
labels: [concurrency]
---
D107 ([[MYLA-212]]): `await task.yield()` (name to settle) is a suspension point that lets other ready tasks run, and where a stopped task notices the end of the program (D97). Also a cheap fix for a sibling that loops without suspending (review finding B11).

- [ ] Name and place (`std.task`), in the checker, the interpreter(s) and the native runtime
- [ ] A test that a spinning loop with `yield` lets a failing sibling end the program at once; [[Language/Concurrency]]
