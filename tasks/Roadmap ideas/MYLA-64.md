---
id: MYLA-64
title: Project tool like cargo
type: feature
status: review
priority: medium
labels: [tooling, cli, design]
---
One command for Myla projects, like `cargo` for Rust: create, build, run and test a project, and fetch its dependencies.

## Design

Decided as D73 on [[Project/Decisions]]; the details, with the questions settled when the design was approved, are on [[Architecture/Project-tool]]:

- a manifest `myla.toml` (a TOML subset) and a lock file `myla.lock` for Git dependencies;
- `src/main.my` as the program, `src/<name>.my` as the library; a dependency `geo` is imported as a package `geo`;
- dependencies from paths and Git, checked out per project in `.myla/deps/<name>-<commit>/`, one version per name;
- both loaders take `--package name=dir`; lookup is project, packages, standard library;
- `myla new`, `build`, `run`, `test`, `check`, `fetch`, `clean` in the self-hosted CLI, written in Myla; `myla fmt` later.

## Steps (epic `Project tool`)

- [x] Manifest format and resolution rules recorded on [[Project/Decisions]] (D73) and [[Architecture/Project-tool]]
- [x] The design page approved, its questions settled as proposed
- [x] [[MYLA-88]] File-system functions in `std.fs` (in review)
- [x] [[MYLA-89]] `std.toml` (in review)
- [x] [[MYLA-92]] `--package name=dir` in both loaders (in review)
- [x] [[MYLA-93]] The project model: manifest, lock file, path dependencies (in review; with [[MYLA-98]], `std.fs.current_dir`)
- [x] [[MYLA-94]] The commands, with path dependencies (in review)
- [x] [[MYLA-95]] Git dependencies and `myla fetch` (in review)
- [ ] [[MYLA-96]] Removing and renaming files in `std.fs` (not needed for now: `rm -rf`/`mv` through `std.process`)
- [x] [[MYLA-97]] The language server finds files with `list_dir` and resolves into packages (in review)

## Depends on

- The self-hosted loader understanding packages ([[MYLA-30]]) and a stdlib root that needn't be passed by hand ([[MYLA-31]]), both in review

## Done when

- [x] Manifest format and resolution rules recorded on [[Project/Decisions]]
- [x] `myla new` + `myla build/run/test` work on a fresh project with one path dependency (`tests/burn/test_project_commands.py`)
