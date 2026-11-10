---
id: MYLA-431
title: "P17 Seed size"
type: improvement
status: todo
priority: high
labels: [bootstrap, seed, repository, round-5]
---
Work package P17 of [[Project/Review-2026-11-09]], moved before wave A (the owner's choice, 2026-11-10): every round adds two seeds. Over half of each seed is the embedded standard library as `.byte` lists (10.5 of 19.4 MB); the seeds doubled in two days and each update adds about 3.4 MB to the pack.

- [ ] Measure what the bootstrap reads of the seed's embedded library
- [ ] Build the seed without the embedded library if the bootstrap never reads it, else emit strings as `.ascii`
- [ ] Its own pull request: both seeds rewritten, the bootstrap's fixed point and `scripts/check-seed.sh` unchanged in meaning
