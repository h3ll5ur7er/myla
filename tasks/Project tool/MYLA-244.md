---
id: MYLA-244
title: "myla new --lib: a library project"
type: feature
status: review
priority: low
labels: [project-tool, cli]
---
`myla new --lib <name>` creates a library project: `src/<name>.my` (a public function with a `#test` case) instead of `src/main.my`, so other projects can use it as a path or Git dependency ([[Architecture/Project-tool]]). Settled question 5 of that page left it out at first; the owner asked for it (2026-11-02). Libraries stay source packages ([[MYLA-241]] has why).

- [x] The test first: a fresh `--lib` project checks and tests, and a second project using it as a path dependency builds and runs
- [x] `myla new --lib <name>` in [[selfhost/main.my]] and the project tool; `myla build` and `myla run` on it say it has no program, as for any library
- [x] [[Architecture/Project-tool]] (the command table, question 5) and [[Getting-started]]

## Built (2026-11-05)

`myla new --lib <name>` writes `myla.toml`, `.gitignore` and `src/<name>.my` (`pub fun greeting` with a `#test` case) and says `created library '<name>' in <name>/`; `myla run` on it says it has no program, as for any library. [[tests/burn/test_project_commands.py]] `test_new_lib`: the library checks and tests, and a second project with it as a path dependency runs and builds.
