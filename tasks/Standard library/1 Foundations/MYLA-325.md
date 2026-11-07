---
id: MYLA-325
title: The standard library docs one page per module; every module's cases run by one test
type: chore
status: todo
priority: high
labels: [docs, stdlib, tests, wave-1]
---
Wave 1 of [[Project/Standard-library-roadmap]]. Two shared files would make every parallel lane clash, so this task changes them first. It is done by the integrator before the wave's lanes start.

- [[Language/Standard-library]] holds every module's section today. It becomes an index table (module, what it holds, its page), with one page per module below it.
- `test_json.py`'s `StdTests` runs the cases of `std.num` and `std.json` from a list. It becomes a test that runs `myla test` on every `lib/std/*.my` that has cases (the runtime and platform modules excluded), in the interpreter and with `--native`. A new module is then covered without editing a list.

- **Owns:** `docs/Language/Standard-library.md`, `docs/Language/Standard-library/`, `tests/burn/test_json.py` (its `StdTests`)
- **Needs:** nothing; it can start as soon as its wave does

- [ ] The page split, each existing module's section moved unchanged, links to the old anchors updated
- [ ] The module test finds every module with cases, interpreted and native
- [ ] Both checked: `test_doc_blocks` and the new test pass
