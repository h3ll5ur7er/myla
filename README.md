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
> [docs/future-features.md](docs/future-features.md).

## Proposed guidelines
### Syntax
Widely inspired by modern languages like swift, rust, python, etc.

Some highlights of the v0.0 design: function definitions use `fun`; primitives
are explicitly sized integers (`int8`/`int16`/`int32`/`int64` and their `uint`
counterparts) with `int` as a built-in alias for `int32`; integer literals take
optional type suffixes (`255u8`, `123i64`); user-defined `typealias` is
supported; and declarations may carry built-in attributes (`#main` to mark the
entry point, `#test(inputs)[expected]` for inline tests run via `myla test`).

Design docs:
- [docs/language-spec.md](docs/language-spec.md) — v0.0 concrete syntax & semantics
- [docs/grammar.md](docs/grammar.md) — v0.0 formal EBNF grammar
- [docs/architecture.md](docs/architecture.md) — toolchain architecture (interpreter + x86-64 compiler)
- [docs/future-features.md](docs/future-features.md) — proposals for post-v0.0 features
- [docs/self-hosting.md](docs/self-hosting.md) — the road to v1.0: feature gap analysis + milestone plan
- [docs/v0.2-data-modeling.md](docs/v0.2-data-modeling.md) — detailed v0.2 design: enums, `match`, tuples, generics, `Option`/`Result` + `?`
- [docs/v0.3-collections-and-ops.md](docs/v0.3-collections-and-ops.md) — detailed v0.3 design: collections, strings, bitwise/shift, casts, literal bases, `break`/`continue`, `const`, `assert`/`panic`/`unreachable` (**v0.3 complete**: operators & literals, const/intrinsics, lists `[T]`, maps `[K: V]`, and the string toolkit — char literals, byte indexing, `+` concat, `format`, `StringBuilder`)
- [docs/roadmap.md](docs/roadmap.md) — live implementation status, progress, and decision log
- [docs/clarification_needed.md](docs/clarification_needed.md) — open decisions awaiting input


### CLI
```bash
# pre-bootstrapping phase
uv sync 
uv run myla.py <cmd>

# bootstrapping phase
uv sync 
uv run myla.py build myla.my -o myla-bs
myla-bs build myla.my -o myla
myla run <cmd>

## Example commands:
# repl
myla repl
# interpreter
myla run myscript.my
# compiler
myla build myscript.my -o myscript
# run inline #test cases
myla test myscript.my
```

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

> For live status (what is implemented, in progress, planned) and the running
> log of design decisions, see [docs/roadmap.md](docs/roadmap.md). The section
> below is the high-level milestone outline.

### v0.0

v0.0 will be implemented in python to support a minimal set of functionality.

- Define v0.0 syntax
    - variables
    - loops
    - flow-control
    - structs
    - functions
- implement tokenization + lexing for v0.0 in python 
- implement parsing for v0.0 in python 
- implement interprete for v0.0 in python
- implement compiler for v0.0 in python that produces native code (e.g. x86 assembly or arm64)

#### Deliverable
- myla.py (bootstrapping compiler)

#### v0.0 milestones
##### v0.0.0 architecture and design
    - clear, simple, well documented software architecture
    - clear, simple, well documented language grammer
##### v0.0.1 setup and scaffolding
    - create a directory structure to hold both our python bootstrapping compiler, test files (burn, unit and integration)
    - created one .my file per major feature, acting as burn-tests
##### v0.0.2 working interpreter
    - can interpret a *.my file in the commandline
    - interpreter can run all burn-test .my files successfuly
    - full python unit- and integration test coverage
    - everything documented
##### v0.0.3 working compiler
    - compiler can compile .my files into x86 assembly
    - compiled my files can be executed and produce the same result as if they were interpreted


### v0.1

v0.1 will implement the exact same feature-set in the myla language itself. This is where we will start self-hosting the compiler.

- implement tokenization + lexing for v0.0 in myla 
- implement parsing for v0.0 in myla 
- implement interprete for v0.0 in myla
- implement compiler for v0.0 in myla that produces native code (e.g. x86 assembly or arm64)

#### Deliverable
- myla.my (self-hosted compiler)
#### v0.1 milestones
##### v0.1.0 working interpreter
    - interpreted bootstrap compiler (v0.0, written in python) can interpret a *.my file in the commandline
    - interpreter can run all burn-test .my files successfuly
##### v0.1.1 self-hosted interpreter
    - interpreted bootstrap compiler (v0.0, written in python) can interpret myla.my, basically self-hosting the interpreter
    - self-hosted interpreter can run all burn-test .my files successfuly
##### v0.1.2 working compiler
    - compiler can compile .my files into x86 assembly
    - compiled my files can be executed and produce the same result as if they were interpreted
##### v0.1.3 self-hosted compiler
    - compiler can compile myla.my into x86 assembly
    - the self-hosted compiler can build itself.

