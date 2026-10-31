---
id: MYLA-148
title: A child task awaiting its sibling
type: feature
status: todo
priority: medium
labels: [concurrency, lowering, runtime, selfhost]
---
From the concurrency stress tests ([[MYLA-144]], test 5), the user's decision: support it. An `async let` initializer may await an earlier sibling (`async let b = use(await a)`, the checker allows it and both interpreters run it), but native code printed garbage: it runs the initializer as an async lambda, which captured the sibling's task slot as a number. A sibling is always declared earlier, so waiting between siblings can't form a cycle.

- [ ] Native code: a child's lambda takes the sibling's task along, awaits it (a task with more than one frame waiting) and reads its result as a copy of its own (the parent may read it at the same time)
- [ ] The stress test on every implementation and on 1 to 16 workers
