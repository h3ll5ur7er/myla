# Testing

All tests use the standard library's `unittest`, so they need nothing beyond Python. Each `tests/*/__init__.py` puts `src/` on the import path. pytest runs them as well and is in the `dev` dependency group ([[MYLA-58]]).

[TOC]

## Running

```bash
scripts/test.sh fast                                     # about 20 seconds once the tools are cached
scripts/test.sh                                          # every suite (all)
python3 -m unittest discover -s tests/unit -t .
python3 -m unittest discover -s tests/integration -t .
python3 -m unittest discover -s tests/burn -t .          # needs as/ld
python3 -m unittest tests.burn.test_error_corpus -v      # one file
uv run pytest tests/unit -q                              # pytest from the dev group
```

`scripts/test.sh fast` runs the unit and integration tests and the burn tests without the self-hosting gates (`tests/burn/test_selfhost_*`); use it while working and the full run before committing.

The burn tests build the self-hosted tools (`selfhost/<name>.my`, compiled by the Python backend) through `selfhost_tool(name)` in `tests/burn/_tools.py`, and other Myla programs such as the grammar tool through `myla_tool(path, name)`. A tool is cached as `build/test-tools/<name>-<hash>`, where the hash covers every source that can change it (`src/myla/**/*.py`, `src/myla/std/*.my`, `selfhost/*.my`, `tools/**/*.my`), so an edit to any of them rebuilds it and the stale copy is removed. The full burn run takes about 65 s with an empty cache and about 42 s with a warm one; when every module built its own tools it took 78 s, with fewer tests ([[MYLA-58]]).

## Continuous integration

`.github/workflows/ci.yml` runs on pull requests and pushes to `master` ([[MYLA-69]]):

| Job | Runs |
| --- | --- |
| `unit` | Unit and integration tests on Python 3.12 and 3.13 |
| `burn` | The burn suite (native builds with the runner's binutils), with Node and the tree-sitter CLI for `test_grammar.py` (Node also runs the VS Code extension's server choice in `test_lsp.py`) |
| `bootstrap` | `scripts/bootstrap.sh`, then the stage 3 compiler builds and runs `examples/hello.my` |

## Results (October 2026)

| Suite | Tests | Result |
| --- | --- | --- |
| Unit | 479 | All pass, about 2 s |
| Integration | 2 | Pass |
| Burn | 544 (plus subtests) | All pass, about 190 s with cached tools (green since [[MYLA-4]]) |

## Unit tests

`tests/unit/` has one file per area: lexer, parser, types, enums/match, tuples, methods, traits, generic traits, floats, chars, interpolation, imports, loader (including module errors and which file an error is attributed to), interpreter, stdio, fs, process, toml, the VS Code extension's grammar and snippets, and assembly-text checks for the compiler. `tests/integration/` parses every example. The language server's scenarios are in `tests/burn/_lsp_scenarios.py`, run by `tests/burn/test_lsp.py` (they also ran against the Python server until it was retired, [[MYLA-83]]).

## Burn tests

