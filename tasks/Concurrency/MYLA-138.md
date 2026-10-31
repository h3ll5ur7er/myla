---
id: MYLA-138
title: The stackless lowering of async functions
type: feature
status: todo
priority: medium
labels: [concurrency, ir, codegen, selfhost, design]
---
D89 (5), after [[MYLA-137]]: `async` functions as state machines with heap frames, in both native backends.

- [ ] A decision under D85: how the IR holds an async function's frame (slots as members of a heap object, or a new home for slots), its suspension points and resumption, and its calling convention
- [ ] The self-hosted backend, then the Python backend
- [ ] Parity programs and deep task trees in both
