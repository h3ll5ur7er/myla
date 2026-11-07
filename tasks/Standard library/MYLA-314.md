---
id: MYLA-314
title: "The standard library's extensions (the umbrella of the roadmap's tasks)"
type: feature
status: todo
priority: high
labels: [stdlib]
---
Found by Advent of Code ([[Project/AoC-2015-2021]], F5). There is no `split`, `trim`, `join`, `lines`, `sort`, integer `abs`/`min`/`max`, set, queue or heap. The agent's `lib/aoc/text.my` was imported in about 150 of 175 solutions, and any real program needs these first. Its `md5.my` dominated three of the six slowest days.

[[Project/Standard-library-roadmap]] lists 68 candidate modules with their use, size and order. Its plan ([[Project/Standard-library-roadmap#The plan]]) groups the rows into the tasks of this folder, in four waves, with the lane rules that let several agents work at once. This task tracks the waves.

- [ ] Wave 1, foundations: [[MYLA-319]] (the conventions, the owner's decision), [[MYLA-320]] (the implicit imports), [[MYLA-325]] (the docs split and the module test), [[MYLA-321]] `std.str`, [[MYLA-322]] `std.char` and `std.int`, [[MYLA-323]] `std.list`, [[MYLA-324]] `std.option` and `std.map`; [[MYLA-336]] (the platform primitives) and [[MYLA-310]] beside them
- [ ] Wave 2, collections, hashes and formats: [[MYLA-326]] to [[MYLA-335]], [[MYLA-338]]; [[MYLA-315]], [[MYLA-313]] and [[MYLA-318]] on the compiler track
- [ ] Wave 3, streams and the middle tier: [[MYLA-337]], [[MYLA-339]] to [[MYLA-345]], [[MYLA-353]]
- [ ] Wave 4, networks and larger formats: [[MYLA-346]] to [[MYLA-352]], [[MYLA-354]]
- [ ] The rows with no task yet (#10, #32, #39, #40, #55, #67) planned