| File | Guarantees |
| --- | --- |
| `test_examples_run.py` | Every top-level `examples/*.my` prints exactly its pinned output under the interpreter; fails when an example is added or removed without updating the table |
| `test_examples_compile.py` | Each listed example builds natively, exits 0 and prints what the interpreter prints; the list must match the directory |
| `test_examples_tests.py` | Every `#test` case in the examples passes, and every non-generic value-returning top-level function has at least one |
| `test_error_corpus.py` | Each file in `examples/errors/` fails in the stage its directive names, with a message containing its text; runtime errors also fail natively with the message their `native` directive names |
| `test_compiler_parity.py` | 104 targeted programs (wrapping, division, structs, methods, consts, collections and copy-on-write, stores into containers, strings and byte ranges, enums and reference counting, generics, `?`, closures, pipelines, traits, floats, chars) produce identical output natively; plus stress tests that allocate and drop millions of cells (lists, maps, builders, closures, partial application, trait dispatch, `?` early returns, values staged for a container store, `break`/`continue`, strings (concatenation, `format`, builders, map keys), match results, temporaries of a match scrutinee left early and of conditions, guards and `&&`/`||` operands) to prove memory is reclaimed, a timing guard that allocation never scans unusable free cells (MYLA-16), and trap tests for division by zero, `panic`, `assert` and `unreachable` |
| `test_debug_info.py` | `myla build -g` binaries carry a line table readelf reads, behave exactly like plain builds, and (where gdb is installed) stop on a Myla source line |
| `test_modules.py` | `examples/modules` in both back ends |
| `test_stdio.py`, `test_fs.py`, `test_process.py` | Parity of stdout, stderr, exit status, argv, file contents, errno mapping, signals and spawn errors; `test_fs.py` also runs the directory functions of `std.fs` ([[MYLA-88]]) in all four implementations, each in a fresh working directory (every function and error, and a directory of 655 names up to 255 bytes long) |
| `test_json.py` | `std.json` and `std.num` against Python's `json` ([[MYLA-79]]): a Myla driver parses length-framed texts from stdin and writes them back; on 3,000 random values (compact UTF-8 and indented ASCII with `\u` escapes, strings with escapes and astral characters, int64 limits, random float bit patterns) its output equals Python's re-serialization, so floats come out in their shortest repr; on 3,000 broken texts it fails where Python does, with Python 3.13's message, line and column; 5,000 floats; the nesting limit; both native builds, and a small corpus in both interpreters; and the modules' own `#test` cases |
| `test_toml.py` | `std.toml` against Python's `tomllib` ([[MYLA-89]]): a Myla driver parses length-framed documents and prints them as JSON; on 3,000 generated documents of the subset (tables, quoted and dotted headers, every kind of key, strings with escapes and astral characters, int64 limits, string arrays over several lines, nested inline tables, comments, CRLF) and 4,000 broken ones, it rejects what `tomllib` rejects, and otherwise gives `tomllib`'s value or rejects the document as outside the subset; both native builds, and a small corpus in both interpreters |
| `test_lsp.py` | The language server written in Myla ([[MYLA-80]]), built by the Python backend and by the self-hosted one: the diagnostics scenarios of `tests/burn/_lsp_scenarios.py` (errors in imported modules published for them and cleared, unsaved text of the document and of other open documents, UTF-16 ranges, parse errors, unknown methods, shutdown and exit) and its request scenarios (symbols, definition, references, hover, completion), a malformed message, a burst of 38 changes checked once, RSS flat over 200 checks, the last good parse after lex and parse errors, the `.` completion trigger, added and removed workspace folders, a watched file changing, semantic tokens (a classified sample, UTF-16 offsets, and every example and compiler source covered: tokens sorted, apart, within their lines, matching their type, and every character but white space and punctuation in one), its own `#test` cases, resolution by scope, imports and type (scenarios, and corpus tests: every declared name resolves, member accesses agree with the Python checker, both builds print the same), completion by type, and the VS Code extension's server command |
| `test_stdin.py` | Reading with `std.io` ([[MYLA-78]]): the Python interpreter, the Python native backend, the self-hosted interpreter and the self-hosted native backend print the same for the same bytes on a pipe (lines, CRLF, no input, 100 KB across chunk boundaries, Content-Length framing with a cut-off message, binary input echoed back, a bad descriptor), and each answers an interactive exchange line by line, run without `PYTHONUNBUFFERED`, so output is out before a read |
| `test_grammar.py` | [[grammar/myla.ebnf]] and what is generated from it ([[MYLA-77]]): the wiki page [[Language/Grammar]] shows the same rules; `grammar.js` and `highlights.scm` in `editor/tree-sitter-myla/` are current; the self-hosted parser accepts 10,000 programs sampled from the grammar; `keywords()` in `selfhost/tokens.my`, which the grammar must use in full, matches the Python lexer's table; the grammar tool's `#test` cases pass. With the tree-sitter CLI (`npm install` in `editor/tree-sitter-myla`, or `TREE_SITTER`) and `cc`, also: `src/` is current, tree-sitter parses every `.my` file of the repository and 2,000 samples without an ERROR or MISSING node, every lex and parse error of the error corpus gives one, and the queries compile; skipped without the CLI, CI installs it |
| `test_selfhost_cli.py` | The self-hosted `build/myla` in a checkout's layout (stdlib found from the binary): `run`, `test`, `build`, `repl` ([[MYLA-82]]: a scripted session's values, errors against the input's lines, `exit`); and `myla test` parity with the Python CLI ([[MYLA-81]]): the same stdout and exit status on every example, compiler, tool and stdlib source with `#test`s, and on a program failing in every way (value reprs, runtime errors, `exit`, output from tests) |
| `test_selfhost_floatlit.py` | The self-hosted float literal conversion (`std.num`'s `f64_literal_bits`, through `selfhost/floatlit_main.my`) gives the same double and float32 bits as Python on tricky and 800 random literals |
| `test_selfhost_lexer.py`, `…_parser.py`, `…_checker.py`, `…_interp.py`, `…_codegen.py` | The self-hosting gates: the Myla-written stages, built with the Python backend, agree with the Python oracle (canonical tokens, canonical AST, accept/reject with the error's position and message, interpreted output, native output); the checker gate also runs the programs the Python unit tests expect to fail (`tests/burn/data/type_error_snippets.json`, collected by `scripts/harvest_type_errors.py`) and a snippet for each remaining message; the lexer and parser gates also compare every lex and parse error (message and position) on the corpus, on snippets for each message, and on every line prefix of a few examples, which also proves the self-hosted parser stops after its first error; the interpreter gate also compares runtime errors (message, file, caret) and evaluation order with the Python CLI, runs the codegen gate's parity programs, and checks that `push`, element assignment and updates inside `var self` methods and nested lists scale linearly ([[MYLA-74]]); the codegen and interpreter gates also run multi-module projects through the self-hosted loader (and the codegen gate checks that its diagnostics, lex and parse errors in imported modules included, print exactly as the Python CLI's), the codegen gate also runs the `test_compiler_parity.py` programs for bugs both backends had, and its arena-reclaim stress programs with a 30 MB peak-memory bound (measured from a minimal helper process: a child's peak RSS includes its parent's at fork) |

`tests/burn/_native.py` holds the helpers to build and run native binaries, `tests/burn/_tools.py` the cache of self-hosted tools.

## The error corpus

Every file in `examples/errors/` starts with a directive naming the stage that must reject it and a substring of the message:

```
//~ type error: cannot assign to an immutable binding
fun main() {
    let x = 1
    x = 2
}
```

Stages are `lex`, `parse`, `module`, `type` and `runtime`. A `module` case goes through the loader with the bundled standard library. A `runtime` case runs in the interpreter and is also built with the Python backend; it needs a second directive with what the native binary prints on stderr (its messages have no values in them, [[MYLA-17]]), and the binary must exit with status 1:

```
//~ runtime error: map key 2 not found
//~ native: runtime error: map key not found
```

The corpus has 133 files: 10 lex, 9 parse, 2 module, 108 type, 4 runtime. More module errors (cycles, which file an error is attributed to) are covered by `tests/unit/test_loader.py`.

## Adding tests

- A new feature gets an example in `examples/` with `#test` cases, registered in `test_examples_run.py` and `test_examples_compile.py`.
- A fixed bug gets a program: an accepted one in `examples/regressions.my` (or a parity case in `test_compiler_parity.py`), a rejected one in `examples/errors/`.
- Anything the native backend does differently from the interpreter belongs in `test_compiler_parity.py`.
