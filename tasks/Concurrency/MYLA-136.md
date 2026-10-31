---
id: MYLA-136
title: Concurrency in the Python interpreter
type: feature
status: todo
priority: medium
labels: [concurrency, interpreter]
---
D89 (6), after [[MYLA-135]]: the semantics, with each task on a Python thread, deep copies at every crossing, reentrant actors (a mailbox, one message at a time), structured scopes waiting for their children.

- [ ] Tasks, `await`, `async let`, task groups
- [ ] Actors: handles, mailboxes, reentrancy
- [ ] Deep copies at crossings
- [ ] Examples and parity programs whose output doesn't depend on the order of tasks running at once
