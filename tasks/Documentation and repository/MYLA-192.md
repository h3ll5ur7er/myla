---
id: MYLA-192
title: "Repository hygiene: timer.py, duplicate scripts, stray test output"
type: chore
status: todo
priority: low
labels: [repository, tests]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]).

- `timer.py` at the repository root is an unrelated stopwatch script (committed with MYLA-53/55); nothing references it
- `scripts/run.sh` and `scripts/samples.sh` duplicate the justfile's `run` and `run-all` and go through `build/stage3`; the justfile's `bs` recipe needs `uv` in a project without dependencies, and `asm2bin` predates `myla build`
- `.vscode/settings.json` holds only comments
- the burn tests print stray `wrote /tmp/...` lines to stdout (`test_debug_info.py`), and `test_lsp.py:756` leaks an unclosed file (a `ResourceWarning`)
- the tree-sitter package commits six language bindings nobody consumes (`editor/tree-sitter-myla/bindings/`); `parser.c` (1.3 MB) is regenerated in grammar commits and dominates their diffs (acceptable for tree-sitter, worth `linguist-generated` and a note)

- [ ] Each removed or consolidated; CI caching of `build/test-tools` and the tree-sitter npm install with [[MYLA-156]]
