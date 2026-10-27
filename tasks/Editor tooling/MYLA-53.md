---
id: MYLA-53
title: VS Code extension settings and packaging
type: bug
status: review
priority: low
labels: [vscode]
---
In `vscode-extension/myla/`:

- [x] `myla.trace.server` does nothing: vscode-languageclient reads `<clientId>.trace.server` and the client id is `mylaLanguageServer`
- [x] `myla.diagnostics.enable = false` stops the whole server, hover and definition included
- [x] The `**/*.my` file watcher sends notifications the server ignores
- [x] `${workspaceFolder}` isn't expanded in the path settings
- [x] `myla.formatFile` is a stub command
- [x] `publisher` is still `your-publisher-name`; there's no `.vscodeignore` content to keep `src/`, `LSP_DESCRIPTION.md` and the examples out of the `.vsix`
- [x] README says the extension is a "scaffold for future language-server integration"; CHANGELOG is the template
- [x] `examples/` duplicates four files of the top-level `examples/` byte for byte

## How

In [[vscode-extension/myla/]]:

- The client id is `myla`, so vscode-languageclient reads `myla.trace.server`.
- `myla.diagnostics.enable = false` no longer keeps the server from starting: a `handleDiagnostics` middleware drops the diagnostics and everything else keeps working.
- The `**/*.my` watcher is gone until a server handles `didChangeWatchedFiles` (noted on [[MYLA-80]]).
- `expandPath` expands `${workspaceFolder}`, `${userHome}` and `~` in `myla.compilerPath` and `myla.pythonPath`.
- The `Myla: Format File` stub is removed (there is no formatter).
- `publisher` is `h3ll5ur7er` (the repository owner) and `repository` is set; `.vscodeignore` keeps sources, maps and `.vsix` files out of the package; the committed `myla-language-support-0.0.1.vsix` is deleted and ignored; the duplicated `examples/` and the stale `LSP_DESCRIPTION.md` brief are deleted ([[MYLA-56]]).
- README and CHANGELOG describe the actual extension.

## Evidence

- `npx tsc -p ./ --noEmit` passes; `expandPath`, compiled and run under node with a stubbed `vscode`, gives `${workspaceFolder}/myla.py` → `/w/proj/myla.py`, `~/venv/bin/python` → `/home/u/venv/bin/python`.
- `npx vsce ls` lists only the manifest, README, CHANGELOG, language configuration, snippets, grammar and the production dependency `vscode-languageclient` (no `src/`, no examples).
- Not tried in a running VS Code here (no GUI in this environment).
