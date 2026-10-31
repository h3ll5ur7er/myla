---
id: MYLA-139
title: Concurrency in the self-hosted interpreter
type: feature
status: todo
priority: medium
labels: [concurrency, interpreter, selfhost]
---
D89 (6), after [[MYLA-138]]: the synchronous tree walker stays for code that can't suspend; what lies on the path to an `await` (an async function's body, and the statements and expressions containing one, which the checker marks) runs on an async evaluator compiled stackless.

- [ ] The checker's marks of what contains an `await`
- [ ] The async evaluator, delegating to the synchronous one below every `await`-free subtree
- [ ] The parity programs of [[MYLA-136]]
