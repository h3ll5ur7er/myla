# Editor tooling

[TOC]

## Language server

`src/myla/lsp/` is a language server built on pygls 2 over stdio. It is an optional extra, so the rest of the toolchain stays dependency-free.

```bash
uv sync --extra lsp
python3 myla.py lsp            # or: python -m myla.lsp
```

| Module | Role |
| --- | --- |
| `server.py` | pygls server, document store, debounced diagnostics, feature handlers |
| `compiler_adapter.py` | Runs `loader.link` + `types.check` on a buffer and turns a `MylaError` into a diagnostic |
| `positions.py` | 1-based code-point positions ↔ 0-based UTF-16 LSP positions; squiggle width |
| `symbols.py` | Builds a symbol tree from the parsed buffer; outline; picks the best declaration |
| `lookup.py` | The identifier under the cursor and every occurrence, from the token stream |
| `definition.py`, `hover.py`, `references.py`, `completion.py` | The features |
| `workspace.py` | Scans the workspace's `.my` files (mtime-cached symbols) |

**Diagnostics** use the real compiler: the open buffer is passed to the loader as a source override, so unsaved text is checked. The compiler stops at the first error, so there is at most one diagnostic. Opening and saving check immediately; edits are debounced by 0.4 s.

**Everything else is name-based**: the buffer is only lexed and parsed (not checked), and definitions, hover, references and completion match identifiers by name in the file and across the workspace. Imports and scopes are ignored, locals don't resolve, and member completion offers every known member.

Supported: `didOpen`/`didChange`/`didSave`/`didClose`, `documentSymbol`, `definition`, `hover`, `references`, `completion`. Not supported: formatting, rename, semantic tokens, signature help, code actions, workspace symbols.

A declaration's selection range (the target of go-to-definition, and the token `includeDeclaration: false` drops from references) is its name token, found in the token stream from the declaration's keyword (MYLA-48); for an `impl` it is the target type. Positions sent by the editor are UTF-16 offsets, which `positions.from_lsp_character` converts before a line is sliced.

An error in an imported module is published for that module's URI (it shows in the Problems panel and in that file), and cleared there once a later check of the importing document no longer finds it (MYLA-10); other open buffers are checked with their unsaved text. `tests/integration/test_lsp_diagnostics.py` drives the real server over stdio when pygls is installed; `tests/unit/test_lsp_features.py` covers positions, symbols, definition, references and completion without it (MYLA-52).

Open problems: [[MYLA-49]], [[MYLA-50]], [[MYLA-51]].

## VS Code extension

`vscode-extension/myla/` contributes the `myla` language for `.my` files: a TextMate grammar, snippets, a language configuration and a language client.

- The client looks for `myla.py` (setting `myla.compilerPath`, then the workspace folders) and for Python (`myla.pythonPath`, then `<repo>/.venv`, then `python`), and starts `python myla.py lsp` with the repository as working directory. Changing a setting restarts the server.
- Settings: `myla.compilerPath`, `myla.pythonPath`, `myla.diagnostics.enable`, `myla.trace.server`.
- A packaged `myla-language-support-0.0.1.vsix` is checked in.

Open problems: [[MYLA-53]], [[MYLA-54]], [[MYLA-55]].

## tree-sitter grammar

`editor/tree-sitter-myla/` is a tree-sitter grammar (with bindings for C, Go, Node, Python, Rust and Swift, and highlight, fold, indent and injection queries). It was written for the removed [[Architecture/Rust-edition]]'s dialect, still follows it in places and is looser than the real parser ([[MYLA-47]]).
