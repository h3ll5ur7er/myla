# Myla

[![CI](https://github.com/h3ll5ur7er/myla/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/h3ll5ur7er/myla/actions/workflows/ci.yml)

Myla is a small, statically typed programming language with value semantics. It compiles to x86-64 Linux binaries without libc, and its compiler is written in Myla and compiles itself. It borrows from Swift, Rust and Python, but is none of them: newlines end statements, functions start with `fun`, collections are values, and everything is checked before anything runs.

```myla
enum Shape {
    Square(int),
    Rect(int, int),
}

#test(Shape.Rect(2, 3))[6]
fun area(s: Shape) -> int {
    return match s {
        Square(side) => side * side,
        Rect(w, h) => w * h,
    }
}

fun parse_digit(c: char) -> Result<int, str> {
    let d = (c as int) - ('0' as int)
    if d < 0 || d > 9 {
        return Err(f"not a digit: {c}")
    }
    return Ok(d)
}

fun sum_digits(text: str) -> Result<int, str> {
    var total = 0
    for c in chars(text) {
        total = total + parse_digit(c)?
    }
    return Ok(total)
}

fun main() {
    let shapes = [Shape.Square(3), Shape.Rect(2, 5)]
    var total = 0
    for s in shapes {
        total = total + area(s)
    }
    print(f"total area {total}")      // total area 19
    match sum_digits("20x6") {
        Ok(n) => print(n),
        Err(e) => print(e),           // not a digit: x
    }
}
```

And concurrency in the style of Swift: an actor's methods run one at a time, child tasks run in parallel, and values cross between them as copies.

```myla
actor Counter {
    n: int,
}

impl Counter {
    fun add(var self, k: int) -> int {
        self.n = self.n + k
        return self.n
    }
}

async fun work(c: Counter, times: int) -> int {
    for i in 0..times {
        await c.add(1)
    }
    return times
}

#main
async fun main() {
    let c = Counter { n: 0 }
    async let a = work(c, 1000)
    async let b = work(c, 2000)
    let done = await a + await b
    print(f"{done} calls, counter at {await c.add(0)}")   // 3000 calls, counter at 3000
}
```

## What it values

- **No dependencies.** The toolchain needs Python's standard library and GNU binutils (`as`, `ld`), nothing else; native programs are static binaries without libc.
- **Predictable code.** Explicitly sized integers (`int8` … `uint64`, `int` is `int32`), no implicit conversions, value semantics with copy-on-write, deep immutability for `let`, no null (`Option`), errors as values (`Result` and `?`).
- **Safety the checker can give cheaply.** Exhaustive `match`, ranges and spans in every diagnostic, actors whose state only their own methods reach, captures that can't be changed from a lambda, a warning for actor state checked before an `await` and changed after it.
- **One meaning, several implementations.** The interpreter defines the language; two interpreters and two native backends are tested against each other on every program of the test suites, down to the text of every diagnostic.
- **Self-hosting.** The compiler in `selfhost/` compiles itself to a byte-identical fixed point, and the tools around it (the language server, the REPL, the project tool, the grammar generator) are written in Myla too.

## The language

Structs, enums with payloads and `match`, tuples, lists and maps, strings and `char` (UTF-8), `float32`/`float64`; generics (monomorphized), traits with operator overloading and `#derive(Eq)`; methods, closures, pipelines (`x |> f(y)`), composition (`f >> g`) and partial application (`f(_, 2)`); guaranteed tail calls (`become`); modules with `pub` and packages; `#test(args)[expected]` cases next to the code they test; `async`/`await`, structured child tasks (`async let`, `std.task`) and actors on a multi-threaded native runtime.

The standard library has I/O and files (`std.io`, `std.fs`), processes (`std.process`), JSON and TOML (`std.json`, `std.toml`), number formatting (`std.num`) and task groups (`std.task`).

The reference is the wiki, starting at [Language](docs/Language.md); the reasons behind each rule are the numbered decisions on [Decisions](docs/Project/Decisions.md).

## Getting started

You need x86-64 Linux, Python 3.12 or later and GNU binutils. gdb is optional, for debugging.

```bash
python3 myla.py run examples/hello.my          # interpret a program
python3 myla.py test examples/structs.my       # run its #test cases
python3 myla.py check examples/structs.my      # type-check only
python3 myla.py build examples/hello.my -o hello && ./hello   # a native binary (-g: for gdb)
```

`scripts/bootstrap.sh` builds the self-hosted compiler through its three stages, checks the fixed point, and builds `build/myla`, the self-hosted command-line tool, and `build/myla-lsp`, the language server:

```bash
scripts/bootstrap.sh
build/myla run examples/concurrency.my         # the same commands as myla.py, faster
build/myla repl                                # the interactive interpreter
build/myla new hello && cd hello && ../build/myla run   # a project with a myla.toml
```

In a project, `build/myla` also has `build`, `test`, `check`, `fetch` (Git dependencies, with a lock file) and `clean`. Native programs with tasks run on one worker per CPU; `MYLA_THREADS` sets the number.

More in [Getting started](docs/Getting-started.md), including an examples reading order: every file in `examples/` is a runnable program.

## Editor support

The VS Code extension in [`vscode-extension/myla`](vscode-extension/myla/README.md) starts the language server (diagnostics as you type, hover, go to definition, references, completion, semantic highlighting), runs and tests files, and debugs them with gdb through its own debug adapter. A tree-sitter grammar, generated from [`grammar/myla.ebnf`](grammar/myla.ebnf), is in `editor/`. See [Editor tooling](docs/Architecture/Editor-tooling.md).

## How it is built

| Part | Where | Role |
| --- | --- | --- |
| Python toolchain | `src/myla/`, `myla.py` | The reference: lexer, parser, checker, tree-walking interpreter, `#test` runner, and a native backend that builds the first stage of the bootstrap |
| Self-hosted compiler | `selfhost/` | The same pipeline in Myla, with a mid-level IR and its verifier, a native backend with the concurrency runtime, and its own interpreter; `build/myla` |
| Tools in Myla | `tools/` | The language server (`tools/lsp/`) and the grammar generator (`tools/grammar/`) |
| Standard library | `src/myla/std/` | Written in Myla |
| Editor support | `vscode-extension/`, `editor/`, `grammar/` | The VS Code extension, the tree-sitter grammar, the grammar description |

The architecture, from the module loader to the native runtime, is described in [Architecture](docs/Architecture.md); the bootstrap in [Bootstrap](docs/Development/Bootstrap.md).

## Status

Version 1.0, self-hosting, was reached in June 2026. Since then: the mid-level IR, guaranteed tail calls, concurrency with actors and a work-stealing runtime, the project tool, and the tools rewritten in Myla. The review of October 2026 and what came of it are on [Review 2026-10](docs/Project/Review-2026-10.md); open bugs are on [Known issues](docs/Project/Known-issues.md).

Next on the [Roadmap](docs/Project/Roadmap.md): an LLVM backend, and other platforms through it (Linux on aarch64, macOS, Windows, WebAssembly), then a C FFI.

## Working on Myla

```bash
scripts/test.sh fast        # unit, integration and the quick burn tests, about 20 s
scripts/test.sh             # everything, the self-hosting gates included (several minutes)
scripts/bootstrap.sh        # after changing selfhost/ or the native backend: the fixed point
```

- **Tests.** Unit and integration tests for the Python toolchain; burn tests that run every example through the interpreters and both backends, pin the error corpus (`examples/errors/`, one rejected program per diagnostic), and compare the self-hosted compiler with the Python one stage by stage. See [Testing](docs/Development/Testing.md).
- **Tasks and wiki.** Work is planned as tasks in [`tasks/`](tasks/) and documented in the wiki in [`docs/`](docs/Home.md), both plain Markdown managed with [Genbeya](https://github.com/genbeya/genbeya). Conventions are in [Conventions](docs/Development/Conventions.md); coding agents start at [`AGENTS.md`](AGENTS.md).
- **History.** The design documents written while the language was designed, and a Rust edition removed in October 2026, are kept in the [Archive](docs/Archive.md).
