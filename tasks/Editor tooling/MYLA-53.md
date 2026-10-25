---
id: MYLA-53
title: VS Code extension settings and packaging
type: bug
status: backlog
priority: low
labels: [vscode]
---
In `vscode-extension/myla/`:

- [ ] `myla.trace.server` does nothing: vscode-languageclient reads `<clientId>.trace.server` and the client id is `mylaLanguageServer`
- [ ] `myla.diagnostics.enable = false` stops the whole server, hover and definition included
- [ ] The `**/*.my` file watcher sends notifications the server ignores
- [ ] `${workspaceFolder}` isn't expanded in the path settings
- [ ] `myla.formatFile` is a stub command
- [ ] `publisher` is still `your-publisher-name`; there's no `.vscodeignore` content to keep `src/`, `LSP_DESCRIPTION.md` and the examples out of the `.vsix`
- [ ] README says the extension is a "scaffold for future language-server integration"; CHANGELOG is the template
- [ ] `examples/` duplicates four files of the top-level `examples/` byte for byte
