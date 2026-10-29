---
id: MYLA-128
title: Guaranteed tail calls (become)
type: feature
status: done
priority: medium
labels: [language, ir, codegen, selfhost, interpreter]
---
D87, after [[MYLA-126]] and [[MYLA-127]]: `become f(args)` ends the function like `return f(args)` and guarantees the call doesn't grow the stack, in both interpreters and both native backends, with `-g` too.

- [x] The language pages ([[Language/Statements]], the grammar, the keyword list) and the decision (D87)
- [x] Lexer and parser, Python and self-hosted: the `become` keyword and statement
- [x] Checkers, Python and self-hosted: where it may stand, the result type, no `?`, the arguments it can pass (scalars; heap values, owned by a direct callee or parameters and captures for a function value; aggregates that are parts of parameters), with the same errors and notes; error corpus entries
- [x] Interpreters, Python and self-hosted: a trampoline in the call loop
- [x] Self-hosted backend: the lowering drops the owners and ends the block with a tail-call terminator (direct, through a function value, with an aggregate result); a parameter a `become` passes a heap value to is owned; the backend jumps, under `-g` too
- [x] Python backend: callee-pops, and `become` as a jump
- [x] Tests: a parity program recursing deeply through `become` (direct, mutual, through a function value, with an aggregate result) run by every implementation; the checker's errors; the IR text form

## What it became

- **Checkers** (`_check_become` in [[src/myla/types.py]], `check_become` in [[selfhost/checker.my]]), the same errors, each in the error corpus (`type_become_*`): not in a lambda; a call, without `?`, of a function, a method or a function value; the function's result type; a function value and the heap values passed to it (parts of) parameters; a struct, tuple, enum, function value or type parameter (a part of) a parameter; a `var self` method only on `self`, with no aggregate part of `self`; a parameter not both handed a value over (`become_handovers`, `handovers`) and passed on to a function value.
- **Interpreters:** `_BecomeSignal` and `_run` (Python), `Ctrl.CBecome`, `TailCall` and `run_tail` (self-hosted).
- **Self-hosted backend:** the lowering drops temporaries and owners before the call and ends the block with the IR's new `become` terminator (verified: a call before it, no owner live); `emit_tail_call` handles all four calls (`*%rcx` through a function value), `emit_frame_handover` the frame, under `-g` too; `find_kept_params` makes the checker's handovers owned and its passed-on parameters borrowed.
- **Python backend:** callee-pops (`ret $8n`), owned parameters for the handovers (`_param_owned`), `_gen_become` and `_frame_handover`, and a `__fnval` adapter that jumps.
- Found on the way: [[MYLA-129]] (a heap-free aggregate argument read from a `var self` receiver).

## Evidence

- The parity program `become_keeps_the_stack_flat` (direct, mutual, method, `var self` method, function values from a field, a lambda, a parameter and a partial application, an aggregate result, more and fewer argument words, heap values handed over and passed on, a generic callee, no result; 20,000 deep) gives the same output in both interpreters and both native backends. With `return` instead of `become` the Python interpreter stops at a depth of 300 (RecursionError).
- At a million deep (`test_become_replaces_the_frame`): both native backends, with and without `-g`, print what the self-hosted interpreter prints; the same program with `return` segfaults in the self-hosted build, also without `-g`.
- Costs: compiling itself, the self-hosted compiler runs 0.14% more instructions for the same output (2,748,477,596 → 2,752,418,104); the Python backend with callee-pops builds a 1.1% smaller compiler that runs 0.7% fewer instructions (same source).
- Unit 595, integration 2, burn 758 (5 skipped) and the extension's 54 tests pass; the bootstrap reaches its byte-identical fixed point (5,292,285 bytes).
