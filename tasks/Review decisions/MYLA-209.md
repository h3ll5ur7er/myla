---
id: MYLA-209
title: "Decision: the generated tree-sitter grammar and its bindings in the repository"
type: chore
status: todo
priority: low
labels: [decision, editor, repository]
---
From the October 2026 review ([[Project/Review-2026-10]], §11.8 and §13.12). `editor/tree-sitter-myla` holds 1.6 MB of tracked files generated from [[grammar/myla.ebnf]] by `tools/grammar`: `grammar.js`, the generated `src/parser.c`, highlight queries, and six language bindings with their packaging (C, Go, Node, Python, Rust, Swift: `Cargo.toml`, `Package.swift`, `binding.gyp`, `setup.py`, `pyproject.toml`, `Makefile`). Nothing consumes the grammar yet but the grammar tests; the VS Code extension uses a TextMate grammar.

## Question

What of the tree-sitter output lives in the repository?

## Options

- **A. Everything, as today.**
- **B. The grammar, `src/parser.c` and the queries; no bindings.** Committing `parser.c` is the tree-sitter convention (Neovim, Helix and Zed build a grammar from its repository without the CLI); the bindings and packaging are regenerated with `tree-sitter init` when someone publishes a package.
- **C. Generated in CI only**: the repository keeps the EBNF, CI generates and tests the grammar and publishes it as an artifact (or into a separate `tree-sitter-myla` repository).

## Recommendation

**B now**: it removes the part nobody uses and keeps the part an editor would need. **C** when there is a consumer (an editor package, or the website, which could highlight with `web-tree-sitter`, [[MYLA-159]]).

## Decision

*Open.* The owner's answer goes here and, once given, onto [[Project/Decisions]] as a numbered decision.

- [ ] Decided, and recorded on [[Project/Decisions]]
- [ ] The implementation tasks created or updated to match
