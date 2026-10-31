---
id: MYLA-145
title: A lambda can't change what it captures
type: feature
status: done
priority: high
labels: [concurrency, checker, selfhost, language]
---
From the concurrency stress tests ([[MYLA-144]], test 1, "shared mutation through hidden aliases"), decided as D93: a lambda that assigned to a variable it captured changed only its copy, so two callbacks counting into a captured counter left it at 0 without a word. The Functions page said captures were immutable, D48 that a change affected only the copy, and the implementations disagreed: the Python interpreter kept the lambda's copy between calls (100,000 per callback), the self-hosted interpreter and native code started each call afresh (1).

- [x] Both checkers reject a change to a captured variable inside a lambda: an assignment to it or to a field or element of it, `push`, `pop`, `remove`, `append`, a `var self` method on it (every write is checked through the place's root, `_check_lvalue` / `check_lvalue`)
- [x] The same diagnostic in both, with a help line; two cases in the error corpus
- [x] D93, the Functions page

## Evidence

- Before: `t01a_closures` (two callbacks in a list, each incrementing a captured `Box`, run by two children 100,000 times) printed `100000 100000 0` on the Python interpreter and `1 1 0` on the self-hosted interpreter and natively.
- After: `type error: a lambda can't change 'counter', a variable it captures: it holds a copy of its own` with `help: return the new value, or keep shared state in an actor`, from both checkers. The shared counter as an actor (`t01b_actor`) counts exactly 200,000 everywhere.
- No example, standard library module or part of the self-hosted compiler changes a capture. The error corpus (201 cases) and the checker parity tests pass.
- Unit 621, integration 2, burn 808 (5 skipped) and the extension's 54 tests pass; the bootstrap reaches its byte-identical fixed point (6,107,397 bytes).
