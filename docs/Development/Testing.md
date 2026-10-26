# Testing

All tests use the standard library's `unittest`; there is no third-party test dependency. Each `tests/*/__init__.py` puts `src/` on the import path.

[TOC]

## Running

```bash
python3 -m unittest discover -s tests/unit -t .
python3 -m unittest discover -s tests/integration -t .
python3 -m unittest discover -s tests/burn -t .          # needs as/ld; about 30 seconds
python3 -m unittest tests.burn.test_error_corpus -v      # one file
```

`uv run pytest` works too when pytest is installed globally; it isn't a project dependency ([[MYLA-58]]).

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
| Unit | 411 | All pass, about 1.5 s |
| Integration | 4 | Pass (2 need pygls) |
| Burn | 340 (plus subtests) | All pass, about 33 s (green since [[MYLA-4]]) |

## Unit tests

`tests/unit/` has one file per area: lexer, parser, types, enums/match, tuples, methods, traits, generic traits, floats, chars, interpolation, imports, loader (including module errors and which file an error is attributed to), interpreter, stdio, fs, process, the language server's compiler adapter, and assembly-text checks for the compiler. `tests/integration/test_lsp_diagnostics.py` starts the language server and checks its diagnostics over stdio (skipped without pygls; CI installs it). The rest of the language server has no tests yet ([[MYLA-52]]).

## Burn tests

| File | Guarantees |
| --- | --- |
| `test_examples_run.py` | Every top-level `examples/*.my` prints exactly its pinned output under the interpreter; fails when an example is added or removed without updating the table |
| `test_examples_compile.py` | Each listed example builds natively, exits 0 and prints what the interpreter prints; the list must match the directory |
| `test_examples_tests.py` | Every `#test` case in the examples passes, and every non-generic value-returning top-level function has at least one |
| `test_error_corpus.py` | Each file in `examples/errors/` fails in the stage its directive names, with a message containing its text |
| `test_compiler_parity.py` | 88 targeted programs (wrapping, division, structs, methods, consts, collections and copy-on-write, stores into containers, strings, enums and reference counting, generics, `?`, closures, pipelines, traits, floats, chars) produce identical output natively; plus stress tests that allocate and drop millions of cells (lists, maps, builders, closures, partial application, trait dispatch, `?` early returns, values staged for a container store, `break`/`continue`) to prove memory is reclaimed, a timing guard that allocation never scans unusable free cells (MYLA-16), and trap tests for division by zero, `panic`, `assert` and `unreachable` |
| `test_debug_info.py` | `myla build -g` binaries carry a line table readelf reads, behave exactly like plain builds, and (where gdb is installed) stop on a Myla source line |
| `test_modules.py` | `examples/modules` in both back ends |
| `test_stdio.py`, `test_fs.py`, `test_process.py` | Parity of stdout, stderr, exit status, argv, file contents, errno mapping, signals and spawn errors |
| `test_selfhost_floatlit.py` | The self-hosted float literal conversion (`selfhost/floatlit.my`) gives the same double and float32 bits as Python on tricky and 800 random literals |
| `test_selfhost_lexer.py`, `…_parser.py`, `…_checker.py`, `…_interp.py`, `…_codegen.py` | The self-hosting gates: the Myla-written stages, built with the Python backend, agree with the Python oracle (canonical tokens, canonical AST, accept/reject with the error's position and message, interpreted output, native output); the checker gate also runs the programs the Python unit tests expect to fail (`tests/burn/data/type_error_snippets.json`, collected by `scripts/harvest_type_errors.py`) and a snippet for each remaining message; the lexer and parser gates also compare every lex and parse error (message and position) on the corpus, on snippets for each message, and on every line prefix of a few examples, which also proves the self-hosted parser stops after its first error; the interpreter gate also compares runtime errors (message, file, caret) and evaluation order with the Python CLI and runs the codegen gate's parity programs; the codegen and interpreter gates also run multi-module projects through the self-hosted loader (and the codegen gate checks that its diagnostics, lex and parse errors in imported modules included, print exactly as the Python CLI's), the codegen gate also runs the `test_compiler_parity.py` programs for bugs both backends had, and its arena-reclaim stress programs with a 30 MB peak-memory bound (measured from a minimal helper process: a child's peak RSS includes its parent's at fork) |

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
