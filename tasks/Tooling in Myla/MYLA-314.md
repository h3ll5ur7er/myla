---
id: MYLA-314
title: "The standard library's everyday helpers (strings, sorting, collections, hashes)"
type: feature
status: backlog
priority: high
labels: [stdlib]
---
Found by Advent of Code ([[Project/AoC-2015-2021]], F5). There is no `split`, `trim`, `join`, `lines`, `sort`, integer `abs`/`min`/`max`, set, queue or heap. The agent's `lib/aoc/text.my` was imported in about 150 of 175 solutions, and any real program needs these first. Its `md5.my` dominated three of the six slowest days.

The whole list of candidate modules, with usefulness, cost and a suggested order, is [[Project/Standard-library-roadmap]]. This task is its umbrella: once the owner has reviewed and ordered the table, each row picked becomes a task of its own, and this task tracks them.

- [ ] The roadmap reviewed and ordered by the owner
- [ ] One task per row picked
