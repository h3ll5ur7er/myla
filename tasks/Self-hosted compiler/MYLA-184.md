---
id: MYLA-184
title: "The #test convention in selfhost/: 1,164 of 1,259 value-returning functions have none"
type: chore
status: backlog
priority: low
labels: [selfhost, tests, docs]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). [[Development/Conventions]], the `myla` skill and [[Architecture/Self-hosted-compiler]] say every value-returning function in `selfhost/` carries `#test` cases; `tests/burn/test_examples_tests.py` enforces it only for `examples/`. Counted on 2026-10-31: lexer 21 of 21 untested, parser 103 of 108, checker 296 of 299, lower 85 of 85, interp 180 of 183, codegen 182 of 194. The tests that exist are meaningful.

- [ ] Decide: enforce the convention for `selfhost/` (and start with the pure helpers of `ir.my`, `lower.my`, `util.my`), or restate it as "the examples, and the self-hosted compiler where a function is testable in isolation"
- [ ] The three places that state it agree with the decision
