---
id: MYLA-70
title: Remove the Rust edition from the repository
type: chore
status: backlog
priority: low
labels: [rust, cleanup]
---
The Rust edition was an experiment: a faster stage 0 for the bootstrap and a testbed for actors ([[Architecture/Rust-edition]]). The bootstrap speed problem has a much cheaper fix ([[MYLA-60]], [[MYLA-16]]), and actors will be designed in the main toolchain ([[MYLA-61]]). Once nothing depends on it, delete `rust/` entirely.

## Before deleting

- [ ] Bootstrap fixes landed, so nobody needs a faster stage 0
- [ ] Anything worth keeping from the actor prototype and `rust/docs/concurrency.md` is noted in [[MYLA-61]]
- [ ] The tree-sitter grammar in `rust/editor/tree-sitter-myla/` (follows the Rust dialect, [[MYLA-47]]): move it to `editor/` and align it with the real grammar, or drop it; `.vscode/settings.json` points at it ([[MYLA-55]])
- [ ] The VS Code grammar and snippets lose their Rust-dialect keywords ([[MYLA-54]])

## Done when

- [ ] `rust/` removed; references in the wiki ([[Architecture/Rust-edition]], [[Home]], [[Architecture]], [[Project/Known-issues]]) removed or turned into a short history note
- [ ] The Rust tasks [[MYLA-36]] … [[MYLA-47]] moved to `done` with "Rust edition removed (MYLA-70)"
