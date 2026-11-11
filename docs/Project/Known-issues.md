# Known issues

Open bugs and gaps by component, each with a task that has its steps to reproduce; this page is the overview. A line goes when its task is `done`. The entries come from the reviews of 31 October ([[Project/Review-2026-10]]), 6 November ([[Project/Review-2026-11]]) and 9 and 10 November 2026 ([[Project/Review-2026-11-09]], [[Project/Review-2026-11-10]]), and from round 5's lanes. The findings round 5's wave A2 fixes are in its packages ([[Project/Follow-up-plan]]), not here.

[TOC]

## Self-hosted compiler

- `#test` coverage of `selfhost/` is 67 percent (1,402 of 2,107 value-returning functions, `scripts/test_coverage.py`) against D109's 80, with no generator left ([[MYLA-184]]).
- The interpreter is about 500 times slower than native code (`fib(30)`: 3.7 s against 7 ms on `d5d80bc`, [[MYLA-317]]).
- **Interpreter:** a written `eq` or `hash` of a generic type, called for a list's `==` or a map key, binds no type parameter, so an operation typed by `T` falls back to erasure ([[MYLA-436]]); a `uint64` map key of 2^63 or more is written signed in `map key … not found` ([[MYLA-440]]).
- **Native:** a missing map key of a struct, enum or list type is `map key not found` without the key the interpreter writes ([[MYLA-441]]).
- Maps never shrink: iteration over an emptied map costs its old size, 82 s for 20,000 keys taken oldest-first from a once-10^6 map ([[MYLA-429]]).
- `--checked` 64-bit arithmetic is three to five times slower in hot loops, as a checked `*` divides to detect overflow ([[MYLA-430]]).
- An import of std.io checks `io`, `fs` and `bytes` whole, as they import each other: 61.8 M instructions of a hello world's 101 M, as [[Project/Review-2026-11-10]] measured ([[MYLA-432]]).

## Backends and platforms

The targets are x86-64 and aarch64 Linux and wasm32 on WASI; macOS and Windows are planned ([[MYLA-62]]).

## Concurrency

- A non-reentrant actor method kind is still open ([[MYLA-274]]).
- Natively, on 16 workers, armed timers make every loop top take `__timer_lock`: CPU-bound tasks about 15 % slower ([[MYLA-296]]).
- A trait method can't be async, so there is no async `Read` or `Write` ([[MYLA-434]]).

## Tooling in Myla

- The language server's bare completion dumps the workspace, and a long check blocks every request ([[MYLA-188]]).

## Editor tooling

- The TextMate grammar isn't generated from `grammar/myla.ebnf` ([[MYLA-154]]); the language server's open points on Git dependencies and manifest documents ([[MYLA-155]]); no snippets for `actor` and `async` ([[MYLA-196]]).

## Language

- A compound assignment's hoisted index loses the place's type: `r[Ok("a")] += 10` and `acc.items += lst()` can't infer what `r[Ok("a")] = …` and `acc.items = lst()` do ([[MYLA-448]]); a literal before the element that fixes a wider type must fit `int32`: `[4000000000, big]` with `big: int64` fails ([[MYLA-449]]).
- Every field and method of a `pub` type is public, so no library type can protect an invariant ([[MYLA-433]]).

## Standard library

- A failing `opt.expect("…")` points into `lib/std/option.my`, not at its caller ([[MYLA-435]]).
- `Url` isn't `Eq` or `Hash` ([[MYLA-488]]).

## Documentation and repository

- The recorded Python answers cover only the examples and the error corpus now; 20 new corpus files are held to the CLI's own output ([[MYLA-288]]).
- The tutorial and the "Why Myla" page aren't written yet (D114, [[MYLA-299]]).
