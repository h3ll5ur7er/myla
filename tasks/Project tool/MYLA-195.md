---
id: MYLA-195
title: myla.lock stores URLs as written; myla new --lib
type: improvement
status: backlog
priority: low
labels: [project-tool]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). Two small gaps found while driving the project tool end to end (everything documented worked):

- `myla.lock` stores a path dependency's URL as written (`…/app/../geo`), so two spellings of one directory look like two dependencies and the lock reads "not current"; normalising as D77 (1) does for package directories would avoid it
- there is no `myla new --lib`, so making a dependency means deleting `src/main.my` by hand (D73 chose not to, and may stay so)

- [ ] Normalise the recorded URL of a path dependency
- [ ] `--lib`, or the page saying how to make a library
