# Myla (Rust edition)

An independent reimplementation of the **Myla** programming language in Rust,
built with powerful crates instead of the original "no dependencies, no libc"
constraint. The Python / self-hosted implementation in the parent repository is
**inspiration only** — this is a clean-room design that fixes the pain points we
discovered and adds a bonus concurrency model.

> Myla = "my language" (and the name of my daughter).

## What's here

```
rust/
├── crates/
│   ├── myla-syntax/    logos lexer · AST · recursive-descent + Pratt parser · diagnostics
│   ├── myla-sema/      symbol tables · entry-point resolution · mutability checks
│   ├── myla-interp/    tree-walking interpreter (the reference semantics)
│   ├── myla-runtime/   sized-int arithmetic · float formatting · concurrency primitives
│   ├── myla-codegen/   Cranelift native back end (object file → linked executable)
│   └── myla-cli/       the `myla` binary
├── docs/               language spec, grammar, architecture, concurrency, stdlib
└── examples/           runnable programs + a negative (error) corpus
```

## Quick start

```bash
cd rust
cargo build

# interpret a program (full language)
cargo run -p myla-cli -- run examples/enums.my

# compile to a native executable (scalar/control-flow/function core)
cargo run -p myla-cli -- build examples/fib.my -o build/fib
./build/fib

# run inline #test(...)[...] cases
cargo run -p myla-cli -- test examples/fib.my

# explore
cargo run -p myla-cli -- tokenize examples/hello.my
cargo run -p myla-cli -- parse examples/hello.my
cargo run -p myla-cli -- repl
```

## Headline improvements over the original

| Pain point in the original | Fix here |
| --- | --- |
| Strict one-statement-per-line | **Optional semicolons**: a statement ends at a newline *or* `;`. Newlines inside `()`/`[]`, after a trailing binary operator, or before a leading `.`/`\|>`/`?` do not terminate. |
| Floats unimplemented in codegen | **Floats are first-class** in the interpreter *and* the native back end (`float32`/`float64`, `f32`/`f64` suffixes, round-trippable printing via `ryu`). |
| Map keys limited to scalar-sized values | **Arbitrary keys**: any value (structs, tuples, strings, enums) can be a map key via structural `Eq` + `Hash`. |
| Very limited I/O (no file write, no subprocesses) | **Rich I/O**: file read/write/append, `run` subprocesses with captured output, `args`, `env_var`, `now_millis`, stdin. |
| (new) | **Bonus concurrency**: Go/Swift-inspired `spawn`/`go`, channels + `select`, `async`/`await`, and `actor`s. |

## Backends

- **Interpreter** (`myla run`) — the complete language and the reference
  semantics: generics (by erasure), traits + operator overloading, closures,
  pipelines, pattern matching, `Option`/`Result` + `?`, collections, the full
  standard library, and concurrency.
- **Native** (`myla build`) — a Cranelift back end that lowers the
  scalar/control-flow/function/print core to a real executable, linked with a
  tiny C runtime. Constructs it does not yet lower report a clear `unsupported`
  message; `myla run` always handles the whole language. A differential test
  asserts native output matches the interpreter for the supported subset.

See [`docs/`](docs/) for the language specification, grammar, architecture,
concurrency model, and standard library reference.
