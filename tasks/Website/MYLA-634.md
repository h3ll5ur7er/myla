---
id: MYLA-634
title: "The website's learn area: gamified exercises checked by #test"
type: feature
status: review
priority: high
labels: [website, learn, tutorial]
---
Inspired by rustlings and boot.dev (MYLA-159, D208): chapters of small exercises, each a `.my` file in `learn/` with a broken or unfinished program and `#test` cases that pass once it is fixed, its solution beside it; CI checks that every exercise fails as given and passes solved. In the browser: the exercise in the editor, Check runs its tests, progress kept in the browser.

- [x] The exercise format and the chapters (the language from the first program to traits, generics, errors and concurrency), with hints
- [x] Gamification: XP, levels with titles, a daily streak, achievements, chapters that unlock, boss exercises, celebrations
- [x] The learn pages: the map of chapters, an exercise with its instructions, tests, hints and solution, the profile with progress and achievements
- [x] A burn test: every exercise fails as given and passes with its solution

## Evidence

- `learn/`: 8 chapters, 48 exercises, 1,635 XP (the top level needs 1,380): Don't Panic (values, let and var, f-strings, conversions), The Grand Line (if, while, for, match, break and continue), Shadow Clone Jutsu (returns, recursion, defaults, closures, function values, pipelines), Infinity Stones (lists, filter, map, maps, strings), The Straw Hat Crew (structs, methods, var self, enums, payloads, Format), Pied Piper (Option, Result, ?, error enums, run-length coding), Avengers Assemble (traits, bounds, generic structs, Add, Mul<int>), Deep Thought (writing tests, async, async let, actors, JSON, task.all). Each has hints, a boss, and pop culture.
- Every exercise unsolved as given and solved by its solution: natively (`tests/burn/test_website.py`, 48) and in `play.wasm` (`npm run check-course`, 48 in 20 s).
- Gamification (`core/gamification.ts`, 12 specs): XP (hints at 15 % each down to half, nothing with the solution shown first), 13 levels from Mostly Harmless to Pirate King, daily streaks, 17 achievements, unlocks (a chapter at 60 % of the one before, a boss after its chapter; sudo mode), confetti and toasts; progress in `localStorage`, exported and imported as a file. A locked exercise solved early counts only once it opens.
- In Chromium (e2e): an exercise solved earns `+10 XP` and "Don't Panic", and stays solved after a reload; a wrong answer shows the program's output.
