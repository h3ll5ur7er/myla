# Development

How to change Myla safely: the test suites, the bootstrap and the working conventions.

[SUBPAGES]

## The short version

1. Pick or create a task (`tasks/`, see [[Development/Conventions]]) and set it to `in-progress`.
2. Change the self-hosted toolchain ([[Architecture/Self-hosted-compiler]]); a change of behaviour goes into its interpreter and its native backend alike, and into the [[Language]] pages.
3. Add an example or a regression case: a positive program in `examples/` (registered in the run and compile burn tests) or a rejected one in `examples/errors/` with its `//~` directive.
4. Run the quick burn tests while working, and all of them before committing ([[Development/Testing]]).
5. If you touched `selfhost/` or `lib/std/`, run `scripts/bootstrap.sh` and check the fixed point, and if the compiler's output changed, make a new seed with `scripts/update-seed.sh` and commit it ([[Development/Bootstrap]]).
6. Update the wiki page that describes what you changed, record new design decisions on [[Project/Decisions]], and name the task in the commit message.

## Repository layout

```
bootstrap/seed.s        the seed: the self-hosted compiler's own assembly, stage 0 of the bootstrap
selfhost/               the self-hosted compiler, interpreter and CLI (build/myla)
lib/                    the stdlib root: std/ holds the standard library, debug/ the gdb pretty-printer
examples/               one runnable example per feature, plus args/ stdio/ readfile/ subprocess/ modules/
examples/errors/        programs that must be rejected, one diagnostic each
tests/burn/             the tests (Python unittest): interpreter output, native parity, #test cases, error corpus, self-hosting gates
scripts/                bootstrap.sh, update-seed.sh, check-seed.sh, install-hooks.sh, build.sh, test.sh (fast|all), the generators (gen_unicode_tables.py, gen_treesitter.sh)
justfile                bootstrap, build, run, test, run-all recipes
grammar/                myla.ebnf, the grammar description
tools/                  tools written in Myla: lsp/ (the language server), grammar/ (the generator)
editor/                 the tree-sitter grammar, generated from grammar/myla.ebnf
vscode-extension/myla/  the VS Code extension
docs/                   this wiki
tasks/                  the task board (Genbeya)
```
