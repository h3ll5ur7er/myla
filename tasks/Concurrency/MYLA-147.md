---
id: MYLA-147
title: Cancellation of child tasks
type: feature
status: todo
priority: medium
labels: [concurrency, language, runtime, interpreter, selfhost, design]
---
From the concurrency stress tests ([[MYLA-144]], test 8, "failure while sibling tasks are running"), the user's decision: add cancellation. A child failed while its sibling looped forever: both interpreters waited for the sibling at the scope's end and hung; native code ended the program at once, without waiting for the scope's other children (so a failing task's children could outlive their scope). With cancellation a failing scope stops its other children, then waits for them.

- [ ] The design (a decision): what stops a cancelled task and where, whether programs can cancel and ask for it, what a cancelled child's `await` gives
- [ ] The Python interpreter, the self-hosted interpreter, native code; test 8 ends with the failure everywhere, its children stopped
