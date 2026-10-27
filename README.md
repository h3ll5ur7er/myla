# Myla Programming Language

Very simple custom language with a compiler and an interpreter.
Inspired by modern languages like Swift, Rust, and Python.

## Visions
### Short Term
- No dependencies
- Easy to learn and understand
- Focus on simplicity, not safety
- Explicitly sized primitive types (e.g. `int32`/`uint8`), not Python-style dynamic numbers
- Neat, modern cli tool
### Long Term
- Self-hosted
- Algebraic data types (enums on steroids) and pattern matching
- Structs and Traits
- A growing standard library (tuples, lists, maps, ...)
- First-class functions: lambdas/closures and functional pipelines
- Operator overloading and custom operators
- Extensible using metaprogramming (attributes/macros, e.g. `#main`, `#test`)
- All kinds of syntactic sugar

> Concrete syntax proposals and a suggested rollout order for these live in
> [docs/Archive/future-features.md](docs/Archive/future-features.md).

## Proposed guidelines
### Syntax
Widely inspired by modern languages like swift, rust, python, etc.

Some highlights of the v0.0 design: function definitions use `fun`; primitives
are explicitly sized integers (`int8`/`int16`/`int32`/`int64` and their `uint`
counterparts) with `int` as a built-in alias for `int32`; integer literals take
optional type suffixes (`255u8`, `123i64`); user-defined `typealias` is
supported; and declarations may carry built-in attributes (`#main` to mark the
entry point, `#test(inputs)[expected]` for inline tests run via `myla test`).

Documentation lives in the project wiki under [`docs/`](docs/Home.md), and work
is tracked as tasks under [`tasks/`](tasks/). Both are plain Markdown managed with
[Genbeya](https://github.com/genbeya/genbeya), so they read fine on GitHub and live
(with working `[[MYLA-12]]`-style references) in Genbeya:

- [Home](docs/Home.md) — overview and where to start
- [Getting started](docs/Getting-started.md) — run, build, test, bootstrap
- [Language](docs/Language.md) — the language reference, including the [grammar](docs/Language/Grammar.md)
- [Architecture](docs/Architecture.md) — the Python toolchain, the self-hosted compiler, editor tooling
- [Development](docs/Development.md) — testing, bootstrap, conventions
- [Project](docs/Project.md) — [roadmap](docs/Project/Roadmap.md), [decision log D1–D58](docs/Project/Decisions.md), [known issues](docs/Project/Known-issues.md)

The documents written during development (the v0.0 spec, grammar and architecture,
the self-hosting plan, the per-version v0.2–v0.5 designs, the feature catalog and
the open-questions tracker) are kept unchanged in the [Archive](docs/Archive.md).


### CLI (the Python toolchain — bootstrap stage0 + oracle)
```bash
uv sync
uv run myla.py <cmd>          # or: python3 myla.py <cmd>  (no third-party deps)

## Example commands:
# interpreter
uv run myla.py run myscript.my
# compiler (native x86-64 ELF via as/ld, no libc)
uv run myla.py build myscript.my -o myscript
# run inline #test cases
uv run myla.py test myscript.my
# repl (in the self-hosted CLI, which scripts/bootstrap.sh builds)
build/myla repl
```

### Self-hosting (the Myla-written compiler)

The compiler is now self-hosted: the toolchain under `selfhost/` (lexer →
parser → checker → x86-64 codegen) compiles its own source to a **byte-identical
fixed point**. Build it and verify the three-stage fixpoint with:

```bash
scripts/bootstrap.sh            # outputs to ./build (gitignored)
# build/gen_tool : selfhost compiler, built by the Python backend (stage1)
# build/stage2   : selfhost compiler, built by gen_tool
# build/stage3   : selfhost compiler, built by stage2 (stage2.s == stage3.s)
```

The self-hosted compiler emits assembly to stdout and takes the stdlib root as
its second argument; a thin host wrapper (the script above) runs `as`/`ld`:

```bash
build/stage3 examples/hello.my src/myla > hello.s
as --64 -o hello.o hello.s && ld -o hello hello.o && ./hello
```

See [Known issues](docs/Project/Known-issues.md) for current gaps (notably float
codegen) and the [Roadmap](docs/Project/Roadmap.md) for status.

### Testing convention

Every `.my` example (and, once we self-host, the compiler source itself) attaches
`#test(inputs)[expected]` cases to **every value-returning function**, turning each
file into its own regression suite runnable with `myla test`. Entry points and
void helpers are exempt since they cannot be unit-tested.

This is deliberately redundant with the Python test suite today, but it is what
keeps a self-hosted Myla honest: when the toolchain is written in Myla, these
in-language tests are how we detect that a change broke something. The
[examples burn test](tests/burn/test_examples_tests.py) enforces both halves of
the convention (all `#test` cases pass, and no value-returning function is left
untested).

### Regression corpus

Every language feature must appear in at least one runnable example, and every
known edge case, past bug, and intentional error must be captured by a program
the toolchain handles in a pinned way. Concretely:

- **Positive cases** live in `examples/*.my` — runnable programs with `#test`
  cases. Each is pinned to its stdout in
  [`test_examples_run.py`](tests/burn/test_examples_run.py) and compiled to
  native code and diffed against the interpreter in
  [`test_examples_compile.py`](tests/burn/test_examples_compile.py). A coverage
  check fails if an example lands without being registered in both.
- **Negative cases** live in `examples/errors/*.my` — programs that *must* be
  rejected. Each declares the diagnostic it expects with a directive comment:

```
//~ type error: cannot assign to an immutable binding
fun main() {
    let x = 1
    x = 2
}
```

The leading `<lex|parse|type|runtime> error` selects the pipeline stage that must
fail and the trailing text is a substring of the expected message.
[`test_error_corpus.py`](tests/burn/test_error_corpus.py) runs each through the
toolchain and asserts it fails in the right stage with the right message — so a
feature can neither silently *stop* rejecting bad input nor start failing for the
wrong reason. When a bug is fixed, add the program that triggered it: an accepted
program to `examples/regressions.my`, or a rejected one to `examples/errors/`.

## Roadmap

For live status (what is implemented, in progress, planned) and the running log
of design decisions, see the [Roadmap](docs/Project/Roadmap.md) and [Decisions](docs/Project/Decisions.md). High-level
milestone outline (all milestones below are **done** — the original
"v0.1 = self-host" framing was superseded by D23, which makes self-hosting the
v1.0 destination reached through the feature milestones):

| Milestone | Theme |
|-----------|-------|
| v0.0 | Python bootstrap toolchain: front end + tree-walking interpreter + x86-64 compiler (`myla run`/`test`/`build`) |
| v0.2 | Data modeling: `enum`+`match`, tuples, generics, `Option`/`Result` + `?` |
| v0.3 | Collections, strings & ops: lists/maps, string toolkit, refcounting, bitwise, casts, `const`, `assert` |
| v0.4 | Abstraction: methods/`impl`, lambdas/closures, pipelines, traits + operator overloading |
| v0.5 | Modules & runtime: imports + `std`, floats, `char`/UTF-8, freestanding I/O |
| v0.6–v0.9 | Self-hosting bring-up: port lexer → parser → checker → codegen to Myla, each differentially tested against the Python oracle |
| **v1.0** | **Self-hosted: Myla compiles Myla to a byte-identical three-stage fixed point** (`scripts/bootstrap.sh`) |

Post-1.0 ideas (custom operators, user macros, compound-assignment sugar) and the
known gaps in the self-hosted backend live in the [Roadmap](docs/Project/Roadmap.md)
and [Known issues](docs/Project/Known-issues.md).
