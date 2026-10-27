---
id: MYLA-92
title: Packages in both loaders (--package name=dir)
type: feature
status: backlog
priority: medium
labels: [loader, selfhost, tooling]
---
Step 3 of the project tool ([[MYLA-64]]): the loaders find dependencies through a list of packages, so the compilers never read a manifest (D73 (6)). The rules are on [[Architecture/Project-tool]] (section "The loaders"); its questions 2 and 3 were settled as proposed.

- [ ] Python loader ([[src/myla/loader.py]]): `link(…, packages=…)`; resolution project, packages, standard library; a package's path looked up as if its directory were `<name>/` in the project root
- [ ] The shadowing error: `'geo' is a dependency and cannot be shadowed by a project file or directory`; errors for a package named `std`, a name given twice, a malformed flag
- [ ] Package module ids as for a `<name>/` directory in the project root (no fetch paths or commits in symbols)
- [ ] A project root parameter that defaults to the entry's directory (for `myla test`/`check` on nested files)
- [ ] Python CLI: `--package name=dir` for `run`, `test`, `build`, `check`
- [ ] Self-hosted loader ([[selfhost/loader.my]]) the same, and the flag in `build/myla`, `interp_main` and `gen_main`
- [ ] Tests: unit tests for the Python loader (resolution, shadowing, ids, errors); burn parity on a project with two packages (one importing the other, relative imports inside a package, a package root with re-exports) in both toolchains, and the module errors printed alike (`MODULE_ERRORS`)
- [ ] [[Language/Modules]] and [[Architecture/Module-loader]] describe packages
