# Myla for VS Code

Support for the [Myla](https://github.com/h3ll5ur7er/myla) programming language (`.my` files): highlighting, the Myla language server, commands to run, test and build, and a debugger built on gdb.

## Features

- **Editing:** syntax highlighting (a TextMate grammar, plus semantic highlighting from the language server), snippets, comment toggling, bracket matching and auto-closing, `// region` folding.
- **Language server** (`build/myla-lsp`, written in Myla): the compiler's diagnostics, document outline, go to definition, find references and hover resolved by scope, imports and type, and completion of members after `.` and of the names in scope. A file inside a project (`myla.toml`) is checked with the project's dependencies, and manifest errors show on `myla.toml`.
- **Run, test, build:** *Myla: Run Current File*, *Myla: Run Tests in Current File* and *Myla: Build Current File* (also the ▷ menu in the editor title) run `myla run`, `myla test` and `myla build` in a terminal; errors land in the Problems view. The same commands are tasks of type `myla` for `tasks.json`.
- **Debugger:** `F5` on a `.my` file builds it with `myla build -g` and debugs it with gdb, no launch configuration needed:
  - line breakpoints (conditions and hit counts too), function breakpoints such as `main` or `Point.len`;
  - continue, step over, step in, step out, pause; the call stack with Myla function names;
  - locals and arguments, with structs, tuples, enums and lists to expand, and strings and lists inside structs shown as values;
  - evaluate in the Debug Console and on hover (gdb's Rust syntax, which is close to Myla's: `xs[1] * 10`, `p.x`); `-exec <command>` runs a gdb command;
  - stop where a runtime error happens (division by zero, an index out of range, `panic`, `assert`) with its message, the program's output in the Debug Console, and its exit code.

## Requirements

- x86-64 Linux: Myla compiles to native Linux binaries.
- The Myla toolchain: a checkout of the repository with `scripts/bootstrap.sh` run, which builds `build/myla` and `build/myla-lsp` from the committed seed with GNU `as` and `ld` alone. Open the repository as a workspace folder, or point `myla.compilerPath` at it. Without `build/myla` the commands say how to build it.
- For debugging: gdb (`sudo apt install gdb`), and GNU `as`/`ld` for the build.

## Settings

| Setting | Meaning |
| --- | --- |
| `myla.compilerPath` | The repository root, the folder with `selfhost/main.my` (a file directly in it works too). Empty: the workspace folder that has a `selfhost/main.my`. The language server gets the standard library from its `lib` folder. |
| `myla.serverPath` | The language server. Empty: `build/myla-lsp` in the repository. |
| `myla.cliPath` | The `myla` CLI for run, test, build and debugging. Empty: `build/myla` in the repository. |
| `myla.debug.gdbPath` | The gdb to debug with (default `gdb`). |
| `myla.diagnostics.enable` | Show the compiler's diagnostics (the server keeps running when off). |
| `myla.trace.server` | Trace the language server protocol in the Myla output channel. |

`${workspaceFolder}`, `${userHome}` and `~` are expanded in the path settings. In an untrusted workspace, the path settings are read from your user settings only.

## Debugging

Without a `launch.json`, `F5` (or *Myla: Debug Current File*) debugs the active file. A launch configuration can name the program, its arguments and more:

```json
{
  "type": "myla",
  "request": "launch",
  "name": "Debug main.my",
  "program": "${workspaceFolder}/main.my",
  "args": ["input.txt"],
  "cwd": "${workspaceFolder}",
  "stopOnEntry": false
}
```

| Attribute | Meaning |
| --- | --- |
| `program` | The `.my` file to build and debug (a binary built with `-g` works too). |
| `args`, `cwd`, `env` | The program's arguments, working directory and extra environment variables. |
| `stdin` | A file the program reads as standard input (default: none). |
| `stopOnEntry` | Stop at the first line of `main`. |
| `gdbPath` | The gdb for this configuration. |
| `trace` | Show the adapter's conversation with gdb (GDB/MI) in the Debug Console. |

The debug build goes to the extension's storage folder, not into your workspace. Runtime errors stop the program by default; untick *Runtime errors* in the Breakpoints view to let them end it.

## Development

```bash
npm ci
npm run build        # bundle src/ into out/ with esbuild (npm run watch to rebuild on change)
npm run typecheck    # tsc, no output
npm run lint         # eslint
npm test             # unit tests and the debugger against real gdb (with the repository's build/myla)
npx vsce package     # myla-language-support-<version>.vsix
```

Open this folder in VS Code and press `F5` to start an Extension Development Host. The debug adapter also runs on its own, speaking DAP on stdio: `node out/debugAdapter.js`.
