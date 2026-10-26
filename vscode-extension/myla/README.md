# Myla Language Support

VS Code support for the [Myla](https://github.com/h3ll5ur7er/myla) programming language (`.my` files).

## Features

- Syntax highlighting (a TextMate grammar) and snippets; a unit test in the Myla repository (`tests/unit/test_vscode_extension.py`) keeps both in step with the compiler
- Comment toggling, bracket matching and auto-closing pairs, `// region` folding
- The Myla language server: compiler diagnostics (for the file an error is in), document outline, go to definition, find references, hover and completion

## Settings

| Setting | Meaning |
| --- | --- |
| `myla.compilerPath` | The repository root or `myla.py`. Empty: the `myla.py` of a workspace folder. |
| `myla.pythonPath` | The Python that runs the server. Empty: the `.venv` next to `myla.py`, then `python`. |
| `myla.diagnostics.enable` | Show the compiler's diagnostics (the server keeps running when off). |
| `myla.trace.server` | Trace the protocol in the Myla output channel. |

`${workspaceFolder}`, `${userHome}` and `~` are expanded in the two path settings.

The server is the Python one (`myla lsp`, needs `pygls`: `uv sync --extra lsp`). A server written in Myla is planned (task MYLA-80 in the repository).

## Development

```bash
npm install
npm run compile      # or: npm run watch
npm run package      # builds the .vsix (not committed)
```

Open this folder in VS Code and press `F5` to start an Extension Development Host. `Developer: Inspect Editor Tokens and Scopes` shows how a token is highlighted.
