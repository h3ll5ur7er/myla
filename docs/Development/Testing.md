# Testing

The tests are the burn tests in `tests/burn/`: modules of the standard library's `unittest` that drive the self-hosted toolchain, so they need nothing beyond Python, `as` and `ld` (gdb, node and the tree-sitter CLI for some, skipped without them). pytest runs them as well and is in the `dev` dependency group ([[MYLA-58]]). Python only runs the tests; it builds nothing. Until the Python toolchain was retired ([[MYLA-219]], D101) there were also unit and integration tests of it (`tests/unit/`, `tests/integration/`).

[TOC]

## Running

```bash
scripts/test.sh fast                                     # about 20 seconds once the tools are cached (the quick burn modules)
scripts/test.sh                                          # every burn test (all)
python3 -m unittest discover -s tests/burn -t .          # the same
python3 -m unittest tests.burn.test_error_corpus -v      # one file
uv run pytest tests/burn -q                              # pytest from the dev group
```

`scripts/test.sh fast` runs the burn tests without the self-hosting gates (`tests/burn/test_selfhost_*`) and every module of 4 s or more ([[MYLA-153]]); use it while working and the full run before committing.

The burn tests build everything with the self-hosted compiler ([[MYLA-235]]). `tests/burn/_tools.py` bootstraps the compiler of the current sources from the seed (`bootstrap/seed.s` assembled is stage 0, it compiles the compiler, which compiles it again: at the fixed point the same as `build/stage3`, [[MYLA-218]]) and builds the self-hosted tools (`selfhost/<name>.my`) with it through `selfhost_tool(name)`, other Myla programs such as the grammar tool and the language server through `myla_tool(path, name)`, as `scripts/bootstrap.sh` does; `tests/burn/_native.py` builds the test programs with the natively built CLI (`myla build`). A tool is cached as `build/test-tools/<name>-selfhost-<hash>`, where the hash covers every source that can change it (`bootstrap/seed.s`, `lib/std/*.my`, `selfhost/*.my`, `tools/**/*.my`), so an edit to any of them rebuilds it and the stale copy is removed. The whole suite takes about 2 minutes in one process with the tools cached (836 tests in 121 s on 4 cores, measured on 2026-11-01 after [[MYLA-219]]); building the tools adds about a minute to a cold run.

## Recorded answers

Until [[MYLA-219]] the burn tests compared the self-hosted toolchain with the Python toolchain, asking its lexer, parser, checker, loader, interpreter and CLI what a program's tokens, tree, errors, warnings and output are. Before it was removed, its answer to every question the tests asked was recorded into `tests/burn/data/golden/<name>.json.gz` (4.1 MB), and the functions that asked it, marked `@golden("name")` (`tests/burn/_golden.py`, whose docstring has the details), now answer from there. A question is keyed by the function and its arguments, a file in an argument standing for its content:

- A question about a changed file of `selfhost/`, `tools/` or `lib/std/`, which change all the time, is skipped when it has no answer; the skip count shows how much of that corpus has changed since the answers were recorded.
- Any other question without an answer (a new or changed example, a new snippet) fails, saying so: give that test an expectation of its own.
- The repository's path and temporary directories are stored as placeholders, so a checkout elsewhere (CI) replays the same answers.

`MYLA_GOLDEN=record` records the answers again; it works only on a checkout that still has the Python toolchain, the branch `backup/python-toolchain-final` ([[Development/Bootstrap]]).

So the self-hosted interpreter and native code built by the self-hosted compiler are tested against each other and against the retired toolchain's answers: the interpreter gate compares `interp_main` with the Python interpreter's recorded output, and the native suites (`test_examples_compile.py`, `test_compiler_parity.py`, the runtime and I/O tests) compare binaries with it too. The 97 single-module programs the Python unit tests ran through the interpreter are kept, with what they printed and their exit status or runtime error, in `tests/burn/data/unit_programs.json`, and run in the self-hosted interpreter and natively (`test_unit_programs.py`). The comparisons with the Python backend's binaries went with it, as did the tests that only exercised the Python toolchain.

## Continuous integration

`.github/workflows/ci.yml` runs on pull requests and pushes to `master` ([[MYLA-69]]); the README shows the state of `master` as a badge:

