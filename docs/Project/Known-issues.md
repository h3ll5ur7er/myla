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

- wasm32: the shadow stack lay above the static data, so a deep overflow of it overwrote data; a trap under `run.mjs` printed `wasm trap: …` and exited 134 ([[MYLA-261]]). *Fixed, in review.*
- aarch64 and wasm32: a plain function used as a function value with a parameter passed by value stops the compiler (`__fnval` panics; [[MYLA-263]]), as does the lowering's `RtPair` fallback ([[MYLA-264]]).
- A computed NaN's bits differed between targets (`to_bits(0.0 / 0.0)`, `copysign(1.0, nan)`) ([[MYLA-266]]). *Fixed by D128, in review.*
- The runtime's lock-free protocols were argued from x86-64's memory order. Unlocks were plain stores, which aarch64 may make visible before a critical section's stores; a task's end and the failure flag lacked an order ([[MYLA-267]]). *Fixed, in review; the stress programs run on arm64 hardware in CI.*
- The aarch64 and wasm32 tests skip silently when clang, `ld.lld`, `wasm-ld`, qemu or Node is missing, and the full self-compile on those targets isn't in CI ([[MYLA-268]]).
- On wasm32 there are no processes (`run` gives `SpawnError.Unsupported`, D129), one worker, and input that can't suspend; no page says so yet ([[MYLA-266]]).

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
