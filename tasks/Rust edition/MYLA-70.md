---
id: MYLA-70
title: Remove the Rust edition from the repository
type: chore
status: review
priority: low
labels: [rust, cleanup]
---
The Rust edition was an experiment: a faster stage 0 for the bootstrap and a testbed for actors ([[Architecture/Rust-edition]]). The bootstrap speed problem had a much cheaper fix ([[MYLA-60]], [[MYLA-16]]), and actors will be designed in the main toolchain ([[MYLA-61]]). Removed on 2026-10-25; the last commit containing `rust/` is `043acb9` (`git checkout 043acb9 -- rust` brings it back).

## Before deleting

- [x] Bootstrap fixes landed, so nobody needs a faster stage 0 (about 8 seconds)
- [x] Anything worth keeping from the actor prototype and `rust/docs/concurrency.md` is noted in [[MYLA-61]] (surface syntax, runtime, and what went wrong)
- [x] The tree-sitter grammar moved from `rust/editor/tree-sitter-myla/` to `editor/tree-sitter-myla/`; `.vscode/settings.json` points there ([[MYLA-55]] still tracks that file's machine-specific paths); aligning it with the real grammar is [[MYLA-47]], now in the Editor tooling epic
- [x] The VS Code grammar and snippets lose their Rust-dialect keywords: left to [[MYLA-54]] (it concerns the extension, not `rust/`), which removed them (in review; no `actor`, `spawn`, `chan`, `select`, `async` or `await` is left in the extension's grammar or snippets)

## Done when

- [x] `rust/` removed (52 tracked files, plus the untracked `target/` build directory); the stray empty `rust/editor/package-lock.json` went with it
- [x] References in the wiki removed or turned into a short history note: [[Architecture/Rust-edition]] is now that note; [[Home]], [[Architecture]], [[Development]], [[Development/Testing]], [[Development/Conventions]], [[Getting-started]], [[Language]], [[Project/Roadmap]], [[Project/Known-issues]] and [[Architecture/Editor-tooling]] updated, and the `myla` skill warns about the old dialect
- [x] The Rust tasks [[MYLA-36]] … [[MYLA-46]] moved to `done` with "Rust edition removed (MYLA-70)"; [[MYLA-47]] (the grammar) stays open
