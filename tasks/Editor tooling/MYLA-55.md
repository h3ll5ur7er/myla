---
id: MYLA-55
title: Workspace settings point at another machine
type: chore
status: review
priority: low
labels: [vscode, repo]
---
`.vscode/settings.json` hard-codes `/home/coder/project/myla.py` and its `.venv`, and points tree-sitter-vscode at `/home/eknecht/code/myla/editor/...` (moved from `rust/editor/` in [[MYLA-70]]). In any other checkout the extension can't find the compiler and shows a warning.

- [x] Use `${workspaceFolder}`-relative paths (which needs the extension fix in [[MYLA-53]]) or drop the file from version control

## How

`.vscode/settings.json` no longer names another machine's paths: the extension finds `myla.py` and the `.venv` in the workspace by itself, and the file only shows, commented out, how to override them with `${workspaceFolder}` (expanded since [[MYLA-53]]). The `tree-sitter-vscode` configuration is gone: it pointed at the outdated grammar, which [[MYLA-77]] replaces.
