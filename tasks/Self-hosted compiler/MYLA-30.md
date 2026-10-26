---
id: MYLA-30
title: Self-hosted loader concatenates modules as text
type: bug
status: review
priority: medium
labels: [selfhost, loader, modules]
---
[[selfhost/loader.my]] removed import lines and concatenated every module's source, dependencies first. There was no name qualification, no privacy and no packages, unlike the Python loader ([[Architecture/Module-loader]]):

- A user function named like a private stdlib helper collided with it: a user `fun collect` clashed with `std.process`'s `collect` → `type-check failed at 130:1`.
- `import x as y` / `y.f()` and package directories (`geometry/geometry.my`) were unsupported, so `examples/modules/main.my` failed: `cannot read module: examples/modules/geometry.my`.
- Each module was lexed and parsed twice.

## How

The loader is now a port of `src/myla/loader.py` over the self-hosted AST: it parses each module once, resolves imports (project root, then stdlib; relative dots; `x.my` or package `x/x.my`, ambiguous if both), gives each module an id, builds exports (with re-exports to a fixpoint) and bindings, and renames every module-level reference to `id$name` with local and type-parameter scopes, folding `alias.member` chains. `load_program` returns the linked declarations; `build_checker_decls` type-checks them with the prelude.

- **Node ids** must be unique across the program (the checker's side tables are keyed by them): `parse_ids` ([[selfhost/parser.my]]) continues numbering from where the previous module stopped, and the prelude is parsed last.
- **Drivers**: `gen_main`, `main` (`run`, `test`, `build`), `interp_main` and `probe_check` use the loader; the text-splicing `amalgamate`, `build_checker_src` and the `amalg_main` driver are gone.
- Differences from the Python loader (textual path normalization, no directory probing, internal module ids) are listed on [[Architecture/Module-loader]].

## Found on the way

- The self-hosted interpreter gave the interpreted program the **tool's** command line as `args()` (`myla run examples/args/main.my src/myla` printed `myla`, `run`, the file and `src/myla`). `new_interp` now takes the program's argv, `[file]`, as `myla run` does.
- Since each module keeps its own coordinates, the prelude no longer shifts positions: `let x: int = "s"` on line 2 is reported as `2:5`, not `10:5` (first item of [[MYLA-28]]).

## Done when

- [x] The loader links parsed modules the way `src/myla/loader.py` does (unique module ids, `module$name` qualification, `pub` exports, module aliases, packages)
- [x] `examples/modules` matches the oracle under stage3 (and under the stage-3-built `myla run`, `test` and `build`)
- [x] The fixpoint still holds (5,576,289 bytes of assembly, up from 4,964,820; the loader is about 440 KB of it)
- [x] Tests: `MODULE_PROJECTS` in `tests/burn/test_selfhost_codegen.py` (private names per module and next to stdlib helpers, aliases, nested modules, packages, types, methods, traits, generics, consts, re-exports, locals shadowing module names), run through both the self-hosted codegen and interpreter gates against the Python `link`; `MODULE_ERRORS` (seven loader errors with the Python loader's message and position). On the previous loader all 19 of these subtests fail (six programs in each gate, seven errors); now all pass, and a mutant that ignores local scopes fails two programs.
