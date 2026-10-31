---
id: MYLA-169
title: An awaited var self struct method on an actor field behaves three ways
type: bug
status: todo
priority: medium
labels: [concurrency, checker, parity]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). An actor field holding a struct whose `var self` method is `async`, called with `await self.c.bump(p)` while another task changes `self.c.n`, is accepted by both checkers without a D95 warning, and the three runners disagree: the Python interpreter prints 2000, the self-hosted interpreter 1000 (the method's copy of `c` is written back over the other task's changes), and the self-hosted backend fails with `runtime error: internal error: Shop.sell can't be lowered to the IR: an awaited 'var self' method on that receiver`. [[MYLA-142]] left actors out of the write-back on purpose, but as an internal error, not a checker error.

- [ ] Decide: reject an awaited `var self` struct method on a place inside an actor (the simple rule), or define it (the write-back through the actor, as [[MYLA-142]] does for lists)
- [ ] Both checkers give the same error (error-corpus file), or all three runners print the same
- [ ] A stress program (`t14_struct_method_in_actor.my`) or a parity program
