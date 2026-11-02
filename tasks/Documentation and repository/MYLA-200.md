---
id: MYLA-200
title: README rework
type: chore
status: review
priority: medium
labels: [docs]
---
The owner asked for a full rework of `README.md`, which still described the project of June 2026 ("very simple custom language", "focus on simplicity, not safety", a milestone table ending at v1.0, the Archive as the place for syntax), beyond the status fixes of [[MYLA-191]].

- [x] What Myla is and two examples (a tour of enums, `match`, `Result` and `?`, `#test`, f-strings; actors and child tasks), each run on both interpreters and natively on 1 and 4 workers with the output the comments show
- [x] What it values, in place of the old vision bullets (no dependencies, predictable code, the safety the checker can give cheaply, one meaning across implementations, self-hosting)
- [x] The language and the standard library in brief; getting started (the Python CLI, the bootstrap, `build/myla`, its REPL and project commands, `MYLA_THREADS`); editor support; how it is built; status and next steps; working on it (test tiers, tasks and wiki, history)
- [x] The three docstrings that pointed at README sections now gone point at the wiki pages that hold them

## Evidence

- Both code blocks extracted from the README run in the Python interpreter as shown (`total area 19`, `not a digit: x`; `3000 calls, counter at 3000`) and the tour's `#test` passes; the same programs give the same output in the self-hosted interpreter and natively on 1 and 4 workers.
- `build/myla new hello && cd hello && ../build/myla run` prints `Hello from hello!`; every path the README links exists.
