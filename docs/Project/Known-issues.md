# Known issues

Open bugs and gaps by component, each with a task that has its steps to reproduce; this page is the overview. A line goes when its task is `done`. The entries come from the reviews of 31 October ([[Project/Review-2026-10]]), 6 November ([[Project/Review-2026-11]]) and 9, 10 and 12 November 2026 ([[Project/Review-2026-11-09]], [[Project/Review-2026-11-10]], [[Project/Review-2026-11-12]]), and from round 5's lanes. Round 6's packages ([[Project/Follow-up-plan]]) hold the smaller findings of the last review; the lines here are their main ones.

[TOC]

## Self-hosted compiler

- `#test` coverage of `selfhost/` is 63 percent (1,475 of 2,347 value-returning functions after round 6, `scripts/test_coverage.py`) against D109's 80, with no generator left ([[MYLA-184]]).
- The interpreter is about 500 times slower than native code (`fib(30)`: 3.7 s against 7 ms on `d5d80bc`, [[MYLA-317]]).
- **Interpreter:** the binding of type parameters is lost when a map key's written `eq` or `hash` runs before a `var self` call, so `m[k].sort()` on a `[uint64]` sorts signed; the environment memo grows per call path (a generic `fib(27)`: 163 MB against 13 MB) ([[MYLA-414]]). Small differences from native code in texts and map order ([[MYLA-546]]). A `StringBuilder` holds each byte in a word (a 20 MB string takes 280 MB to build, [[MYLA-600]]); every turn of the scheduler polls every task that waits for a descriptor ([[MYLA-604]]); a builtin's call is found by comparing its name with each builtin's, 14 percent of reading lines ([[MYLA-605]]).
- **Native code, memory safety:** a value read from a container is freed by a later operand (`h.xs[0] + h.repl()` is `old1!` interpreted and `!` natively; 25 of 90 forms), with two leaks and an evaluation order that differs ([[MYLA-543]]); a closure in a variable that captures a recursive enum segfaults when copied to a task, an actor or a channel ([[MYLA-415]]).
- `self.f(self.g(k))` in a `var self` method copies the receiver for `f` ([[MYLA-542]]).
- `--checked` int64 arithmetic is twice as slow by time in hot loops on x86-64 (`s += i * 3 - (i >> 1)`: 0.22 s against 0.11 s plain, 0.25 s with the trap inline on the same machine, where the review measured 0.62 s against 0.12 s): each check is now a `jo` to its trap after the function's return, one not-taken branch per operation ([[MYLA-551]]).
- **Checker:** an impl's bound that names a generic trait (`I: Iterator<str>`) isn't checked where the impl is used, so an `Iterator<int>` gets in and native code reads an int as a string ([[MYLA-538]]). D178's call error fires on a generic actor's getter ([[MYLA-417]]); D95 no longer reports an `await` and a mutator in one head ([[MYLA-394]]); `x.format(spec)` on a builtin behind `T: Format` is an internal error ([[MYLA-544]]).
- **Loading:** a program's own top-level `std/` directory is read lazily, so `myla check` says `ok` over its errors ([[MYLA-413]]); a declaration swallowed after a missing `}` loads silently when it doesn't start its line, and a library root written with `..` fails ([[MYLA-545]]). A hello world checks in 6.1 ms (2026-11-12, `547339a`) against the 5 ms aimed at, and the generated code depends on which library bodies were read ([[MYLA-552]]); a third of that check is page faults, which huge pages for the heap's chunks would mostly save ([[MYLA-608]]).
- **`myla test`:** a multi-line panic is cut natively, an empty `Err` passes, and exit statuses outside 0 to 255 differ between runners ([[MYLA-547]]).

## Backends and platforms

The targets are x86-64 and aarch64 Linux and wasm32 on WASI; macOS and Windows are planned ([[MYLA-62]]).

## Concurrency

- A non-reentrant actor method kind is still open ([[MYLA-274]]).
- Natively, on 16 workers, armed timers make every loop top take `__timer_lock`: CPU-bound tasks about 15 % slower ([[MYLA-296]]).
- A trait method can't be async, so there is no async `Read` or `Write` ([[MYLA-434]]).
- The poller takes at most four events a wait (under 2 percent to gain, [[MYLA-531]]); a keep-alive request through std.http's lot costs 4 to 6 percent more than a worker waiting on its connection ([[MYLA-530]]).
- **Runtime:** a blocking read of a socket in a task (`io.buffered(s).read_line()`) still holds its worker, and with more of them than workers the program hangs, saying so on stderr after a second ([[MYLA-548]]).

## Tooling in Myla

- The language server's bare completion dumps the workspace, and a long check blocks every request ([[MYLA-188]]).

## Editor tooling

- The TextMate grammar isn't generated from `grammar/myla.ebnf` ([[MYLA-154]]); the language server's open points on Git dependencies and manifest documents ([[MYLA-155]]); no snippets for `actor` and `async` ([[MYLA-196]]).

## Language

- Every field and method of a `pub` type is public, so no library type can protect an invariant ([[MYLA-433]]).

## Standard library

- **std.http:** one byte per socket stops a default server, as a request that has begun holds a worker for `read_ms` ([[MYLA-549]]).
- **std.xml:** the stream reader holds back a complete event until more bytes arrive ([[MYLA-460]]).
- **D184 leftovers:** `std.yaml` traps on a hex scalar past `int64`, a buffered seek and `bigint.bit_len` overflow, `archive.zip_read` has no output limit ([[MYLA-550]]).
- `std.args` accepts specs that can't work; BitSet, Lru and Grid have no `iter()` ([[MYLA-553]]).

## Documentation and repository

- Seventeen burn modules still ask the recorded Python answers about the 32 examples of the retirement, so the gates keyed by an example's text freeze it (`examples/floats.my`'s stale comments stay); token and AST expectation files would replace the recordings ([[MYLA-288]]).
- The tests pin one program per fixed bug; the reviews' generators, which found this round's older bugs, aren't in the suite ([[MYLA-555]]). Stale sentences and 25 `done` tasks with open boxes ([[MYLA-554]]).
- The tutorial and the "Why Myla" page aren't written yet (D114, [[MYLA-234]]).
