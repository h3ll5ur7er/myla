---
id: MYLA-159
title: A website for Myla - an Angular webapp with docs, an online editor and a tutorial
type: feature
status: backlog
priority: low
labels: [website, docs, tutorial, wasm]
---
A modern Angular webapp as the home of the Myla programming language. It comes after the LLVM ([[MYLA-62]]) and WebAssembly ([[MYLA-158]]) work: its editor and tutorial run the real toolchain in the browser.

## Goals

- **A visual masterpiece:** a stunning first impression, yet easy to use, fast to load and not overcrowded.
- **A hero landing page:** what Myla is and why, a live snippet, the way in to the rest.
- **Getting started:** a simple page with great, straightforward and well-documented examples.
- **The full language reference:** concepts, philosophy, the builtins, the standard library and the rest, from the wiki ([[Language]], [[Project/Decisions]]) rather than a second copy.
- **An online editor:** Monaco, with the compiler, interpreter and analyzer running as wasm ([[MYLA-158]]): diagnostics as you type, run with output, maybe hovers and completion from the language server's logic.
- **A tutorial that is heavily gamified,** somewhere between rustlings and boot.dev: small exercises checked by tests (`#test`), progress, streaks, levels and achievements, hints, chapters that unlock.
- **No backend:** everything lives in the browser (IndexedDB: progress, saved programs, settings). The site is static and can be hosted anywhere (GitHub Pages).

## Questions to settle first

- The content pipeline: generate the reference and the getting-started pages from `docs/` at build time (Markdown with `[[…]]` links and `myla` code blocks), so the wiki stays the single source; examples checked by the toolchain in CI so none goes stale.
- The tutorial's exercise format (a `.my` file with `#test` cases and hints, its order and unlocks), and where the exercises live in the repository.
- The design language (typography, colour, motion; light and dark), a performance budget (first load, wasm size, lazy loading of Monaco and the toolchain) and accessibility.
- The Angular setup: a current version, standalone components and signals, prerendering of the static pages, an offline-capable service worker.
- The editor's language support: the tree-sitter grammar or a Monarch grammar generated from `grammar/myla.ebnf` ([[MYLA-154]]), and the language server's features through wasm.

## Done when

- [ ] The questions above decided and recorded
- [ ] Landing, getting started, reference, editor and tutorial pages, all static, data in IndexedDB only
- [ ] Every code example on the site checked by the toolchain in CI
- [ ] Deployed, with load times within the budget
