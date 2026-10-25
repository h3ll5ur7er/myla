---
id: MYLA-57
title: playground.my is a scratch file pinned by the test gates
type: chore
status: backlog
priority: low
labels: [examples, tests]
---
`examples/playground.my` has no header comment, a mis-indented arm (line 41) and an unused `resolve(var self)`, yet `test_examples_run`, `test_examples_compile` and `test_examples_tests` pin it like a feature example.

- [ ] Turn it into a proper example of what it exercises, fold it into `regressions.my`, or move it out of `examples/`
