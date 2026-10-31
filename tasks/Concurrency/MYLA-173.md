---
id: MYLA-173
title: "Concurrency page: print atomicity, FIFO wording, the cost of deep copies, unstated rules"
type: chore
status: todo
priority: low
labels: [concurrency, docs]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). [[Language/Concurrency]] states two things the runtime doesn't do and leaves out three it does:

- "Each `print` writes its line whole": only up to `PIPE_BUF` (4 KiB). Four tasks printing 6,000-byte lines interleave 47 of 800 lines on four workers.
- "Actors queue their callers first in, first out": a frame finding the actor busy with no frame queued spins for it ([[MYLA-150]]), so two spinners race for the actor when it comes free.
- Not said: a value crossing into a task or an actor is copied in full, O(len), and only in a program that has a task: `await s.take(xs)` with a 100k-element list costs about 1.45 ms per call, and the same program without an `async let` runs 200 times faster. Advice: pass what the callee needs, or keep large state in the actor.
- Not said: a failure can't be caught, so a program that must survive one bad input makes its children return `Result`.
- Enforced but stated only elsewhere: `?` can't stand in an `async let`; `MYLA_THREADS` is clamped to 32; `task.cancel` used as a value is an error (D97 (4)).

- [ ] The five points above on the page, and the banner's "in progress" replaced by the current state
