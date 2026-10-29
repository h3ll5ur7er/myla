---
id: MYLA-128
title: Guaranteed tail calls (become)
type: feature
status: in-progress
priority: medium
labels: [language, ir, codegen, selfhost, interpreter]
---
D87, after [[MYLA-126]] and [[MYLA-127]]: `become f(args)` ends the function like `return f(args)` and guarantees the call doesn't grow the stack, in both interpreters and both native backends, with `-g` too.

- [ ] The language pages ([[Language/Statements]], the grammar, the keyword list) and the decision (D87)
- [ ] Lexer and parser, Python and self-hosted: the `become` keyword and statement
- [ ] Checkers, Python and self-hosted: where it may stand, the result type, no `?`, the arguments it can pass (scalars; heap values, owned by a direct callee or parameters and captures for a function value; aggregates that are parts of parameters), with the same errors and notes; error corpus entries
- [ ] Interpreters, Python and self-hosted: a trampoline in the call loop
- [ ] Self-hosted backend: the lowering drops the owners and ends the block with a tail-call terminator (direct, through a function value, with an aggregate result); a parameter a `become` passes a heap value to is owned; the backend jumps, under `-g` too
- [ ] Python backend: callee-pops, and `become` as a jump
- [ ] Tests: a parity program recursing deeply through `become` (direct, mutual, through a function value, with an aggregate result) run by every implementation; the checker's errors; the IR text form
