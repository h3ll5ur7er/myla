# Testing

All tests use the standard library's `unittest`; there is no third-party test dependency. Each `tests/*/__init__.py` puts `src/` on the import path.

[TOC]

## Running

```bash
python3 -m unittest discover -s tests/unit -t .
python3 -m unittest discover -s tests/integration -t .
python3 -m unittest discover -s tests/burn -t .          # needs as/ld; about 25 seconds
python3 -m unittest tests.burn.test_error_corpus -v      # one file
```

`uv run pytest` works too when pytest is installed globally; it isn't a project dependency ([[MYLA-58]]).

The Rust edition has its own `cargo test` in `rust/` ([[Architecture/Rust-edition]]).

## Continuous integration

`.github/workflows/ci.yml` runs on pull requests and pushes to `master` ([[MYLA-69]]):

| Job | Runs |
| --- | --- |
| `unit` | Unit and integration tests on Python 3.12 and 3.13, with pygls for the language server test |
| `burn` | The burn suite (native builds with the runner's binutils) |
| `bootstrap` | `scripts/bootstrap.sh`, then the stage 3 compiler builds and runs `examples/hello.my` |

## Results (October 2026)

| Suite | Tests | Result |
| --- | --- | --- |
| Unit | 408 | All pass, about 1 s |
| Integration | 4 | Pass (2 need pygls) |
| Burn | 335 (plus subtests) | All pass, about 25 s (green since [[MYLA-4]]) |
| Rust (`cargo test`) | 20 | All pass |

## Unit tests

`tests/unit/` has one file per area: lexer, parser, types, enums/match, tuples, methods, traits, generic traits, floats, chars, interpolation, imports, loader (including module errors and which file an error is attributed to), interpreter, stdio, fs, process, the language server's compiler adapter, and assembly-text checks for the compiler. `tests/integration/test_lsp_diagnostics.py` starts the language server and checks its diagnostics over stdio (skipped without pygls; CI installs it). The rest of the language server has no tests yet ([[MYLA-52]]).

## Burn tests

| File | Guarantees |
| --- | --- |
| `test_examples_run.py` | Every top-level `examples/*.my` prints exactly its pinned output under the interpreter; fails when an example is added or removed without updating the table |
| `test_examples_compile.py` | Each listed example builds natively, exits 0 and prints what the interpreter prints; the list must match the directory |
| `test_examples_tests.py` | Every `#test` case in the examples passes, and every non-generic value-returning top-level function has at least one |
| `test_error_corpus.py` | Each file in `examples/errors/` fails in the stage its directive names, with a message containing its text |
| `test_compiler_parity.py` | 84 targeted programs (wrapping, division, structs, methods, consts, collections and copy-on-write, stores into containers, strings, enums and reference counting, generics, `?`, closures, pipelines, traits, floats, chars) produce identical output natively; plus stress tests that allocate and drop millions of cells (lists, maps, builders, closures, partial application, trait dispatch, `?` early returns, values staged for a container store, `break`/`continue`) to prove memory is reclaimed, a timing guard that allocation never scans unusable free cells (MYLA-16), and trap tests for division by zero, `panic`, `assert` and `unreachable` |
| `test_debug_info.py` | `myla build -g` binaries carry a line table readelf reads, behave exactly like plain builds, and (where gdb is installed) stop on a Myla source line |
| `test_modules.py` | `examples/modules` in both back ends |
| `test_stdio.py`, `test_fs.py`, `test_process.py` | Parity of stdout, stderr, exit status, argv, file contents, errno mapping, signals and spawn errors |
| `test_selfhost_lexer.py`, `…_parser.py`, `…_checker.py`, `…_interp.py`, `…_codegen.py` | The self-hosting gates: the Myla-written stages, built with the Python backend, agree with the Python oracle (canonical tokens, canonical AST, accept/reject and error position, interpreted output, native output); the codegen gate also runs the store programs of `test_compiler_parity.py` |

`tests/burn/_native.py` holds the helpers to build and run native binaries.

## The error corpus

Every file in `examples/errors/` starts with a directive naming the stage that must reject it and a substring of the message:

```
//~ type error: cannot assign to an immutable binding
fun main() {
    let x = 1
    x = 2
}
```

Stages are `lex`, `parse`, `type` and `runtime` (runtime cases run in the interpreter only). The corpus has 130 files: 10 lex, 9 parse, 107 type, 4 runtime. Module errors have no corpus stage yet; they are covered by `tests/unit/test_loader.py`.

## Adding tests

- A new feature gets an example in `examples/` with `#test` cases, registered in `test_examples_run.py` and `test_examples_compile.py`.
- A fixed bug gets a program: an accepted one in `examples/regressions.my` (or a parity case in `test_compiler_parity.py`), a rejected one in `examples/errors/`.
- Anything the native backend does differently from the interpreter belongs in `test_compiler_parity.py`.
