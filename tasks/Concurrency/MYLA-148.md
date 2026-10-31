---
id: MYLA-148
title: A child task awaiting its sibling
type: feature
status: done
priority: medium
labels: [concurrency, lowering, runtime, selfhost]
---
From the concurrency stress tests ([[MYLA-144]], test 5), the user's decision: support it. An `async let` initializer may await an earlier sibling (`async let b = use(await a)`, the checker allows it and both interpreters run it), but native code printed garbage: it runs the initializer as an async lambda, which captured the sibling's task slot as a number. A sibling is always declared earlier, so waiting between siblings can't form a cycle.

- [x] Native code: a child's lambda takes the sibling's task along, awaits it (a task with more than one frame waiting) and reads its result as a copy of its own (the parent may read it at the same time)
- [x] The stress test on every implementation and on 1 to 16 workers

## Design

- **The capture.** The child's lambda captures the sibling's task slot (its first frame) like any variable; a capture that is a task is marked (`Cap.task`), and the child registers it as a foreign task: awaited there, never joined (the parent joins its children latest first, so the sibling outlives every child that awaits it).
- **Waiting.** A task's `task` word holds the first of the frames waiting for it, each linked to the next through word 32 (a waiting frame is in no actor's queue); `myla___wait` pushes onto that list with `lock cmpxchg`, and the task's end (or failure) swaps its state in and queues every frame of the list (`__wake_waiters`).
- **The result.** The parent may read the result at the same moment, so a sibling can't take a reference of its own (counts are plain, D92): a new IR instruction `clone T [%p]` makes the word-for-word copy a deep copy of its own, only reading the original (`__dclonew_<T>`, `__dclone_<cell>`, and for a function value's env the routine two words before its drop function). The original can't change meanwhile: the sibling has ended and the parent writes through copy-on-write.

## Evidence

- Before: `async let b = use(await a)` printed 2 on both interpreters and natively numbers such as 2097297, 738197649, 916455569 (the sibling's frame pointer read as a value).
- After: `t05_child_awaits_sibling` prints 2 everywhere; `t05_siblings_share_a_result` (3,000 rounds of a child returning a list of structs holding strings, read by three siblings, one of which changes its copy, and by the parent) prints 60780 on both interpreters and natively on 1, 4 and 16 workers, at an 11 MB peak (`tests/burn/test_concurrency_stress.py`).
- Unit 621, integration 2, burn 808 (5 skipped) and the extension's 54 tests pass; the bootstrap reaches its byte-identical fixed point (6,107,397 bytes).
