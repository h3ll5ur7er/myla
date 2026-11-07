# Known issues

Open bugs and gaps by component, each with a task that has its steps to reproduce; this page is the overview. A line goes when its task is `done`. The entries come from the reviews of 31 October ([[Project/Review-2026-10]]) and 6 November 2026 ([[Project/Review-2026-11]]).

[TOC]

## Self-hosted compiler

- **x86-64 miscompile:** a function-value parameter in a function that also contains a tail call is read from `%rdi` after the call's argument loads overwrote it: the binary segfaults where aarch64 and the interpreter print the result ([[MYLA-250]]).
- **Isolation:** a program's `impl [T] { fun len }` or `impl str { fun len }` is picked up by the standard library's own calls natively, not in the interpreter, so slices and format specs trap ([[MYLA-221]]).
- **Safety:** the raw-memory primitives (`__load64`, `__store64`, `__free`, `__addr_of`, …) are callable from a program with a warning; natively a bare segfault ([[MYLA-285]]).
- `#test` coverage of `selfhost/` is 70 percent against D109's 80, with no generator left ([[MYLA-184]]); `let`s in an `if`/`else` pair don't share frame cells ([[MYLA-183]]).
- The optimisation passes have invariants nothing checks ([[MYLA-294]]); the interpreter keeps about 115 KB per sleeping task ([[MYLA-296]]).
- The interpreter is about 500 times slower than native code (`fib(30)`: 3.7 s against 7 ms), and its maps are lists searched linearly ([[MYLA-317]], [[MYLA-310]]).

## Backends and platforms

The targets are x86-64 and aarch64 Linux and wasm32 on WASI; macOS and Windows are planned ([[MYLA-62]]). What the two new backends showed ([[Project/Reflection-2026-11]]):

- wasm32: a list or string stops at 2^26 elements with `out of memory`, far below the 4 GiB the memory allows: big cells round to the next power of two and freed big cells aren't reused across classes ([[MYLA-284]]).
- The reactor's protocols have run only under qemu, which can't reorder memory ([[MYLA-301]]); the burn suite can't run on aarch64 hardware, `wasmtime` and the browser page are tested nowhere in CI ([[MYLA-297]]).
- The two backends repeat seven helpers and the WASI import numbering ([[MYLA-298]]).

## Concurrency

- **Use after free in `task.timeout`:** a child that finishes before its deadline is armed leaves a stale timer that later writes into freed memory: a spurious `None`, an unrelated task cancelled, a segfault on 2+ workers ([[MYLA-230]]).
- Two tasks reading the same descriptor with `read_line_async` hang natively ([[MYLA-230]]).
- A non-reentrant actor method kind is still open ([[MYLA-274]]).

## Tooling in Myla

- A NUL byte in a path is silently truncated ([[MYLA-286]]); a write error on stdout other than a broken pipe is invisible ([[MYLA-287]]).
- The language server's bare completion dumps the workspace, and a long check blocks every request ([[MYLA-188]]).
- `task.cancel`'s fake signature, `Command.env` without validation, modules without `#test` cases ([[MYLA-295]]).

## Editor tooling

- The TextMate grammar isn't generated from `grammar/myla.ebnf` ([[MYLA-154]]); the language server's open points on Git dependencies and manifest documents ([[MYLA-155]]); no snippets for `actor` and `async` ([[MYLA-196]]).

## Language

- `if c { Some(n) } else { None }` can't be typed: branches aren't typed against each other ([[MYLA-290]]); a bound `T: Format` can't be formatted ([[MYLA-291]]); a negative slice bound silently means "before the start" ([[MYLA-292]]); two messages don't name the defaults the caller filled in ([[MYLA-293]]); float printing is 17 digits ([[MYLA-300]]).
- A generic function can't build an empty generic value (`B { items: [] }` as a `B<T>`), and a call's expected type takes no part in inference ([[MYLA-315]]); tuples have no `==` and neither tuples nor structs can be map keys ([[MYLA-313]]); `int` wraps silently at 32 bits ([[MYLA-311]]). From [[Project/AoC-2015-2021]].

## Documentation and repository

- The recorded Python answers cover only the examples and the error corpus now; 20 new corpus files are held to the CLI's own output ([[MYLA-288]]).
- 153 seed versions in six days: 110 of the 117 MB pack ([[MYLA-289]]).
- No example or doc block uses the November features ([[MYLA-299]]).
- [[Language/Methods-and-traits]] says `#derive(Eq)` rejects `char` and float fields; it accepts them ([[MYLA-316]]).
