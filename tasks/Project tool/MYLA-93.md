---
id: MYLA-93
title: Project model - manifest, lock file and path dependencies
type: feature
status: done
priority: medium
labels: [tooling, selfhost]
---
Step 4 of the project tool ([[MYLA-64]]): the Myla code that turns `myla.toml` (and `myla.lock`) into the list of packages a build needs, as [[Architecture/Project-tool]] describes. Needs [[MYLA-89]] (`std.toml`); lives next to the CLI in `selfhost/` (`project.my` or similar).

- [x] Read `myla.toml` with `std.toml` and check it: `[package]` `name` (`[A-Za-z][A-Za-z0-9_]*`, not a keyword, not `std`), `version`, the optional fields; `[dependencies]` entries with exactly one of `path`/`git` and at most one of `tag`/`branch`/`rev`; unknown keys (question 9, settled). Errors with file, line and column
- [x] Find the manifest from the current directory upwards (question 7, settled)
- [x] Resolve dependencies transitively, breadth first; one version per name with the message of the design page; a dependency's name equals its `package.name`; it has `src/<name>.my`
- [x] Read and write `myla.lock` (format version 1, sorted, current entries); writing is for [[MYLA-95]], reading is needed to find Git checkouts
- [x] The result: the root package (name, directory, program and library present or not) and the `(name, dir/src)` pairs for the loader ([[MYLA-92]])
- [x] `#test` cases for the pure parts; burn tests on manifests in temporary directories (every error once)
- [x] The working directory: `std.fs.current_dir` and the primitive `__getcwd` ([[MYLA-98]])
- [x] Positions of keys and values in `std.toml` (`parse_doc`, `key_pos`, `value_pos`), so errors point at what they are about

## How

[[selfhost/project.my]], with the interface on [[Architecture/Project-tool]] ("The project model") and the decisions in D77:

- **Paths** are absolute and lexically normalised (`normalize_path`, `join_path`, `parent_dir`), a relative one taken from `std.fs.current_dir()` ([[MYLA-98]]). Two requests name one package when their directories are equal strings, however they were spelt (`../x/../util/.`). `find_manifest` walks from the start directory to `/`.
- **Checking** (`parse_manifest`, pure): `std.toml`'s new `parse_doc` keeps where every key and value is, so each error points at its key (unknown keys, a dependency's problems) or its value (a bad name, a wrong type), with carets under the whole key or value. A missing field points at the `[package]` header; no `[package]` at all has no position.
- **Resolving** (`resolve_project`): breadth first from the root manifest, each name once, remembering the first request for each name (a key such as `path:/abs/dir` or `git:<url> tag v1`, the text for messages, the requesting package). A second request with another key is `two versions of package …`; the root package is in the table from the start, so a dependency back to the root's own directory is the root (allowed; it needs its library and gets no `--package`). An error about a dependency points at its key in the manifest that asks for it.
- **Git dependencies** are read from `<root>/.myla/deps/<name>-<commit>/` with the commit of the current entry (same name, URL and reference) of the root's `myla.lock`; their path dependencies must stay inside the checkout. A dependency without a current entry is ``dependency 'x' is not locked: run `myla fetch` `` from `load_project`; `resolve_project(…, true)` lists such dependencies in `Project.unlocked` instead, for `myla fetch`. A locked one whose checkout doesn't exist is in `Project.missing` (with the commit and the directory to clone into) and isn't followed further: the commands check those out and resolve again ([[MYLA-94]], [[MYLA-95]]).
- **The lock file**: `load_lock`/`parse_lock` check the format version (`myla.lock is from a newer myla`), the keys and the commit ids; `render_lock` writes the design's format, sorted by name, with TOML-escaped strings; `lock_of(p)` gives the current entries of a project.
- **Errors** render like compile errors (`render_project_error`, through `diag.render`): `manifest error:` or `lock file error:`, `-->`, the source line and carets; without a position `myla: <file>: <message>`.
- `selfhost/project_main.my` is a driver for the tests: it prints `describe_project` of the project found from its working directory, or the error; `--fetch` resolves as `myla fetch` would and prints the lock file it would write; `--lock file` reads a lock file and renders it again.

The self-hosted toolchain calls the top-level function of the entry module when a local closure has the same name: a closure `fail` in `resolve_project` called the driver's `fun fail` (a crash in the self-hosted build, found by the parity test). `project.my` uses a helper function instead; the bug itself is outside this task (repro: a local `let fail = (m: str) => len(m)` next to a top-level `fun fail`; the Python toolchain calls the closure, `build/myla run` and `gen_main` the function).

## Evidence

- `#test` cases: `build/myla test selfhost/project.my` and `python3 myla.py test selfhost/project.my`: 85/85 passed (including `diag` and `tokens`): name validation (empty, digits first, `-`, `_` first, non-ASCII, keyword, `std`), commit ids, path normalisation, joining, parents, `is_inside`, byte order, Git references, `toml_string` escapes, `render_lock` (empty, sorted, escaped), lock round trips, nine manifests through `manifest_summary` (with error ranges), `describe_package`, `render_project_error` without a position.
- `tests/burn/test_project.py` (new, 47 tests): the driver built by the Python backend in temporary directories: transitive path dependencies from a nested directory, the nearest manifest, no manifest, an absolute path dependency, cycles (also back to the root), two versions (of a dependency and of the root package), one directory spelt differently, name mismatch, missing library, missing package directory, errors in a dependency's manifest, every manifest error (syntax, no `[package]`, `package` not a table, missing `name`, missing `version`, wrong types, optional fields, bad, keyword and `std` names, unknown key, unknown table, unknown dependency key, `path` and `git`, neither, two references, a reference with `path`, a short `rev`, a shorthand dependency, an empty path, a bad dependency name), Git dependencies locked and checked out (with a path dependency inside the checkout), a path dependency leaving its checkout, unlocked, a stale lock entry, unlocked as `myla fetch` sees them, a missing checkout (and the lock `myla fetch` would write, dropping an entry that isn't current), default branch and `rev`, lock round trips and canonical rewriting, nine lock file errors, a broken lock file stopping the build. `ProjectModelParity` runs a project with every kind of package, an error and a lock file in the Python interpreter and in the drivers built by both backends: identical output.
- `tests/unit/test_toml.py`, `test_positions`: key and value positions of pairs, inline-table keys, opened and implied headers, multi-line arrays, non-ASCII columns.
- Test counts: unit 519 → 524 (5 new: 4 for `current_dir`, 1 for TOML positions), integration 2 → 2, burn 573 → 623 (47 in `test_project.py`, 2 in `test_fs.py`, 1 in `test_debug_info.py`), all passing (5 skipped, as before).
- `scripts/bootstrap.sh`: byte-identical fixed point, 8,487,923 bytes (8,471,478 before; the growth is [[MYLA-98]]: `project.my` is not linked into the compiler yet).
