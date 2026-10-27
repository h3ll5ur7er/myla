# Myla Language Support

VS Code support for the [Myla](https://github.com/h3ll5ur7er/myla) programming language (`.my` files).

## Features

- Syntax highlighting (a TextMate grammar) and snippets; a unit test in the Myla repository (`tests/unit/test_vscode_extension.py`) keeps both in step with the compiler
- Comment toggling, bracket matching and auto-closing pairs, `// region` folding
- The Myla language server: compiler diagnostics (for the file an error is in), document outline, go to definition, find references and hover resolved by scope, imports and type, completion of a receiver's members after `.` and of the locals in scope, and semantic highlighting from the compiler's lexer

## Settings

| Setting | Meaning |
| --- | --- |
| `myla.serverPath` | The language server's binary. Empty: `build/myla-lsp` in the repository. |
| `myla.compilerPath` | The repository root or `myla.py`. Empty: the `myla.py` of a workspace folder. |
| `myla.diagnostics.enable` | Show the compiler's diagnostics (the server keeps running when off). |
| `myla.trace.server` | Trace the protocol in the Myla output channel. |

`${workspaceFolder}`, `${userHome}` and `~` are expanded in the path settings.

The language server is written in Myla; `scripts/bootstrap.sh` builds it as `build/myla-lsp` (x86-64 Linux). When it isn't built, the extension says so. The extension reports changes to `.my` files on disk to it.

## Development

```bash
npm install
npm run compile      # or: npm run watch
npm run package      # builds the .vsix (not committed)
```

Open this folder in VS Code and press `F5` to start an Extension Development Host. `Developer: Inspect Editor Tokens and Scopes` shows how a token is highlighted.