[![CI](https://github.com/h3ll5ur7er/myla/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/h3ll5ur7er/myla/actions/workflows/ci.yml)

The jobs run on `ubuntu-24.04` (pinned: `ubuntu-latest` moves, and the burn job relies on that runner's Python 3.12), with the actions at their Node 24 versions:

| Job | Runs |
| --- | --- |
| `burn` | The burn suite (native builds with the runner's binutils) on the runner's own Python 3.12, with gdb for the debug-information and debugger tests (on `actions/setup-python` gdb would embed its libpython and the pretty-printers wouldn't run, [[MYLA-156]]), Node and the tree-sitter CLI for `test_grammar.py` (Node also runs the VS Code extension's server choice in `test_lsp.py`); `build/test-tools` and the npm install are cached; the compiler the tests use is bootstrapped from the seed |
| `bootstrap` | Without Python: `scripts/bootstrap.sh` from the seed (stages 0 to 3, the fixed point, `build/myla`, `build/myla-lsp`), `scripts/check-seed.sh` (fails a pull request whose seed isn't the compiler of its sources), then the stage 3 compiler builds and runs `examples/hello.my` ([[Development/Bootstrap]]) |
| `vscode-extension` | `scripts/bootstrap.sh` for `build/myla`, then in `vscode-extension/myla`, with Node 22, gdb and the runner's own Python (`actions/setup-python` would point gdb at its libpython, and the binaries' pretty-printers wouldn't run, D82): `npm ci`, `npm run typecheck`, `npm run lint`, `npm test` (the extension's tests, the debugger against gdb with `build/myla build -g` building), `npx vsce package`; uploads the `.vsix` as the artifact `myla-vscode-extension` ([[MYLA-101]]) |

## Results (November 2026)

| Suite | Tests | Result |
| --- | --- | --- |
| Burn | 836 (plus subtests, 24 skipped) | All pass (but `test_native_runtime.py`'s stack overflow on a worker is flaky: in one of six runs the error was printed twice); about 120 s in one process with the tools cached, the compiler bootstrapped from the seed and every program built by it |
| `#test` cases in `selfhost/` | on 1,030 of 1,286 value-returning functions (80 %) | `myla test` passes every one ([[MYLA-184]]) |

## What the Python tests covered

`tests/unit/` (627 tests) and `tests/integration/` (every example parses) tested the Python toolchain module by module; they went with it ([[MYLA-219]]). What they covered of the language survives as the 97 programs of `test_unit_programs.py` (see "Recorded answers"), the error corpus, the examples and the self-hosting gates. The language server's scenarios are in `tests/burn/_lsp_scenarios.py`, run by `tests/burn/test_lsp.py` (they also ran against the Python server until it was retired, [[MYLA-83]]).

## Burn tests

| File | Guarantees |
| --- | --- |
| `test_examples_run.py` | Every top-level `examples/*.my` prints exactly its pinned output under the self-hosted interpreter (`myla run`); fails when an example is added or removed without updating the table |
| `test_examples_compile.py` | Each listed example builds natively, exits 0 and prints what the interpreter printed (the Python interpreter's recorded output); the list must match the directory |
| `test_examples_tests.py` | Every `#test` case in the examples passes, and every non-generic value-returning top-level function has at least one |
| `test_error_corpus.py` | Each file in `examples/errors/` fails in the stage its directive names, with a message containing its text, and underlines the text its `span` directive names; it reports one error, or as many as its `errors` directive says, the later ones containing the texts of its `next` directives (D80); runtime errors also fail natively with the message their `native` directive names. The diagnostics checked are the Python toolchain's, recorded: a file added or changed since has none, and its test fails until it gets an expectation of its own |
| `test_compiler_parity.py` | 104 targeted programs, natively against the interpreter's recorded output (wrapping, division, structs, methods, consts, collections and copy-on-write, stores into containers, strings and byte ranges, enums and reference counting, generics, `?`, closures, pipelines, traits, floats, chars) produce identical output natively; plus stress tests that allocate and drop millions of cells (lists, maps, builders, closures, partial application, trait dispatch, `?` early returns, values staged for a container store, `break`/`continue`, strings (concatenation, `format`, builders, map keys), match results, temporaries of a match scrutinee left early and of conditions, guards and `&&`/`||` operands) to prove memory is reclaimed, a timing guard that allocation never scans unusable free cells (MYLA-16), and trap tests for division by zero, `panic`, `assert` and `unreachable` |
| `test_declaration_recovery.py` | The checker goes on after a declaration's error (D84, [[MYLA-110]]): 674 mutants of the single-file examples, each with one parameter, return, field, payload, const, alias or impl target type made unknown or one function, struct or enum declared twice (`tests/burn/_mutants.py`), report exactly that error and nothing that follows from it; the checker gate compares the self-hosted checker on the same mutants |
| `test_debug_info.py` | `myla build -g` binaries carry a line table readelf reads, behave exactly like plain builds, and (where gdb is installed) stop on a Myla source line; gdb shows parameters and locals of every scalar type, values while stepping, shadowed and scoped names, strings, lists, structs, tuples, enums, builders, maps, parameters passed by address, `self`, a lambda's parameter and capture, and `set var` writes a value the program reads ([[MYLA-66]]); the abbreviation table is the one the Python backend wrote (recorded) |
| `test_native_runtime.py` | The native runtime ([[MYLA-17]], [[MYLA-65]]): every kind of runtime error prints `runtime error: <message>` and the interpreter's `  --> file:line:col` (the Python interpreter's, recorded) (also in an imported module's function, method and lambda), and no output is lost on a non-blocking pipe |
| `test_modules.py` | `examples/modules` in the self-hosted interpreter and natively, the native output also against the Python interpreter's recorded one |
| `test_project.py` | The project model ([[MYLA-93]]) through `selfhost/project_main.my`: every manifest and lock-file error once, transitive path dependencies, cycles, the one-version rule, Git dependencies locked and checked out (by hand), unlocked, or not checked out yet, lock files round-tripping; a few scenarios also in the self-hosted interpreter and in the driver compiled by `gen_main` |
| `test_project_commands.py` | The project commands of `build/myla` ([[MYLA-94]]): `myla new` and `build`, `run`, `test`, `check`, `clean` on the project it creates; a project with a path dependency and a nested module (arguments, a run from a subdirectory, `-g`, each file's own `#test` cases, a library without a program, file mode reading no manifest); errors: no manifest, a manifest error, compile errors with project-relative paths, a Git dependency not checked out |
| `test_project_fetch.py` | Git dependencies and `myla fetch` ([[MYLA-95]]), with local repositories through `file://` URLs: lightweight and annotated tags, a branch that moves only with `--update`, the default branch, a `rev`, commands checking out locked commits (an interrupted `.partial` checkout cloned again), a dependency of a dependency, `clean --deps`, errors (an unknown tag, a repository that doesn't exist, a commit that doesn't exist, two versions of a package), no lock file without Git dependencies |
| `test_packages.py` | Packages (`--package name=dir`, [[MYLA-92]]): a project with two packages (a package root re-exporting through relative imports, a nested directory, one package importing the other) runs, tests and builds alike in `build/myla`, `interp_main` and `gen_main`, its tests printing what the Python CLI printed; a nested entry with a project root resolves alike; every package error (shadowing, unresolved, no root module, ambiguous, errors inside a package's modules, the package list's and the flag's errors) prints exactly the Python loader's diagnostic (the Python CLI's and loader's answers are recorded) |
| `test_stdio.py`, `test_fs.py`, `test_process.py` | Native builds against the interpreter (the Python interpreter's recorded answers): stdout, stderr, exit status, argv, file contents, errno mapping, signals and spawn errors; `test_fs.py` also runs the directory functions of `std.fs` ([[MYLA-88]]) in the self-hosted interpreter and natively, each in a fresh working directory (every function and error, and a directory of 655 names up to 255 bytes long) |
| `test_json.py` | `std.json` and `std.num` against Python's `json` ([[MYLA-79]]): a Myla driver parses length-framed texts from stdin and writes them back; on 3,000 random values (compact UTF-8 and indented ASCII with `\u` escapes, strings with escapes and astral characters, int64 limits, random float bit patterns) its output equals Python's re-serialization, so floats come out in their shortest repr; on 3,000 broken texts it fails where Python does, with Python 3.13's message, line and column; 5,000 floats; the nesting limit; the big corpus natively, a small one in the self-hosted interpreter; and the modules' own `#test` cases |
| `test_toml.py` | `std.toml` against Python's `tomllib` ([[MYLA-89]]): a Myla driver parses length-framed documents and prints them as JSON; on 3,000 generated documents of the subset (tables, quoted and dotted headers, every kind of key, strings with escapes and astral characters, int64 limits, string arrays over several lines, nested inline tables, comments, CRLF) and 4,000 broken ones, it rejects what `tomllib` rejects, and otherwise gives `tomllib`'s value or rejects the document as outside the subset; the big corpus natively, a small one in the self-hosted interpreter |
| `test_lsp.py` | The language server written in Myla ([[MYLA-80]]), in the cached tool build and in one built by `gen_main` as `scripts/bootstrap.sh` builds `build/myla-lsp`: the diagnostics scenarios of `tests/burn/_lsp_scenarios.py` (errors in imported modules published for them and cleared, unsaved text of the document and of other open documents, UTF-16 ranges, parse errors, every error of a check, in one file and in two (D80), unknown methods, shutdown and exit) and its request scenarios (symbols, definition, references, hover, completion), a malformed message, a burst of 38 changes checked once, RSS flat over 200 checks, the last good parse after lex and parse errors, the `.` completion trigger, added and removed workspace folders, a watched file changing, semantic tokens (a classified sample, UTF-16 offsets, and every example and compiler source covered: tokens sorted, apart, within their lines, matching their type, and every character but white space and punctuation in one), its own `#test` cases, projects ([[MYLA-97]]: a path dependency outside the workspace with diagnostics, definition, hover, references and completion into it, a nested file under `src/`, Git dependencies checked out or not, a manifest error and its fix), the workspace scan skipping `build/`, `.myla/`, `.git/` and `node_modules/`, resolution by scope, imports and type (scenarios, and corpus tests: every declared name resolves, member accesses agree with the Python checker's recorded answers, both builds print the same), completion by type, and the VS Code extension's server command |
| `test_vscode_debugger.py` | The VS Code extension's debug adapter against real gdb ([[MYLA-99]]): its integration test (`test/integration/adapter.test.ts`) run with the self-hosted CLI building the programs with `-g`; skipped without gdb or node 22.6+ |
| `test_stdin.py` | Reading with `std.io` ([[MYLA-78]]): the self-hosted interpreter and native backend print the same for the same bytes on a pipe (where a test has no expectation of its own, what the Python interpreter printed, recorded) (lines, CRLF, no input, 100 KB across chunk boundaries, Content-Length framing with a cut-off message, binary input echoed back, a bad descriptor), and each answers an interactive exchange line by line, run without `PYTHONUNBUFFERED`, so output is out before a read |
| `test_grammar.py` | [[grammar/myla.ebnf]] and what is generated from it ([[MYLA-77]]): the wiki page [[Language/Grammar]] shows the same rules; `grammar.js` and `highlights.scm` in `editor/tree-sitter-myla/` are current; the self-hosted parser accepts 10,000 programs sampled from the grammar; `keywords()` in `selfhost/tokens.my`, which the grammar must use in full, matches the Python lexer's table (recorded); the grammar tool's `#test` cases pass. With the tree-sitter CLI (`npm install` in `editor/tree-sitter-myla`, or `TREE_SITTER`) and `cc`, also: `src/` is current, tree-sitter parses every `.my` file of the repository and 2,000 samples without an ERROR or MISSING node, every lex and parse error of the error corpus gives one, and the queries compile; skipped without the CLI, CI installs it |
| `test_selfhost_cli.py` | The self-hosted `build/myla` in a checkout's layout (stdlib found from the binary): `run`, `test`, `build`, `repl` ([[MYLA-82]]: a scripted session's values, errors against the input's lines, `exit`); and `myla test` parity with the Python CLI's recorded output ([[MYLA-81]]): the same stdout and exit status on every example, compiler, tool and stdlib source with `#test`s, and on a program failing in every way (value reprs, runtime errors, `exit`, output from tests) |
| `test_selfhost_floatlit.py` | The self-hosted float literal conversion (`std.num`'s `f64_literal_bits`, through `selfhost/floatlit_main.my`) gives the same double and float32 bits as Python's `float` and `struct` on tricky and 800 random literals |
| `test_unit_programs.py` | The 97 programs the Python unit tests ran ([[MYLA-219]], `tests/burn/data/unit_programs.json`) give their recorded output and exit status in the self-hosted interpreter and natively, and the interpreter their runtime error |
| `test_selfhost_lexer.py`, `…_parser.py`, `…_checker.py`, `…_interp.py`, `…_codegen.py` | The self-hosting gates: the Myla-written stages, built by the self-hosted compiler, agree with the retired Python toolchain's recorded answers (canonical tokens with their ends, canonical AST, accept/reject with the error's position, range and message, interpreted output, native output); the checker gate also runs the programs the Python unit tests expected to fail (`tests/burn/data/type_error_snippets.json`, collected from them before they were removed) and a snippet for each remaining message; the lexer and parser gates also compare every lex and parse error (message, position and range) on the corpus, on snippets for each message, and on every line prefix of a few examples; the parser and checker gates compare the whole list of errors a run reports (D80): the parser gate on snippets that recover at statements, members and declarations and on four garbled copies of every example (lines broken in ten ways), the checker gate on snippets with errors in several functions, attributes, the entry point, after a failed loop, lambda or `#test`, and the limit, compares every note and help line (D83), and runs the declaration mutants of `test_declaration_recovery.py` (D84); the interpreter gate also compares runtime errors (message, file, caret) and evaluation order with the Python CLI's, runs the codegen gate's parity programs, and checks that `push`, element assignment and updates inside `var self` methods and nested lists scale linearly ([[MYLA-74]]); the codegen and interpreter gates also run multi-module projects through the self-hosted loader (and the codegen gate checks that its diagnostics, lex and parse errors in imported modules included, print exactly as the Python CLI printed them, carets and all: every lex, parse, module and type error of the corpus, and ranges that run past their line, hold characters beyond ASCII or sit in an f-string, [[MYLA-65]], and several errors in one file and in two modules with the summary line, D80), the codegen gate also runs the `test_compiler_parity.py` programs for bugs both backends had, and its arena-reclaim stress programs with a 30 MB peak-memory bound (measured from a minimal helper process: a child's peak RSS includes its parent's at fork); since [[MYLA-107]] every function it compiles goes through the IR ([[Architecture/IR]]), whose text form it also checks (`--emit-ir`) |

`tests/burn/_native.py` holds the helpers to build and run native binaries, `tests/burn/_tools.py` the bootstrap and the cache of self-hosted tools, `tests/burn/_golden.py` the recorded answers.

## The VS Code extension's tests

`vscode-extension/myla/test/` holds the extension's own tests, written with `node:test` and run by node with the types stripped, so they need no compile step ([[MYLA-99]], [[MYLA-100]]):

- `test/unit/`: the GDB/MI parser, the DAP framing, how stops and values are presented (names, children's expressions), finding the CLI and its command lines, the compiler's diagnostics and debug builds, the adapter against a fake gdb, and the bundle activating against a stand-in `vscode` module (registering every command the manifest contributes);
- `test/integration/adapter.test.ts`: the adapter on stdio against real gdb, debugging `test/fixtures/*.my` built by `$MYLA_CLI` or the repository's `build/myla` (breakpoints, stepping, the stack, variables, evaluate, runtime errors, pause, exit codes, build errors, Run Without Debugging); skipped without gdb, as/ld or the CLI. `MYLA_DAP_BUNDLE=1` tests `out/debugAdapter.js` instead of the sources, `DAP_TRANSCRIPT=<file>` writes every message.

`npm test` builds the bundle and runs both (CI's `vscode-extension` job); `tests/burn/test_vscode_debugger.py` runs the integration test, so the burn suite covers it without `npm ci`. (`tests/unit/test_vscode_extension.py` ran the unit tests and checked the grammar and snippets until [[MYLA-219]].)

## The error corpus

Every file in `examples/errors/` starts with a directive naming the stage that must reject it and a substring of the message:

```
//~ type error: cannot assign to an immutable binding
fun main() {
    let x = 1
    x = 2
}
```

Stages are `lex`, `parse`, `module`, `type` and `runtime`. A `module` case goes through the loader with the bundled standard library. A `runtime` case is also built natively, by the self-hosted compiler; it needs a second directive with the first line the native binary prints on stderr (its messages have no values in them, [[MYLA-17]]). The binary must exit with status 1 and print exactly that line and then the interpreter's position, `  --> <file>:<line>:<col>` ([[MYLA-65]]):

```
//~ runtime error: map key 2 not found
//~ native: runtime error: map key not found
```

A file may also name the source text the diagnostic underlines, which pins the range an error reports ([[MYLA-65]]):

```
//~ type error: unknown function
//~ span: nope(1)
fun main() {
    let x = nope(1)
}
```

The stage must report exactly one error, unless the file says how many it reports; then it may name a substring of each later error's message, in order (D80, [[MYLA-65]]):

```
//~ parse error: expected variable name
//~ errors: 5
//~ next: expected an expression, found ')'
//~ next: expected ':', found 'int'
```

The first error's notes and help lines are named in order, each by its label and a substring of its message, and a note's underlined text may be pinned like the error's; a file without these directives expects an error without notes, so a note can't appear or change unnoticed (D83, [[MYLA-65]]):

```
//~ type error: cannot assign to an immutable binding
//~ note: 'x' is declared here
//~ note span: let x = 1
```

```
//~ type error: unknown name 'cuont'
//~ help: did you mean 'count'?
```

The diagnostics a file is checked against are the Python toolchain's, recorded ([[MYLA-219]], "Recorded answers"), so a file added or changed since fails until its test gets an expectation of its own. The corpus has 214 files: 12 lex, 12 parse, 2 module, 175 type, 13 runtime. The `type_recover_*` files have errors in declarations and bodies (D84, [[MYLA-110]]). More module errors (cycles, which file an error is attributed to) were covered by the Python loader's unit tests (`tests/unit/test_loader.py`, until [[MYLA-219]]); the codegen gate's `MODULE_ERRORS` and `test_packages.py` pin the self-hosted loader's.

## Generated `#test` cases

Most `#test` cases in `selfhost/` were generated by `scripts/harvest_tests.py` ([[MYLA-184]]), which ran the self-hosted CLI in the Python interpreter and was removed with it ([[MYLA-219]]; it is on the branch `backup/python-toolchain-final`). The self-hosted toolchain agreed with the Python one on the whole corpus and compiled itself to a fixed point, so what its functions returned then was a valid expected result, and a case protects it against regressions; the cases record behaviour, they don't specify it.

- `record` ran the self-hosted CLI over workloads (`check`, `build`, `test` and `run` of every example, `check` of the error corpus, REPL sessions, project commands, `fetch` from a local Git repository, `build -g`) and kept calls whose arguments and result print as Myla expressions, but none that did I/O.
- `generate` called the remaining functions: a parameter of a state type (the parser, checker, interpreter, code generator, lowering) or an AST type took a *factory* (`parser_on("1 + 2 * 3")`, `checker_on(…)`, …) over a set of one-line snippets; the other parameters took recorded values, or values of their type from a pool.
- `write` wrote the chosen cases above the functions that had none; `validate` ran both test runners on every module and removed each case either rejected, which is how differences between the two interpreters showed up ([[MYLA-238]]).

New cases are written by hand. The generated cases of path functions use `/work/myla` as the repository's path, so no checkout's path appears in them.

`scripts/test_coverage.py` reports the share of value-returning functions with cases per module; `tests/burn/test_selfhost_coverage.py` warns below 80 % (D109).

## Adding tests

- A new feature gets an example in `examples/` with `#test` cases, registered in `test_examples_run.py` and `test_examples_compile.py`.
- A fixed bug gets a program: an accepted one in `examples/regressions.my` (or a parity case in `test_compiler_parity.py`), a rejected one in `examples/errors/`. A test that asked the Python toolchain has no recorded answer for a new program and fails until it gets an expectation of its own ("Recorded answers").
- Anything the native backend does differently from the interpreter belongs in `test_compiler_parity.py`.
