---
id: MYLA-232
title: "Drop the tree-sitter bindings and packaging from the repository"
type: chore
status: todo
priority: low
labels: [editor, repository, tree-sitter]
---
D111 ([[MYLA-209]]): `editor/tree-sitter-myla` keeps the generated `grammar.js`, `src/parser.c` (with `src/tree_sitter/` and `node-types.json`) and the queries; the six bindings (`bindings/c`, `go`, `node`, `python`, `rust`, `swift`) and their packaging (`Cargo.toml`, `Package.swift`, `binding.gyp`, `setup.py`, `pyproject.toml`, `Makefile`, the package files the tests don't need) go.

- [ ] Which of the files the grammar tests and CI need (the tree-sitter CLI wants `package.json` or `tree-sitter.json`), the rest removed and ignored
- [ ] [[Architecture/Editor-tooling]] says how to regenerate the bindings (`tree-sitter init`) when a package is published
