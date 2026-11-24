---
id: MYLA-930
title: "The project commands don't work on Windows: selfhost/project.my takes only '/' for a path's root and separator"
type: bug
status: in-progress
priority: high
labels: [project, windows]
---
Found by [[MYLA-926]] step 2's port of the burn suites (2026-11-24, group G5), reproduced under Wine with a Windows-built `myla.exe` and `project_main.exe`: in a project's directory, `myla run` (also right after `myla new hello`) prints

```
myla: Z:\…\app/Z:\…\app/myla.toml: cannot read the manifest
```

and from a subdirectory `../myla.toml: cannot read the manifest`. `selfhost/project.my`'s path functions (`normalize_path`, the join of a base and a relative path, `is_under`, the relative path of a file below the root) treat a path as absolute only when it starts with `/` and split and join with `/` alone, so a Windows working directory (`C:\…`) is taken for a relative path and joined onto itself. The file commands (`myla run f.my`, `build`, `test`) are right on Windows: they go through std.path's Windows rules ([[MYLA-704]], `lib/std/path_windows.my`).

This breaks every project command on Windows (`run`, `build`, `test`, `fetch`, `add` in a project) and so test_project, test_project_commands' project-mode tests, test_project_fetch and test_installed's project test there.

- [x] project.my's paths through std.path (the machine's rules: a drive or a share as the root, `\` and `/` both separators on Windows), its own `#test` cases for Windows' paths (`windows_paths`, `posix_paths`: each checks its machine's; `myla test selfhost/project.my --target x86_64-windows` runs Windows' under Wine)
- [x] How a project's paths print on Windows (the root's spelling, `\` in messages), decided and the same as the file commands'. Decided: written with `/` and the drive as given (`Z:/…/app/myla.toml`, a share `//srv/share/…`), as the loader and the file commands print a path ([[MYLA-931]]: `myla run Z:\…\d\bad.my` shows `--> Z:/…/d/bad.my:2:5`); what the commands show from the working directory stays relative (`src/main.my`, `../src/main.my`). A verbatim path (`\\?\C:\…`) is kept as written.
- [ ] test_project's expectations of `{root}/…` with the machine's separator, then the suites above on the `burn-windows` job. The expectations stay `{root}/…`, as the tool writes `/`; `run_tool` takes the root's `/`-spelling (`C:/…`) for `{root}` too. Left: running the four suites on Windows itself (not possible under Wine here: no Windows Python)
- [x] Evidence: under Wine with a Windows-built `myla.exe`, in `myla new hello`'s directory and in `hello/src/sub`, `myla run` prints `Hello from hello!` and `myla test` passes 1/1 (before: `myla: Z:\…\hello/Z:\…\hello/myla.toml: cannot read the manifest`, from `sub` `myla: myla.toml: cannot read the manifest`); `myla build` resolves the project and writes `build/hello.exe.s`, then stops for want of clang (Wine has none); `project_main.exe` resolves a `..\\geo` path dependency (`--package geo=Z:/…/geo/src`); `myla test selfhost/project.my --target x86_64-windows` 114/114. On Linux `build/myla test selfhost/project.my` 114/114, the bootstrap's fixed point, test_project 47, test_project_commands 20, test_project_fetch 9, test_installed 5 (as before), test_selfhost_cases, test_lsp and check-seed.sh pass
