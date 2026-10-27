---
id: MYLA-97
title: Language server - list files with list_dir and resolve into packages
type: improvement
status: backlog
priority: low
labels: [lsp, tooling]
---
The language server's workspace index ([[tools/lsp/workspace.my]]) finds `.my` files by running `find`, because Myla had no directory listing. `std.fs.list_dir` ([[MYLA-88]]) can replace it, which removes the dependency on `find` and a process per scan.

Once projects exist ([[MYLA-92]] to [[MYLA-94]]), the server should also read the project's packages (through the project model of [[MYLA-93]]), so definitions, references and completion reach into dependencies.

- [ ] Walk the workspace roots with `list_dir`/`is_dir` (skip `build/`, `.git/`, `.myla/`), sorted as today
- [ ] Packages of the project passed to the loader the server runs
- [ ] The scenarios in `tests/burn/_lsp_scenarios.py` still pass; a scenario with a path dependency
