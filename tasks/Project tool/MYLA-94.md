---
id: MYLA-94
title: Project commands in build/myla (path dependencies)
type: feature
status: backlog
priority: medium
labels: [tooling, cli, selfhost]
---
Step 5 of the project tool ([[MYLA-64]]): `myla new`, `build`, `run`, `test`, `check` and `clean` in the self-hosted CLI ([[selfhost/main.my]]) when no file is given, as the command table on [[Architecture/Project-tool]] describes. Needs [[MYLA-92]] and [[MYLA-93]]; Git dependencies follow in [[MYLA-95]].

- [ ] Project mode: the first argument after the command doesn't end in `.my`; file mode unchanged
- [ ] `myla new <name>`: `myla.toml`, `src/main.my`, `.gitignore` (`build/`, `.myla/`); errors for a bad name or an existing directory
- [ ] `myla build [-g]`: `src/main.my` with the packages to `build/<name>` (`make_dir_all("build")`)
- [ ] `myla run [args…]`: interpret, with the arguments (question 6, settled)
- [ ] `myla test`: every `.my` file under `src/` (sorted, with `list_dir`), each file's own `#test` cases only, project root `src/`; a total and exit status 1 on a failure
- [ ] `myla check`: every file under `src/`, each file's first error
- [ ] `myla clean [--deps]` (question 4, settled)
- [ ] `usage()` and the header comment of `selfhost/main.my` list the commands
- [ ] Burn tests in `tests/burn/test_selfhost_cli.py`: a fresh `myla new` project with one path dependency builds, runs and tests; each command's errors
- [ ] [[Getting started]] shows a project; [[Language/Modules]] links the design
