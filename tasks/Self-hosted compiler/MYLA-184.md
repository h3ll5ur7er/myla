---
id: MYLA-184
title: "The #test convention in selfhost/: 1,164 of 1,259 value-returning functions have none"
type: chore
status: todo
priority: low
labels: [selfhost, tests, docs]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). [[Development/Conventions]], the `myla` skill and [[Architecture/Self-hosted-compiler]] say every value-returning function in `selfhost/` carries `#test` cases; `tests/burn/test_examples_tests.py` enforces it only for `examples/`. Counted on 2026-10-31: lexer 21 of 21 untested, parser 103 of 108, checker 296 of 299, lower 85 of 85, interp 180 of 183, codegen 182 of 194. The tests that exist are meaningful.


Also a decision question from the review's §11.10, tracked with the others in `Review decisions/` ([[MYLA-201]] to [[MYLA-217]]).

## Options

- **A. Enforce it for `selfhost/`**: a burn test like the one for `examples/`, and some 1,160 functions to cover, many of which need a whole AST or IR to be called.
- **B. Restate it**: "every function in `examples/` and the standard library; in the self-hosted compiler, functions that can be tested in isolation", with the three places that state it agreeing.
- **C. B plus a ratchet**: a burn test that counts the `selfhost/` functions with `#test` cases and fails when the count drops, so new pure helpers come with cases.

## Recommendation

**C.** The convention becomes true as written, and coverage can only grow; starting with the pure helpers of `ir.my`, `lower.my` and `util.my`.

## Decision

**D109 (2026-11-01).** The owner: "soft enforce >80 % coverage". A burn test reports the share of value-returning functions with `#test` cases per module and overall, and warns without failing while the overall share is below 80 %.

- [x] Decided (D109): at least 80 %, softly enforced; it used to read: enforce the convention for `selfhost/` (and start with the pure helpers of `ir.my`, `lower.my`, `util.my`), or restate it as "the examples, and the self-hosted compiler where a function is testable in isolation"
- [ ] The three places that state it agree with the decision
- [ ] The burn test: coverage per module and overall, a warning below 80 % (in the test output and as a CI annotation)
- [ ] Cases added, the pure helpers first, until the share passes 80 %
