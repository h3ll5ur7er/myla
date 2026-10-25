---
id: MYLA-55
title: Workspace settings point at another machine
type: chore
status: backlog
priority: low
labels: [vscode, repo]
---
`.vscode/settings.json` hard-codes `/home/coder/project/myla.py` and its `.venv`, and points tree-sitter-vscode at `/home/eknecht/code/myla/editor/...` (moved from `rust/editor/` in [[MYLA-70]]). In any other checkout the extension can't find the compiler and shows a warning.

- [ ] Use `${workspaceFolder}`-relative paths (which needs the extension fix in [[MYLA-53]]) or drop the file from version control
