# Known issues

Open bugs and gaps by component, each with a task that has its steps to reproduce; this page is the overview. A line goes when its task is `done`. Most entries come from the review of 31 October 2026 ([[Project/Review-2026-10]]); the bugs the October review before it found are fixed and signed off.

[TOC]

## Python toolchain

Retired by D101 ([[MYLA-219]]); its tasks stay in the `Python toolchain` epic.

- `as char` is unchecked: a surrogate crashed the Python interpreter when printed, native code prints garbage ([[MYLA-177]]). *Fixed, in review.*
- Map removal keeps no tombstones in the Python backend ([[MYLA-151]]); moot since the backend was retired.

## Self-hosted compiler

- Map iteration order differs between the interpreter and native code (allowed by the page; D105 makes it insertion order everywhere, not built yet) ([[MYLA-179]]).

- The convention that every value-returning function in `selfhost/` has `#test` cases is 8 % true ([[MYLA-184]]). *Fixed, in review: 80 %, mostly generated cases.*
- Native code took a read-only method receiver, and the Python interpreter a function's argument, after a later argument that writes the same variable ([[MYLA-237]]). *Fixed, in review.*
- The self-hosted interpreter lost an argument's change to a `var self` receiver ([[MYLA-238]]). *Fixed, in review.*

Also by design: x86-64 Linux is the only target (D2); the LLVM round ([[MYLA-62]]) is to change that.

## Concurrency

- An awaited `var self` struct method on an actor field is accepted and behaves three ways across the implementations ([[MYLA-169]]). *Fixed, in review.*
- The D95 warning is bypassed through `self` methods ([[MYLA-171]]).
- Every tasked program reserves 128 GiB of address space; worker stacks have no guard page ([[MYLA-172]]).

## Tooling in Myla

- The `__` primitives are callable from user code ([[MYLA-186]]). *Fixed, in review.*
- The language server's bare completion dumps the workspace, and a long check blocks every request ([[MYLA-188]]).

## Editor tooling

- The TextMate grammar isn't generated from `grammar/myla.ebnf` ([[MYLA-154]]); the language server's open points on Git dependencies and manifest documents ([[MYLA-155]]); no snippets for `actor` and `async` ([[MYLA-196]]).

## Documentation and repository

No open issues.
