---
id: MYLA-232
title: "Drop the tree-sitter bindings and packaging from the repository"
type: chore
status: review
priority: low
labels: [editor, repository, tree-sitter]
---
D111 ([[MYLA-209]]): `editor/tree-sitter-myla` keeps the generated `grammar.js`, `src/parser.c` (with `src/tree_sitter/` and `node-types.json`) and the queries; the six bindings (`bindings/c`, `go`, `node`, `python`, `rust`, `swift`) and their packaging (`Cargo.toml`, `Package.swift`, `binding.gyp`, `setup.py`, `pyproject.toml`, `Makefile`, the package files the tests don't need) go.

- [x] Which of the files the grammar tests and CI need (the tree-sitter CLI wants `package.json` or `tree-sitter.json`), the rest removed and ignored
- [x] [[Architecture/Editor-tooling]] says how to regenerate the bindings (`tree-sitter init`) when a package is published

## Evidence

- **Kept:** `grammar.js`, `src/`, `queries/`, `tree-sitter.json`, `README.md`, `.gitattributes`, `.gitignore`, and `package.json` with its lock.
  - `test_src_is_current` copies `grammar.js` and `tree-sitter.json` to generate.
  - CI installs the CLI with `npm ci` from the lock.
  - `package.json` is now private and has one dev dependency, `tree-sitter-cli`. Gone are the Node binding's `main`, `types`, `files`, the install and prebuildify scripts, `node-gyp-build` and the peer dependency. The lock loses 351 lines with it.
- **Removed:** `bindings/` (C, Go, Node, Python, Rust, Swift), `Cargo.toml`, `Package.swift`, `binding.gyp`, `setup.py`, `pyproject.toml`, `Makefile` and `.editorconfig`. `.gitignore` names them, so a `tree-sitter init` for publishing leaves them out.
- **Docs:** [[Architecture/Editor-tooling]] and the package's README say how to get the bindings back (`tree-sitter init`, then publish from that working copy).
- **Checks:**
  - CI's install recipe works on the new files in an empty directory (`npm ci --ignore-scripts`, the CLI's `install.js`, `tree-sitter --version` gives 0.25.10).
  - `test_grammar.py` passes (10 tests: the generated files current, every source file parsed, the queries compiling).
  - `scripts/gen_treesitter.sh` changes nothing and recreates none of the removed files.

