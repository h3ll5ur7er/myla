---
id: MYLA-94
title: Project commands in build/myla (path dependencies)
type: feature
status: done
priority: medium
labels: [tooling, cli, selfhost]
---
Step 5 of the project tool ([[MYLA-64]]): `myla new`, `build`, `run`, `test`, `check` and `clean` in the self-hosted CLI ([[selfhost/main.my]]) when no file is given, as the command table on [[Architecture/Project-tool]] describes. Needs [[MYLA-92]] and [[MYLA-93]]; Git dependencies follow in [[MYLA-95]].

- [x] Project mode: the first argument after the command doesn't end in `.my`; file mode unchanged
- [x] `myla new <name>`: `myla.toml`, `src/main.my`, `.gitignore` (`build/`, `.myla/`); errors for a bad name or an existing directory
- [x] `myla build [-g]`: `src/main.my` with the packages to `build/<name>` (`make_dir_all("build")`)
- [x] `myla run [args…]`: interpret, with the arguments (question 6, settled)
- [x] `myla test`: every `.my` file under `src/` (sorted, with `list_dir`), each file's own `#test` cases only, project root `src/`; a total and exit status 1 on a failure
- [x] `myla check`: every file under `src/`, each file's first error
- [x] `myla clean [--deps]` (question 4, settled)
- [x] `usage()` and the header comment of `selfhost/main.my` list the commands
- [x] Burn tests in `tests/burn/test_selfhost_cli.py`: a fresh `myla new` project with one path dependency builds, runs and tests; each command's errors
- [x] [[Getting started]] shows a project; [[Language/Modules]] links the design

## How

- **Modules:**
  - `selfhost/main.my` now only parses the command line and dispatches.
  - What the commands do with one entry file (load and check, interpret, run tests, build) moved to `selfhost/driver.my`, unchanged.
  - The project commands are `selfhost/project_cmd.my`, on top of the project model ([[MYLA-93]]) and the loader's options ([[MYLA-92]]).
- **Project mode:** the first argument that ends in `.my` is the file. Without one, `build`, `run`, `test` and `check` work on the project: `find_manifest` from the working directory, `load_project`, then the loader with the project's `--package` pairs (before any given on the command line) and `src/` as the root.
- **Paths:** paths are passed to the loader relative to the working directory (`relative_path`, new in `project.my`), so diagnostics read `--> src/main.my:2:11` and the program's `argv[0]` is `src/main.my` (or `../main.my` from `src/util/`).
- **`myla test`:** each file under `src/` (sorted, `.`-names skipped) is loaded as an entry. Only its own cases run: `Interp.run_test_cases(own_only)` keeps the functions whose names the loader didn't qualify with a module id (no `$`), and returns the PASS/FAIL lines and counts so the command can print a block per file and one total. `run_tests` (file mode) prints the same as before through it.
  - A file that doesn't compile prints its error; the others still run, and the exit status is 1.
- **`myla check`:** with a file, it prints `ok` like the Python CLI. In a project it prints only errors, each file's first.
- **`myla new`:** writes a program whose greeting a `#test` case checks, so `myla test` has something to run in a new project.
- **`myla clean`:** runs `rm -rf` through `std.process` (settled question 4).
- **Git dependencies:** a Git dependency whose locked commit wasn't checked out stopped the command with ``run `myla fetch` ``; since [[MYLA-95]] the commands check it out.

## Evidence

- **Tests first:** `tests/burn/test_project_commands.py`, 14 tests, all failing before (`unknown command 'new'`, file mode taking the arguments as files), all passing after:
  - `myla new` with its exact files, then `run`, `test`, `check`, `build` (the binary runs) and `clean` twice;
  - a project with a path dependency and a nested module: arguments, a run from a subdirectory, `build -g`, each file's own cases (the dependency's cases don't show up under `src/main.my`), a library without a program, file mode reading no manifest;
  - errors: no manifest (every command), a manifest error, compile errors with project-relative paths in `run`/`check`/`test`, a Git dependency not checked out, the usage.
- **Unit tests:** the new `#test` cases of `relative_path`, `is_qualified`, `count` and `ends_with` pass under `myla test`.
- **The other suites:** the CLI parity test (`myla test file.my` against the Python CLI on the corpus) and the rest still pass; see the full-suite numbers in the commit.

## Evidence (sign-off, 2026-10-31)

The review ([[Project/Review-2026-10]]) found `myla clean` refusing to clean: it located the project through `checked_out_project`, so a dependency that isn't locked (a Git dependency after its tag was edited, or before the first `myla fetch`) stopped it with ``dependency 'geo' is not locked: run `myla fetch` `` and nothing was removed. `project_clean` now reads only the manifest (`find_here`) and removes `build/` (and `.myla/` with `--deps`) from the manifest's directory. Test first: `test_clean_needs_no_resolvable_dependencies` in `tests/burn/test_project_commands.py` (a project with an unlocked Git dependency: `check` reports it, `clean` removes `build/` and leaves `.myla/`, `clean --deps` removes `.myla/`), failing before (`myla: dependency 'greet' is not locked`, exit 1), passing after; the module's 15 tests pass.
