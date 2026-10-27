---
id: MYLA-92
title: Packages in both loaders (--package name=dir)
type: feature
status: review
priority: medium
labels: [loader, selfhost, tooling]
---
Step 3 of the project tool ([[MYLA-64]]): the loaders find dependencies through a list of packages, so the compilers never read a manifest (D73 (6)). The rules are on [[Architecture/Project-tool]] (section "The loaders"); its questions 2 and 3 were settled as proposed.

- [x] Python loader ([[src/myla/loader.py]]): `link(…, packages=…)`; resolution project, packages, standard library; a package's path looked up as if its directory were `<name>/` in the project root
- [x] The shadowing error: `'geo' is a dependency and cannot be shadowed by a project file or directory`; errors for a package named `std`, a name given twice, a malformed flag
- [x] Package module ids as for a `<name>/` directory in the project root (no fetch paths or commits in symbols)
- [x] A project root parameter that defaults to the entry's directory (for `myla test`/`check` on nested files)
- [x] Python CLI: `--package name=dir` for `run`, `test`, `build`, `check`
- [x] Self-hosted loader ([[selfhost/loader.my]]) the same, and the flag in `build/myla`, `interp_main` and `gen_main`
- [x] Tests: unit tests for the Python loader (resolution, shadowing, ids, errors); burn parity on a project with two packages (one importing the other, relative imports inside a package, a package root with re-exports) in both toolchains, and the module errors printed alike (`MODULE_ERRORS`)
- [x] [[Language/Modules]] and [[Architecture/Module-loader]] describe packages

## How

The details D73 left open are D76 on [[Project/Decisions]].

**APIs.** Packages are a parameter, a list of (name, directory) pairs; callers that pass none behave as before.

| Toolchain | Entry point |
| --- | --- |
| Python | `link(entry_path, *, stdlib_root=None, source_overrides=None, packages=None, project_root=None)`; `parse_package_flag(text) -> (name, dir)` |
| Self-hosted | `load_program_packages(entry: str, stdlib_root: str, packages: [(str, str)], root: str) -> Result<Loaded, Report>` (`root` "" for the entry's directory), and the general `load_program_opts(entry: str, opts: LoadOptions)` with `pub struct LoadOptions { stdlib_root: str, packages: [(str, str)], root: str, overrides: [str: str] }` from `load_options(stdlib_root)`; `parse_package_flag(text: str) -> Result<(str, str), Report>`. `load_program` and `load_program_with` keep their signatures and call `load_program_opts` |

The project tool ([[MYLA-94]]) turns each `Package { name, dir }` of [[MYLA-93]] into `(name, dir + "/src")` and calls `load_program_packages("src/main.my", stdlib, pairs, "")`, or with root `"src"` for every file under `src/` in `myla test`/`check`.

**Resolution.** An import without dots whose first segment is a package's name resolves only in that package: `geo` is `G/geo.my` (else `package 'geo' has no root module 'geo.my' in G`), `geo.b.c` is `G/b/c.my` or `G/b/c/c.my`, with the usual ambiguity error. Before that, a project `geo` or `geo.my` (in the project root) is the shadowing error, at the import, like the `std` rule. Other names: project root, then stdlib root, as before.

**Checks.** Before loading, the list: `std`, a name that isn't `[A-Za-z][A-Za-z0-9_]*` or is a keyword, a name given twice, an empty or missing directory; module errors without a position, so both CLIs print `module error: …` and exit 1. A flag without `=` is the same kind of error, from `parse_package_flag`.

**Module ids.** A package module's id is the package's name and its path below the package directory (`geo$shapes$round`); the stdlib root is tried first, then the packages (innermost directory), then the project root, then `up$`. Same in both loaders.

**CLIs.** Python: `--package NAME=DIR` (repeatable, argparse `append`) on `run`, `test`, `build`, `check`; for `run` also after the file, taken out of the program's arguments, as `build/myla` does with `--stdlib`. `build/myla`: a small argument parser (`parse_command_line`) takes `--stdlib`/`--package` before or after the file for `run`, `test`, `build` and `repl` (`-o`/`-g` for `build`), and carries a `LoadOptions`; the REPL loads each input with the packages. `interp_main` and `gen_main` take `--package` and `--root <dir>` (test tools; the user CLIs have no root flag).

**Refactorings on the way.** The Python loader resolves each import once while loading and keeps the target (`_Module.targets`), so `_build_exports`/`_build_bindings` no longer re-resolve paths (and need no roots); the self-hosted loader's file/package lookup is one method, `descend`, used for the project, the stdlib and packages.

## Evidence

- Unit tests (`tests/unit/test_loader.py`: `TestPackages`, `TestProjectRoot`, `TestPackageFlags`, 19 tests): red before the loader change (19 failing for the right reasons: `link() got an unexpected keyword argument 'packages'` / `'project_root'`, `_module_id()` arity, no `parse_package_flag`, argparse rejecting `--package`), green after. Unit suite: 519 → 538, all pass.
- Burn (`tests/burn/test_packages.py`, 5 tests, 17 error cases as subtests): the two-package project prints the same in the Python CLI (`run`, flags before and after the file), `build/myla run`, `interp_main`; `myla test` output is identical in both CLIs (the packages' cases included); the binaries of `myla.py build`, `build/myla build` and `gen_main` print the same; a nested entry with a project root behaves alike (Python `project_root`, `interp_main --root`); every package error prints exactly the Python loader's diagnostic through `gen_main` and `build/myla build`. The self-hosted tools of the base commit fail on all of it (`cannot resolve import 'geo.shapes'`, the flags taken as a stdlib path).
- Burn suite: 573 → 578, all pass. Integration: 2, pass.
- Bootstrap: byte-identical fixed point, 8,543,155 bytes (8,471,478 before: +0.8% for the package code and the CLI parser).
- By hand with the bootstrapped `build/myla`: `printf 'import geo\ngeo.f() + 1\n' | myla repl --package geo=ws/geo/src` prints `2`; `myla run main.my --package geo` prints `module error: malformed --package 'geo': expected name=dir` and exits 1.
