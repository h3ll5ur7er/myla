# Myla (Rust edition) — Architecture

A Cargo workspace with a shared front end feeding two back ends (an interpreter
and a native compiler), mirroring the original's "shared front end guarantees
parity" invariant.

```
source.my
   │
   ▼  myla-syntax
[ logos lexer ] → [ recursive-descent + Pratt parser ] → AST (+ spans)
   │
   ▼  myla-sema
[ symbol tables · entry point · prelude enums · mutability checks ] → Analyzed
   │
   ├─────────────► myla-interp  (tree-walking interpreter = reference semantics)
   │                    └── myla-runtime (ints, float fmt, channels, tasks)
   │
   └─────────────► myla-codegen (Cranelift) → object file → cc link → executable
                        └── tiny C print runtime
```

## Crates

| Crate | Responsibility |
| --- | --- |
| `myla-syntax` | `logos` token kinds, spans, AST, the hand-written parser (optional-semicolon rules, struct-literal/block disambiguation, f-string parsing), and positioned `Diagnostic`s with caret rendering. |
| `myla-sema` | Builds symbol tables (functions, structs, enums, actors, impl-method map, consts, aliases), registers the `Option`/`Result` prelude, resolves the entry point, validates attributes, and runs a mutability/assignability check. Deep static typing is intentionally light — the interpreter carries runtime types. |
| `myla-interp` | The tree-walking interpreter: the full value model, pattern matching, operator dispatch (incl. user operator overloading), closures, pipelines, `?`, the standard-library builtins, and concurrency. **This is the reference semantics.** |
| `myla-runtime` | Shared, back-end-agnostic runtime: `IntKind` wrapping arithmetic, round-trippable float formatting (`ryu`), and concurrency primitives (`Channel<T>`, `Task<T>`, `select`). |
| `myla-codegen` | The Cranelift native back end. Lowers the scalar/control-flow/function/print core to CLIF, emits an object via `cranelift-object`, and links it (plus a small C runtime) with `cc`. |
| `myla-cli` | The `myla` binary: `run`, `build`, `test`, `tokenize`, `parse`, `repl`. |

## Value model (interpreter)

`Value` is `Clone + Send + Sync`, so values move freely across task and channel
boundaries. Aggregates (`list`, `map`, `struct`, `tuple`, `enum`) share via
`Arc` and mutate copy-on-write with `Arc::make_mut`, giving value semantics
without O(n) copies for read-mostly data. Maps are insertion-ordered with a hash
index and accept **any** value as a key via structural `Eq` + `Hash`.

Control flow (`return`/`break`/`continue`), runtime errors, and `exit` are
threaded through evaluation as `Result<T, Control>`, so the `?` operator and
non-local exits compose naturally.

## Native back end scope

Cranelift lowering currently covers: top-level functions with scalar (`int`,
`float`, `bool`, `str`) parameters/returns, `let`/`var` locals, arithmetic /
comparison / bitwise operators, `if`/`else`, `while`, `for x in a..b`, direct
calls, and `print`. Floats use IEEE-754 `f64` and a round-trip C formatter so
native output matches the interpreter (verified by a differential test).

Constructs not yet lowered (closures, enums/match, collections, generics,
traits, concurrency) return a clear `unsupported` error from `myla build`, while
`myla run` executes the entire language. Extending the native back end with a
heap runtime (atomic-refcounted boxes for strings/lists/maps, the green-thread
scheduler) is the natural next step and is kept semantically identical to the
interpreter by construction.

## Testing

- Unit tests in `myla-syntax` (lexer/parser), `myla-runtime` (int wrapping), and
  `myla-interp` (end-to-end language features).
- Integration tests in `myla-cli/tests/cli.rs`:
  - example outputs match expected stdout,
  - **differential** interpreter-vs-native equality for the supported subset,
  - inline `#test` cases pass,
  - the negative corpus reports the expected error stage.
