---
id: MYLA-244
title: "myla new --lib: a library project"
type: feature
status: todo
priority: low
labels: [project-tool, cli]
---
`myla new --lib <name>` creates a library project: `src/<name>.my` (a public function with a `#test` case) instead of `src/main.my`, so other projects can use it as a path or Git dependency ([[Architecture/Project-tool]]). Settled question 5 of that page left it out at first; the owner asked for it (2026-11-02). Libraries stay source packages ([[MYLA-241]] has why).

- [ ] The test first: a fresh `--lib` project checks and tests, and a second project using it as a path dependency builds and runs
- [ ] `myla new --lib <name>` in [[selfhost/main.my]] and the project tool; `myla build` and `myla run` on it say it has no program, as for any library
- [ ] [[Architecture/Project-tool]] (the command table, question 5) and [[Getting-started]]
