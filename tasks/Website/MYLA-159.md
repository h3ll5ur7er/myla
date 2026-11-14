---
id: MYLA-159
title: A website for Myla - an Angular webapp with docs, an online editor and a tutorial
type: feature
status: in-progress
priority: high
labels: [website, docs, tutorial, wasm]
---
A modern Angular webapp as the home of the Myla programming language. It comes after the platform work ([[MYLA-62]]) and WebAssembly ([[MYLA-158]]): its editor and tutorial run the real toolchain in the browser.

## Goals

- **A visual masterpiece:** a stunning first impression, yet easy to use, fast to load and not overcrowded.
- **A hero landing page:** what Myla is and why, a live snippet, the way in to the rest.
- **Getting started:** a simple page with great, straightforward and well-documented examples.
- **The full language reference:** concepts, philosophy, the builtins, the standard library and the rest, from the wiki ([[Language]], [[Project/Decisions]]) rather than a second copy.
- **An online editor:** Monaco, with the compiler, interpreter and analyzer running as wasm ([[MYLA-158]]): diagnostics as you type, run with output, maybe hovers and completion from the language server's logic.
- **A tutorial that is heavily gamified,** somewhere between rustlings and boot.dev: small exercises checked by tests (`#test`), progress, streaks, levels and achievements, hints, chapters that unlock.
- **No backend:** everything lives in the browser (IndexedDB: progress, saved programs, settings). The site is static and can be hosted anywhere (GitHub Pages).

## The owner's brief (2026-11-14)

A modern Angular webapp that looks awesome with great UX: a hero landing page, downloads, quickstart, documentation, reference, learn and the usual pages; the full language documentation; a comprehensive reference including the builtins and the standard library; lots of code examples in a reusable embedded editor that lets you try everything everywhere; as many funny, nerdy pop-culture references as fit without feeling forced (The Hitchhiker's Guide to the Galaxy, One Piece, Naruto, Marvel, Silicon Valley, …); a gamification-heavy interactive learning area inspired by boot.dev and rustlings. Decided with the owner: CodeMirror 6 (not Monaco), GitHub Pages, a full first version in one pull request (D208).

The work, one task each:

- [[MYLA-630]] The app: shell, design system, landing, downloads, quickstart, search
- [[MYLA-631]] The content pipeline: the wiki's language and library pages as the site's docs
- [[MYLA-632]] The API reference generated from `lib/std` by the real parser (`tools/doc`)
- [[MYLA-633]] The embedded editor and the playground: CodeMirror 6, a Myla mode, the toolchain in a worker
- [[MYLA-634]] Learn: exercises checked by `#test`, XP, levels, streaks, achievements, unlocks
- [[MYLA-635]] CI: the site built and tested, the exercises checked, deployed to GitHub Pages

## Questions to settle first

- The content pipeline: generate the reference and the getting-started pages from `docs/` at build time (Markdown with `[[…]]` links and `myla` code blocks), so the wiki stays the single source; examples checked by the toolchain in CI so none goes stale.
- The tutorial's exercise format (a `.my` file with `#test` cases and hints, its order and unlocks), and where the exercises live in the repository.
- The design language (typography, colour, motion; light and dark), a performance budget (first load, wasm size, lazy loading of Monaco and the toolchain) and accessibility.
- The Angular setup: a current version, standalone components and signals, prerendering of the static pages, an offline-capable service worker.
- The editor's language support: the tree-sitter grammar or a Monarch grammar generated from `grammar/myla.ebnf` ([[MYLA-154]]), and the language server's features through wasm.

## Done when

- [x] The questions above decided and recorded (D208)
- [x] Landing, getting started, reference, editor and tutorial pages, all static, data in the browser only (localStorage, D208)
- [x] Every code example on the site checked by the toolchain in CI (the wiki's blocks by test_doc_blocks, the samples and the course by test_website and check-course)
- [ ] Deployed, with load times within the budget
