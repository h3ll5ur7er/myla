# Known issues

Open bugs and gaps by component, each with a task that has its steps to reproduce; this page is the overview. A line goes when its task is `done`. Most entries come from the review of 31 October 2026 ([[Project/Review-2026-10]]); the bugs the October review before it found are fixed and signed off.

[TOC]

## Python toolchain

The reference implementation.

- The Python backend can't compile a map literal whose values involve generics (`[1: Some(2)]` dies with a `KeyError`) ([[MYLA-174]]).
- A positive literal one past the signed maximum (`2147483648`, `128i8`) is accepted and wraps, in both checkers ([[MYLA-175]]).
- A float32 overflow (`1e38 * 10.0`) crashes the interpreter where native code prints `inf` ([[MYLA-176]]).
- `as char` is unchecked: a surrogate crashes the interpreter when printed, native code prints garbage ([[MYLA-177]]).
- A `?` failing inside a list or map literal leaks the half-built literal, in both backends ([[MYLA-157]]).
- Tracebacks from the CLI on a directory argument, a broken pipe or a missing output directory; a byte-order mark is a lex error ([[MYLA-178]]).
- A method's parameter list takes a trailing comma where a function's doesn't ([[MYLA-180]]).
- Map iteration order differs between the interpreter and native code (allowed by the page; a decision) ([[MYLA-179]]).
- Map removal keeps no tombstones in the Python backend ([[MYLA-151]]).

## Self-hosted compiler

- Deep input segfaults the self-hosted parser, interpreter and language server: about 1,000 nested parentheses or 900 levels of recursion ([[MYLA-182]]; the structural fix is a frame layout by liveness, [[MYLA-183]]).
- A local closure named like a builtin (`let build = (n: int) => n + 1`) calls the builtin in the self-hosted interpreter and native code ([[MYLA-152]]).
- The convention that every value-returning function in `selfhost/` has `#test` cases is 8 % true ([[MYLA-184]]).

Also by design: x86-64 Linux is the only target (D2); the LLVM round ([[MYLA-62]]) is to change that.

## Concurrency

- A child task of an actor method may read the actor's fields off the actor: both checkers accept it, native code crashes or hangs at two workers and more ([[MYLA-168]]).
- An awaited `var self` struct method on an actor field is accepted and behaves three ways across the implementations ([[MYLA-169]]).
- A failure isn't reported while a sibling runs without a suspension point ([[MYLA-170]]).
- The D95 warning is bypassed through `self` methods ([[MYLA-171]]).
- Every tasked program reserves 128 GiB of address space; worker stacks have no guard page ([[MYLA-172]]).
- The Concurrency page overstates `print` atomicity and the actors' FIFO order, and leaves out the cost of deep copies ([[MYLA-173]]).
- The stress program `t08_failing_child_cancels_its_children` depends on timing and fails under load ([[MYLA-197]]).

## Tooling in Myla

- The `__` primitives are callable from user code ([[MYLA-186]]).
- `myla test file.my` runs the `#test` cases of the std modules the file imports ([[MYLA-187]]).
- The language server's bare completion dumps the workspace, and a long check blocks every request ([[MYLA-188]]).

## Editor tooling

- The debugger tests always skip in CI: the burn job installs no gdb ([[MYLA-156]]).
- The TextMate grammar isn't generated from `grammar/myla.ebnf` ([[MYLA-154]]); the language server's open points on Git dependencies and manifest documents ([[MYLA-155]]); no snippets for `actor` and `async` ([[MYLA-196]]).

## Documentation and repository

- The status text of README, Home, Language, Architecture, Decisions, Roadmap and the test pages is one to four months old ([[MYLA-191]]).
- `timer.py`, duplicate scripts, stray test output ([[MYLA-192]]); the burn suite's speed and timings ([[MYLA-153]]).
