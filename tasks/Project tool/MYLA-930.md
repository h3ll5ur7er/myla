---
id: MYLA-930
title: "The project commands don't work on Windows: selfhost/project.my takes only '/' for a path's root and separator"
type: bug
status: todo
priority: high
labels: [project, windows]
---
Found by [[MYLA-926]] step 2's port of the burn suites (2026-11-24, group G5), reproduced under Wine with a Windows-built `myla.exe` and `project_main.exe`: in a project's directory, `myla run` (also right after `myla new hello`) prints

```
myla: Z:\…\app/Z:\…\app/myla.toml: cannot read the manifest
```

and from a subdirectory `../myla.toml: cannot read the manifest`. `selfhost/project.my`'s path functions (`normalize_path`, the join of a base and a relative path, `is_under`, the relative path of a file below the root) treat a path as absolute only when it starts with `/` and split and join with `/` alone, so a Windows working directory (`C:\…`) is taken for a relative path and joined onto itself. The file commands (`myla run f.my`, `build`, `test`) are right on Windows: they go through std.path's Windows rules ([[MYLA-704]], `lib/std/path_windows.my`).

This breaks every project command on Windows (`run`, `build`, `test`, `fetch`, `add` in a project) and so test_project, test_project_commands' project-mode tests, test_project_fetch and test_installed's project test there.

- [ ] project.my's paths through std.path (the machine's rules: a drive or a share as the root, `\` and `/` both separators on Windows), its own `#test` cases for Windows' paths
- [ ] How a project's paths print on Windows (the root's spelling, `\` in messages), decided and the same as the file commands'
- [ ] test_project's expectations of `{root}/…` with the machine's separator, then the suites above on the `burn-windows` job
