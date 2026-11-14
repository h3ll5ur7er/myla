---
id: MYLA-634
title: "The website's learn area: gamified exercises checked by #test"
type: feature
status: todo
priority: high
labels: [website, learn, tutorial]
---
Inspired by rustlings and boot.dev (MYLA-159, D208): chapters of small exercises, each a `.my` file in `learn/` with a broken or unfinished program and `#test` cases that pass once it is fixed, its solution beside it; CI checks that every exercise fails as given and passes solved. In the browser: the exercise in the editor, Check runs its tests, progress kept in the browser.

- [ ] The exercise format and the chapters (the language from the first program to traits, generics, errors and concurrency), with hints
- [ ] Gamification: XP, levels with titles, a daily streak, achievements, chapters that unlock, boss exercises, celebrations
- [ ] The learn pages: the map of chapters, an exercise with its instructions, tests, hints and solution, the profile with progress and achievements
- [ ] A burn test: every exercise fails as given and passes with its solution
