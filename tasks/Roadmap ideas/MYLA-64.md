---
id: MYLA-64
title: Project tool like cargo
type: feature
status: backlog
priority: medium
labels: [tooling, cli, design]
---
One command for Myla projects, like `cargo` for Rust: create, build, run and test a project, and fetch its dependencies.

## Sketch

- `myla new <name>`, `myla build`, `myla run`, `myla test`, `myla check`, `myla fmt` later.
- A manifest (name, version, entry point, dependencies). Today there is none: the project root is the entry file's directory (D57); a manifest changes that and needs a decision.
- Dependencies from Git repositories or paths first; a lock file; where fetched packages live and how they map onto module paths (`import pkg.module`).
- Written in Myla, growing out of `selfhost/main.my`, which already has `run`/`test`/`build` and drives `as`/`ld`.

## Depends on

- The self-hosted loader understanding packages ([[MYLA-30]]) and a stdlib root that needn't be passed by hand ([[MYLA-31]])
- File-system functions beyond `read_to_string`/`write_to_file` (directory listing, `mkdir`, existence checks)

## Done when

- [ ] Manifest format and resolution rules recorded on [[Project/Decisions]]
- [ ] `myla new` + `myla build/run/test` work on a fresh project with one path dependency
