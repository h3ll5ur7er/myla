---
id: MYLA-171
title: The reentrancy warning (D95) is bypassed through self methods
type: improvement
status: backlog
priority: medium
labels: [concurrency, checker, warnings]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). The D95 walk sees a change only as a syntactic `self.f = …` or `push(self.f, …)`, and a check only as a condition reading `self.f`. `if self.stock == 0 { … }; await audit.record(); self.take()` (the change in a `var self` method) and `if !self.has_stock() { … }; await …; self.stock = self.stock - 1` (the check in a method) get no warning from either checker, and the stock goes to -1 natively at 4 workers and more: the shape test 6 of the stress plan was written for.

- [ ] A call of a `var self` method on `self` counts as a change of every field it changes (transitively); a call of a `self` method counts as examining every field its body examines
- [ ] Both checkers agree; the two programs above warn, the two ways out (checking again after the `await`, changing before it) stay quiet
- [ ] Consider a non-reentrant method kind (no `await` inside), which is what most invariants want (a decision)
