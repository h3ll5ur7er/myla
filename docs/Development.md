# Development

How to change Myla safely: the test suites, the bootstrap and the working conventions.

[SUBPAGES]

## The short version

1. Pick or create a task (`tasks/`, see [[Development/Conventions]]) and set it to `in-progress`.
2. Change the Python toolchain first; it is the reference. If the change affects behaviour, change the self-hosted compiler to match ([[Architecture/Self-hosted-compiler]]).
3. Add an example or a regression case: a positive program in `examples/` (registered in the run and compile burn tests) or a rejected one in `examples/errors/` with its `//~` directive.
4. Run the unit tests, then the burn tests ([[Development/Testing]]).
5. If you touched `selfhost/` or the native backend, run `scripts/bootstrap.sh` and check the fixed point ([[Development/Bootstrap]]).
6. Update the wiki page that describes what you changed, record new design decisions on [[Project/Decisions]], and name the task in the commit message.

## Repository layout

```
myla.py                 CLI shim (puts src/ on the path)
src/myla/               Python toolchain; std/ holds the standard library
selfhost/               the self-hosted compiler
examples/               one runnable example per feature, plus args/ stdio/ readfile/ subprocess/ modules/
examples/errors/        programs that must be rejected, one diagnostic each
tests/unit/             module-level tests (unittest)
tests/integration/      every example parses
tests/burn/             end-to-end: interpreter output, native parity, #test cases, error corpus, self-hosting gates
scripts/                bootstrap.sh, build.sh, run.sh, samples.sh
justfile                bs, bootstrap, build, run, test, run-all recipes
editor/                 the tree-sitter grammar
vscode-extension/myla/  the VS Code extension
docs/                   this wiki
tasks/                  the task board (Genbeya)
```
