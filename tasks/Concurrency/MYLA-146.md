---
id: MYLA-146
title: A diagnostic for actor state changed across an await
type: feature
status: todo
priority: medium
labels: [concurrency, checker, selfhost, language]
---
From the concurrency stress tests ([[MYLA-144]], test 6, "reentrancy across an await"), the user's decision: keep reentrant actors (D89 (2)) and add a compiler diagnostic. An actor method that reads a field before an `await` and writes it after, without reading it again, acts on a value another call may have changed meanwhile: `if self.stock == 0 { … }; await pay.charge(); self.stock = self.stock - 1` sold the last item twice (stock -1, every time on one worker).

- [ ] The rule and how it is silenced (a decision)
- [ ] Both checkers, the same diagnostic; error corpus cases, and the stress test's idioms accepted
