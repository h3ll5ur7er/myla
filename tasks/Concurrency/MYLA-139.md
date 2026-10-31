---
id: MYLA-139
title: Concurrency in the self-hosted interpreter
type: feature
status: in-progress
priority: medium
labels: [concurrency, interpreter, selfhost]
---
D89 (6), after [[MYLA-138]]: the synchronous tree walker stays for code that can't suspend; what lies on the path to an `await` (an async function's body, and the statements and expressions containing one, which the checker marks) runs on an async evaluator compiled stackless.

- [x] Stage 1, one task at a time: a child task runs to its end when its `async let` starts it, on copies of the variables, its failure (a runtime error or an `exit`) held for `await` or the end of its scope; actors are `VActor` handles to states only their methods change; `std.task` runs as written
- [x] The parity programs of [[MYLA-136]] (`CONCURRENCY_PROGRAMS` in `tests/burn/test_selfhost_interp.py`, and `examples/concurrency.my` in the corpus)
- [ ] Stage 2, interleaving at suspension points: the checker's marks of what contains an `await`
- [ ] Stage 2: the async evaluator, delegating to the synchronous one below every `await`-free subtree, and a scheduler switching tasks at an `await`

Stage 1 runs every program whose tasks needn't make progress side by side: what it prints is one of the outputs a parallel run may give. A child that waits for its parent to change an actor (`while await flag.get() == false {}` started before the parent sets it) never ends one task at a time; stage 2 is for those.

## Found on the way

- A `?` in an `async let`'s initializer made the Python interpreter's parent return from its `await` with the child's value; it is a checker error now in both checkers ("'?' can't stand in an 'async let'…", `examples/errors/type_try_in_async_let.my`).
