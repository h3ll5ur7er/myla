---
id: MYLA-97
title: Language server - list files with list_dir and resolve into packages
type: improvement
status: review
priority: low
labels: [lsp, tooling]
---
The language server's workspace index ([[tools/lsp/workspace.my]]) finds `.my` files by running `find`, because Myla had no directory listing. `std.fs.list_dir` ([[MYLA-88]]) can replace it, which removes the dependency on `find` and a process per scan.

Once projects exist ([[MYLA-92]] to [[MYLA-94]]), the server should also read the project's packages (through the project model of [[MYLA-93]]), so definitions, references and completion reach into dependencies.

- [x] Walk the workspace roots with `list_dir`/`is_dir` (skip `build/`, `.git/`, `.myla/`), sorted as today
- [x] Packages of the project passed to the loader the server runs
- [x] The scenarios in `tests/burn/_lsp_scenarios.py` still pass; a scenario with a path dependency

## How

The decisions are D81 on [[Project/Decisions]]; [[Architecture/Editor-tooling]] describes the result.

- **The workspace scan** (`workspace.my`): a recursive walk with `std.fs.list_dir` and `is_dir`, then the same byte-wise sort as before, so the order of the files (and which declaration of a name the fallback finds first) doesn't change. It skips the directories `find` pruned (`.git`, `.venv`, `node_modules`, `__pycache__`, `build`, `out`) and now `.myla`. `is_dir` follows symbolic links (`find` didn't), so the walk stops 32 levels below a root rather than loop on a link to a parent. No process is spawned per request any more.
- **A document's context** (`tools/lsp/projects.my`, new): `context_of(path, stdlib, overrides)` looks for `myla.toml` from the document's directory upwards (`find_manifest`) and loads the project (`load_project`). The result is the loader's `LoadOptions`: the packages (`loader_packages`), `src/` as the project root when the document is under `src/`, and the open documents as overrides. A document elsewhere in the project (a scratch file next to `src/`) keeps its own directory as the root but gets the packages. The context is made again for every check and request (about 0.2 ms with a path dependency), so an edited manifest counts at once and there is nothing to invalidate.
- **Git dependencies** come from the project model as they are: a checked-out commit in `.myla/deps/<name>-<commit>/` is a package; a locked one that isn't checked out is in `Project.missing`, which the server reports on the manifest, at the dependency's key (``dependency 'color' is not checked out: run `myla fetch` ``), while the document keeps its other packages. The server never runs Git and never writes files.
- **Manifest errors**: when the project doesn't load, its `ProjectError` becomes a diagnostic on the file it names (`myla.toml`, a dependency's manifest, or `myla.lock`; code `manifest` or `lock file`), under the key or value it is about, and the document is checked alone. It is cleared like an error in an imported module (the `elsewhere` list) when a later check of the document finds none. A `didChangeWatchedFiles` naming a `myla.toml` or `myla.lock` queues every open document for a check, and the VS Code extension now watches those files too (`**/{*.my,myla.toml,myla.lock}`).
- **Checks** run `load_program_opts(path, ctx.opts)` instead of `load_program_with`: three lines in `Server.check`, plus the manifest diagnostic (kept small for the merge with [[MYLA-65]]).
- **Resolution** (`resolve.my`): `resolve` and `resolve_at` take the `LoadOptions` instead of the standard library and the overrides, and `module_file` follows the loader's order: a first segment naming a package resolves in its directory (`import geo` is `<dir>/geo.my`, `geo.shapes` is `<dir>/shapes.my`), anything else in the project root (the importing file's directory unless the options name one), then the standard library. So definition, hover, references and completion after `geo.` go into the dependency's modules.
- **References and the fallback by name** look in the workspace's files and in the document's package directories (`Workspace.files(extra)`), so a dependency outside the workspace (a path elsewhere, a Git checkout under the skipped `.myla/`) is searched too.
- `build/myla-lsp --resolve <file>` resolves a file inside a project with its packages as well.

## Evidence

- **Tests first:** `ProjectScenarios` (9 tests) and `WorkspaceScanScenarios` (2) in `tests/burn/_lsp_scenarios.py`, run by `TestMylaLspProjects` and `TestMylaLspWorkspaceScan` in `tests/burn/test_lsp.py` against the server built by both backends. Against the old server 9 of the first 10 failed for the right reasons (`cannot resolve import 'geo'`, `cannot resolve import 'helpers'` from `src/util/round.my`, definition `None`, completion `[]`, references only in `main.my`, no diagnostic for `myla.toml`, the definition of `in_deps` found under `.myla/`); the sorted-order test passed before and after (it guards the order). All pass now:
  - a project with a path dependency outside the workspace: `import geo` and `from geo.shapes import …` check clean; an error in `geo/src/shapes.my` is published for that file; definition of `geo.area`, of an imported name and of the module go into `geo`'s files; hover; references include the declaration and the uses in `geo`'s own modules; completion after `geo.` is `["area"]`;
  - a nested file `src/util/round.my` resolves `import helpers` from `src/` (diagnostics and definition);
  - a Git dependency checked out in `.myla/deps/color-<commit>/` with a `myla.lock`: clean, and definition into it;
  - a locked Git dependency that isn't checked out: `cannot resolve import 'color'` on the document (`geo` still resolves), the manifest diagnostic under the `color` key, and no `.myla/` created;
  - a manifest without `version`: the document is checked alone (no errors), the manifest gets ``missing 'version' in [package]`` under `[package]`; after fixing it on disk and a watched-file notification, both are cleared;
  - the scan finds `sub/deeper/ok.my` but nothing in `build/`, `.myla/`, `.git/` or `node_modules/`; the first of three `twin` functions in sorted path order (`a.my` before `a/z.my` and `b.my`) wins.
- **Timing** (`selfhost/checker.my`, the repository as workspace, median of 7 warm requests or 5 after an edit, same machine; before → after): definition 26 → 24 ms, hover 26 → 25 ms, references 80 → 65 ms (no `find` process), completion 170 → 170 ms, definition after an edit 300 → 297 ms, references after an edit 575 → 530 ms, a check on save 250 → 232 ms. In a small project with a path dependency a definition request after a notification (context and resolution made again) takes 0.3 ms, against 0.1 ms for a file alone.
- **Suites:** unit 544 → 544, integration 2 → 2, burn 653 → 675 (the 11 new scenarios on both builds), all passing. `scripts/bootstrap.sh` reaches its byte-identical fixed point (8,560,400 bytes, unchanged: `selfhost/` isn't touched) and builds `build/myla-lsp`.

## Open points

- A Git dependency's own Git dependencies are checked out under the root package's `.myla/deps/`. Opening a file of a Git checkout makes the checkout's `myla.toml` the project, whose Git dependencies aren't found there: they show as not checked out. Opening a dependency's file through the consumer's project would need the server to remember which project led there.
- The manifest's diagnostics come from checks of `.my` documents; an open `myla.toml` isn't checked itself (the extension's language client only syncs `myla` documents).
