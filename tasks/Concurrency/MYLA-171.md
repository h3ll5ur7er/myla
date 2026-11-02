---
id: MYLA-171
title: The reentrancy warning (D95) is bypassed through self methods
type: improvement
status: review
priority: medium
labels: [concurrency, checker, warnings]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). The D95 walk sees a change only as a syntactic `self.f = …` or `push(self.f, …)`, and a check only as a condition reading `self.f`. `if self.stock == 0 { … }; await audit.record(); self.take()` (the change in a `var self` method) and `if !self.has_stock() { … }; await …; self.stock = self.stock - 1` (the check in a method) get no warning from either checker, and the stock goes to -1 natively at 4 workers and more: the shape test 6 of the stress plan was written for.

- [x] A call of a `var self` method on `self` counts as a change of every field it changes (transitively); a call of a `self` method counts as examining every field its body examines
- [x] Both checkers agree (one checker now, [[MYLA-219]]); the two programs above warn, the two ways out (checking again after the `await`, changing before it) stay quiet
- [ ] Consider a non-reentrant method kind (no `await` inside), which is what most invariants want (a decision: left for the owner)

Part of the next concurrency slice (D107, [[MYLA-212]]).

## Evidence

- `Checker.self_effects` ([[selfhost/checker.my]]) gives each synchronous method of the actor the fields it changes and the fields it examines, through the methods of `self` it calls; the direct effects come from `Effects`, the transitive ones from a closure over the calls. The D95 walk uses them: `Reads` counts a call `self.m(…)` as reading what `m` examines, so it is a check in a condition and taints a local; `Reentrancy.call_changes` counts every such call in a statement as a change of what `m` changes. The warning points at the call.
- Tests first: `test_warnings_through_self_methods` in `tests/burn/test_selfhost_checker.py`, five programs:
  - The task's two shapes: the change in a `var self` method (`self.take()` after the `await`) and the check in a method (`if !self.has_stock()` before it).
  - A change two calls deep (`self.sell()`, which calls `self.take()`).
  - The two ways out: checking again with `self.has_stock()` after the `await`, and `self.take()` before it.

  Before the change the three warning cases got no warning; now they get the expected warning at the call or assignment, and the two ways out stay quiet.
- No example and no stress program gains a warning. Checking the whole compiler takes as long as before (0.54 s before, 0.47 s after, best of 5).
- **Found on the way.** `test_lsp.TestResolutionCorpus` replayed the Python lexer's recorded identifiers. Every file changed since the recording was skipped, so the corpus shrank with each change to `selfhost/`, and this change took it under its floor of 30,000 resolved names (18,811). The test now tokenizes with the self-hosted lexer (`lex_main`, byte-for-byte parity with the Python one when it existed). It has no skips again, and the recording is removed. The burn suite's skips went from 40 to 17.
- The burn suite passes (841 tests), and the bootstrap reaches its fixed point with the new seed.

