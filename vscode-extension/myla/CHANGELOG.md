# Change Log

## [Unreleased]

- The Python language server is retired: the extension starts only `build/myla-lsp`, and says how to build it when it is missing; the settings `myla.server` and `myla.pythonPath` are gone.
- Starts the language server written in Myla (`build/myla-lsp`) by default, falling back to the Python server when it isn't built; new settings `myla.server` and `myla.serverPath`. The `**/*.my` file watcher is back for the Myla server, which handles `workspace/didChangeWatchedFiles`.
- The grammar and snippets follow the real language: no Rust-dialect keywords, the real type names and literal forms, `;` as an optional separator; every snippet is valid Myla.
- `myla.trace.server` works, `myla.diagnostics.enable = false` hides only the diagnostics, and `${workspaceFolder}` is expanded in path settings.
- Removed the placeholder `Myla: Format File` command and the file watcher whose notifications the server ignored.

## 0.0.1

- Initial version: highlighting, snippets and the Python language server client.
