---
id: MYLA-64
title: Project tool like cargo
type: feature
status: backlog
priority: medium
labels: [tooling, cli, design]
---
One command for Myla projects, like `cargo` for Rust: create, build, run and test a project, and fetch its dependencies.

## Design

Decided as D73 on [[Project/Decisions]]; the details, with the open questions to answer before the loaders change, are on [[Architecture/Project-tool]]:

- a manifest `myla.toml` (a TOML subset) and a lock file `myla.lock` for Git dependencies;
- `src/main.my` as the program, `src/<name>.my` as the library; a dependency `geo` is imported as a package `geo`;
- dependencies from paths and Git, checked out per project in `.myla/deps/<name>-<commit>/`, one version per name;
- both loaders take `--package name=dir`; lookup is project, packages, standard library;
- `myla new`, `build`, `run`, `test`, `check`, `fetch`, `clean` in the self-hosted CLI, written in Myla; `myla fmt` later.

## Steps (epic `Project tool`)

- [x] Manifest format and resolution rules recorded on [[Project/Decisions]] (D73) and [[Architecture/Project-tool]]
- [ ] The design page approved, its open questions answered
- [ ] [[MYLA-88]] File-system functions in `std.fs` (in review)
- [ ] [[MYLA-89]] `std.toml`
- [ ] [[MYLA-92]] `--package name=dir` in both loaders
- [ ] [[MYLA-93]] The project model: manifest, lock file, path dependencies
- [ ] [[MYLA-94]] The commands, with path dependencies
- [ ] [[MYLA-95]] Git dependencies and `myla fetch`
- [ ] [[MYLA-96]] Removing and renaming files in `std.fs` (only if the design asks for it)
- [ ] [[MYLA-97]] The language server finds files with `list_dir` and resolves into packages

## Depends on

- The self-hosted loader understanding packages ([[MYLA-30]]) and a stdlib root that needn't be passed by hand ([[MYLA-31]]), both in review

## Done when

- [x] Manifest format and resolution rules recorded on [[Project/Decisions]]
- [ ] `myla new` + `myla build/run/test` work on a fresh project with one path dependency
