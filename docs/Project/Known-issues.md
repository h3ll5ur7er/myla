# Known issues

Open bugs and gaps by component, each with a task that has its steps to reproduce; this page is the overview. A line goes when its task is `done`. The entries come from the reviews of 31 October ([[Project/Review-2026-10]]), 6 November ([[Project/Review-2026-11]]) and 9, 10, 12 and 17 November 2026 ([[Project/Review-2026-11-09]], [[Project/Review-2026-11-10]], [[Project/Review-2026-11-12]], [[Project/Review-2026-11-17]]), and from round 5's lanes. Round 7's packages ([[Project/Follow-up-plan]]) hold the smaller findings of the last review; the lines here are their main ones.

[TOC]

## Self-hosted compiler

- `#test` coverage of `selfhost/` is 61 percent (1,504 of 2,451 value-returning functions, 2026-11-17, `e153ee08`, `scripts/test_coverage.py`) against D109's 80, with no generator left ([[MYLA-184]]).
- The interpreter is about 500 times slower than native code (`fib(30)`: 3.7 s against 7 ms on `d5d80bc`, [[MYLA-317]]).
- **Interpreter:** `myla run` of an empty program costs 29.3 M instructions where it cost 24.0 M at round 5 (35.7 M before its constants were evaluated when first named, 2026-11-17 on `fe30af6`, [[MYLA-792]]); most of the rest is the implicit `std.float`'s ([[MYLA-796]]).
- **Native code, memory safety:** `m.contains(k())`, where `k()` changes the map, reads the freed map: `true false true` natively for the interpreter's `true true true` ([[MYLA-543]]).
- **Async code, every runner:** a mutating method call on a place loses its write when the call has an `await` and the receiver isn't a plain name: `g[i + 1].push(await f())` leaves the list as it was; `xs[::await one()]` is wrong interpreted and an internal error at build ([[MYLA-791]]).
- `--checked` int64 arithmetic is twice as slow by time in hot loops on x86-64 (`s += i * 3 - (i >> 1)`: 0.22 s against 0.11 s plain, 0.25 s with the trap inline on the same machine, where the review measured 0.62 s against 0.12 s): each check is now a `jo` to its trap after the function's return, one not-taken branch per operation ([[MYLA-551]]). On aarch64 a `--checked` function over about 1 MiB doesn't assemble, as the branch to its trap is out of range ([[MYLA-551]]). A function named `segv` doesn't assemble on any target ([[MYLA-791]]).
- **Checker:** an operator impl's bounds aren't checked where an operator with type arguments, `Neg`, `Index` or `IndexSet` picks it, so a `Conv<int>` passes for a `Conv<str>` and native code reads an int as a string ([[MYLA-612]]). An `async` method in an `impl Add` is called by `+` from plain code and crashes natively ([[MYLA-790]]). A program's own `std/process.my` makes a function without a `return` pass ([[MYLA-584]]).
- **Build, polymorphic recursion:** a finite program that wraps a type already 64 deep once more (`wrap([x])` of a 64-deep `x`) checks and runs, but `myla build` refuses it as 65 types deep ([[MYLA-624]]).
- **Loading:** text that starts `#test` inside a function body of an imported module is skipped unparsed; 6,000 `|> id` overflow the compiler's stack ([[MYLA-793]]). A hello world's check costs 25.4 M instructions where it cost 20.7 M before the implicit `std.float`, and no test bounds it ([[MYLA-585]], [[MYLA-793]]).

## Backends and platforms

The targets are x86-64 and aarch64 Linux, wasm32 on WASI and x86-64 Windows; macOS is planned ([[MYLA-62]]).

- **Windows:** on the real runner `process/many-children` counted 393 of 400 children once (CI run 246 of `e153ee08`), and the case can't say why; `env("PATH")` is case-sensitive; a batch file named with a trailing dot gets the wrong quoting ([[MYLA-705]]). No long paths, `/` written into verbatim paths, a deferred close without a limit ([[MYLA-798]]).
- `gen_main` ignores a failed write of its output ([[MYLA-718]]); a function named with a letter outside ASCII doesn't assemble with clang ([[MYLA-775]]).


## Concurrency

- A non-reentrant actor method kind is still open ([[MYLA-274]]).
- Natively, on 16 workers, armed timers make every loop top take `__timer_lock`: CPU-bound tasks about 15 % slower ([[MYLA-296]]).
- A trait method can't be async, so there is no async `Read` or `Write` ([[MYLA-434]]).
- The poller takes at most four events a wait (under 2 percent to gain, [[MYLA-531]]); a keep-alive request through std.http's lot costs 4 to 6 percent more than a worker waiting on its connection ([[MYLA-530]]).
- **Runtime:** I/O beside a task that only yields fell from 98,942 to 499 loopback round trips a second with D245's millisecond glance ([[MYLA-755]]); `net.line_reader_with` overflows for a limit near the largest `int`, and a forged `Signals` value starts listening ([[MYLA-794]]).

## Tooling in Myla

- The language server's bare completion dumps the workspace, and a long check blocks every request ([[MYLA-188]]).

## Editor tooling

- The TextMate grammar isn't generated from `grammar/myla.ebnf` ([[MYLA-154]]); the language server's open points on Git dependencies and manifest documents ([[MYLA-155]]); no snippets for `actor` and `async` ([[MYLA-196]]).

## Language

- Every field and method of a `pub` type is public, so no library type can protect an invariant ([[MYLA-433]]).

## Standard library

- **std.http:** with `max_connections` filled by one-byte requests, eviction closes the newcomer: 99 of 100 normal clients go unanswered ([[MYLA-549]]); bodies begun may hold `max_connections × max_body_bytes`, and slow readers hold the workers ([[MYLA-794]]).
- **The router:** `static_files` leaves its root on Windows (`..%5c`); malformed patterns are taken silently ([[MYLA-613]]). std.json parses a 64,000-digit number in 11.7 s, so four 300 kB bodies stop a server; `static_files` serves dot files and follows symlinks ([[MYLA-795]]).
- **std.xml:** the stream reader holds back whole events when a read cuts a multi-byte character, and a DOCTYPE over short reads is quadratic ([[MYLA-460]]).
- **Numerics:** `json.decode<Matrix>` accepts a 65536×65536 shape with no data in a plain build, and `inverse` of a singular `Mat4` gives `Some` ([[MYLA-587]]); `sinh` and `tanh` are up to 74,000 ulps off ([[MYLA-585]]); `math.log10` near 1 is off in the eleventh digit, and printing a float costs up to 6.5 M instructions ([[MYLA-796]]).

## Documentation and repository

- Seventeen burn modules still ask the recorded Python answers about the 32 examples of the retirement, so the gates keyed by an example's text freeze it (`examples/floats.my`'s stale comments stay); token and AST expectation files would replace the recordings ([[MYLA-288]]).
- The generated tests run a fixed sample (1,500 of 17,497 extreme calls) and CI never the rest; the `myla` skill has two false claims after later merges; README and Roadmap still plan Windows and the website ([[MYLA-800]]).
- **Website:** the skip link leaves the page and `/quickstart` scrolls sideways on a phone ([[MYLA-630]]); the playground loses output printed before a stop, a wrong-shaped progress value breaks the learn area, 26 reference signatures drop their defaults ([[MYLA-799]]).
- The tutorial and the "Why Myla" page aren't written yet (D114, [[MYLA-234]]).
