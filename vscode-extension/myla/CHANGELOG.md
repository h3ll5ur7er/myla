# Changelog

## 0.1.0

- **Projects in the language server** (MYLA-97): a file inside a project (`myla.toml`) is checked with the project's dependencies, so their imports resolve and definition, references, hover and completion reach into them; manifest errors show on `myla.toml`. The file watcher also reports changes to `myla.toml` and `myla.lock`.
- **Debugger** (`myla` debug type, MYLA-99): `F5` on a `.my` file builds it with `myla build -g` (a project, its directory or `myla.toml`, with the project's own `myla build -g`, MYLA-94) and debugs it with gdb through the extension's own debug adapter (GDB/MI, no other extension needed). Line, conditional, hit-count and function breakpoints; continue, step over/in/out, pause; the call stack with Myla names; locals and arguments with expandable structs, tuples, enums and lists, and heap strings and lists inside them shown as values; evaluate and hover; `-exec` gdb commands in the Debug Console; stops on runtime errors with their message; program output and exit code in the Debug Console; Run Without Debugging. A build error stops the launch with the compiler's message and a jump to it. gdb loads the pretty-printers a `-g` binary embeds, so value summaries show heap values inside aggregates as values too (`Bag {items: [4, 5], label: "two"}`, MYLA-66).
- **Commands and tasks** (MYLA-100): *Run Current File*, *Run Tests in Current File*, *Build Current File* and *Debug Current File*, in the command palette and the editor title's run menu; tasks of type `myla` with a `$myla` problem matcher; *Show Output*. The placeholder *Show Extension Info* is gone.
- New settings `myla.cliPath` (the `myla` CLI: `build/myla`, else `python3 myla.py`) and `myla.debug.gdbPath`.
- A language status item shows whether the language server runs and restarts it.
- In untrusted workspaces the path settings come from user settings only.
- Bundled with esbuild: the `.vsix` holds two scripts and the static files, no `node_modules`. An icon, a license (MIT), and the template's leftovers removed.
- Built, tested and packaged in CI; each run uploads the `.vsix` (MYLA-101).

## Before 0.1.0

- The Python language server is retired: the extension starts only `build/myla-lsp`, and says how to build it when it is missing; the settings `myla.server` and `myla.pythonPath` are gone.
- Starts the language server written in Myla (`build/myla-lsp`); the `**/*.my` file watcher reports changes on disk to it.
- The grammar and snippets follow the real language: no Rust-dialect keywords, the real type names and literal forms, `;` as an optional separator; every snippet is valid Myla.
- `myla.trace.server` works, `myla.diagnostics.enable = false` hides only the diagnostics, and `${workspaceFolder}` is expanded in path settings.
- 0.0.1: highlighting, snippets and the Python language server client.
