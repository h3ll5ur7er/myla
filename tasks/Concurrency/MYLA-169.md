---
id: MYLA-169
title: An awaited var self struct method on an actor field behaves three ways
type: bug
status: review
priority: medium
labels: [concurrency, checker, parity]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). An actor field holding a struct whose `var self` method is `async`, called with `await self.c.bump(p)` while another task changes `self.c.n`, is accepted by both checkers without a D95 warning, and the three runners disagree: the Python interpreter prints 2000, the self-hosted interpreter 1000 (the method's copy of `c` is written back over the other task's changes), and the self-hosted backend fails with `runtime error: internal error: Shop.sell can't be lowered to the IR: an awaited 'var self' method on that receiver`. [[MYLA-142]] left actors out of the write-back on purpose, but as an internal error, not a checker error.

- [x] Decide: reject an awaited `var self` struct method on a place inside an actor (the simple rule), or define it (the write-back through the actor, as [[MYLA-142]] does for lists)
- [x] Both checkers give the same error (error-corpus file), or all three runners print the same
- [x] A stress program (`t14_struct_method_in_actor.my`) or a parity program

## Evidence

- The owner's decision: the same solution as for list elements (D99). The Python interpreter now gives such a method a copy and writes its final `self` back to the place (indices computed once); the self-hosted interpreter did already; the lowering accepts a place in the actor's state (`actor_place`), passes the method a deep copy made while the actor is held (the method runs off it, D92), and writes the result back once it holds the actor again.
- `t14_struct_method_in_actor`: calls one after the other keep every change (`101000`); a change made through the actor while a call waits is replaced by its write-back (`1 1 1`). Before, the Python interpreter printed `101 101 1` (it changed the field in place) and native code failed with an internal error; now all four print the same, natively on 1 and 4 workers (3 runs each) and in the stress suite on 1 to 16 workers.
- The first full run found the Python interpreter writing back an actor's own `var self` method called on a handle (`t04_transfers_both_ways` lost a transfer): the write-back is for a field or element in an actor only, fixed in 1ddece4.
- Unit 622, integration 2, burn 828 (5 skipped) and the extension's 54 tests pass on commit 1ddece4; the bootstrap reaches its byte-identical fixed point (6,185,088 bytes).
