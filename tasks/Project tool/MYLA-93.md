---
id: MYLA-93
title: Project model - manifest, lock file and path dependencies
type: feature
status: backlog
priority: medium
labels: [tooling, selfhost]
---
Step 4 of the project tool ([[MYLA-64]]): the Myla code that turns `myla.toml` (and `myla.lock`) into the list of packages a build needs, as [[Architecture/Project-tool]] describes. Needs [[MYLA-89]] (`std.toml`); lives next to the CLI in `selfhost/` (`project.my` or similar).

- [ ] Read `myla.toml` with `std.toml` and check it: `[package]` `name` (`[A-Za-z][A-Za-z0-9_]*`, not a keyword, not `std`), `version`, the optional fields; `[dependencies]` entries with exactly one of `path`/`git` and at most one of `tag`/`branch`/`rev`; unknown keys (open question 9). Errors with file, line and column
- [ ] Find the manifest from the current directory upwards (open question 7)
- [ ] Resolve dependencies transitively, breadth first; one version per name with the message of the design page; a dependency's name equals its `package.name`; it has `src/<name>.my`
- [ ] Read and write `myla.lock` (format version 1, sorted, current entries); writing is for [[MYLA-95]], reading is needed to find Git checkouts
- [ ] The result: the root package (name, directory, program and library present or not) and the `(name, dir/src)` pairs for the loader ([[MYLA-92]])
- [ ] `#test` cases for the pure parts; burn tests on manifests in temporary directories (every error once)
