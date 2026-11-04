# Known issues

Open bugs and gaps by component, each with a task that has its steps to reproduce; this page is the overview. A line goes when its task is `done`. Most entries come from the review of 31 October 2026 ([[Project/Review-2026-10]]); the bugs the October review before it found are fixed and signed off.

[TOC]

## Python toolchain

Retired by D101 ([[MYLA-219]]); its tasks stay in the `Python toolchain` epic.

- `as char` is unchecked: a surrogate crashed the Python interpreter when printed, native code prints garbage ([[MYLA-177]]). *Fixed, in review.*
- Map removal keeps no tombstones in the Python backend ([[MYLA-151]]); moot since the backend was retired. Natively a `remove` rebuilds the whole table, O(capacity) ([[MYLA-271]]).

## Self-hosted compiler


- The convention that every value-returning function in `selfhost/` has `#test` cases is 8 % true ([[MYLA-184]]). *Fixed, in review: 80 %, mostly generated cases.*
- Native code took a read-only method receiver, and the Python interpreter a function's argument, after a later argument that writes the same variable ([[MYLA-237]]). *Fixed, in review.*
- The self-hosted interpreter lost an argument's change to a `var self` receiver ([[MYLA-238]]). *Fixed, in review.*

- A `become` passing a function-value parameter on to a function stops the compiler with an internal error, on every target ([[MYLA-253]]).

## Backends and platforms

The targets are x86-64 and aarch64 Linux and wasm32 on WASI; macOS and Windows are planned ([[MYLA-62]]). What the two new backends showed ([[Project/Reflection-2026-11]]):

- wasm32: the shadow stack lies above the static data, so a deep overflow of it would overwrite data instead of trapping; a trap under `run.mjs` prints `wasm trap: …` and exits 134 instead of `runtime error: stack overflow` and 1 ([[MYLA-261]]).
- aarch64 and wasm32: a plain function used as a function value with a parameter passed by value stops the compiler (`__fnval` panics; [[MYLA-263]]), as does the lowering's `RtPair` fallback ([[MYLA-264]]).
- A computed NaN's bits differ: `to_bits(0.0 / 0.0)` is 0xFFF8… on x86-64 and wasm on x86-64, 0x7FF8… on aarch64 ([[MYLA-266]]).
- The runtime's lock-free protocols were argued from x86-64's memory order; on aarch64 they pass under qemu, which rarely reorders memory ([[MYLA-267]]). Unlocking is a plain store, which aarch64 hardware may reorder before a critical section's stores.
- The aarch64 and wasm32 tests skip silently when clang, `ld.lld`, `wasm-ld`, qemu or Node is missing, and the full self-compile on those targets isn't in CI ([[MYLA-268]]).
- On wasm32 there are no processes (`run` gives `Other(38)`), one worker, and input that can't suspend; no page says so yet ([[MYLA-266]]).

## Concurrency

- An awaited `var self` struct method on an actor field is accepted and behaves three ways across the implementations ([[MYLA-169]]). *Fixed, in review.*
- The D95 warning is bypassed through `self` methods ([[MYLA-171]]).
- Every tasked program reserves 128 GiB of address space; worker stacks have no guard page ([[MYLA-172]]). *Fixed, in review: one arena per worker, reserved in chunks; guard pages and alternate signal stacks.*

## Tooling in Myla

- The `__` primitives are callable from user code ([[MYLA-186]]). *Fixed, in review.*
- The language server's bare completion dumps the workspace, and a long check blocks every request ([[MYLA-188]]).

## Editor tooling

- The TextMate grammar isn't generated from `grammar/myla.ebnf` ([[MYLA-154]]); the language server's open points on Git dependencies and manifest documents ([[MYLA-155]]); no snippets for `actor` and `async` ([[MYLA-196]]).

## Documentation and repository

No open issues.
