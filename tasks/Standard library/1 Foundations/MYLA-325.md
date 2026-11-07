---
id: MYLA-325
title: The standard library docs one page per module; every module's cases run by one test
type: chore
status: review
priority: high
labels: [docs, stdlib, tests, wave-1]
---
Wave 1 of [[Project/Standard-library-roadmap]]. Two shared files would make every parallel lane clash, so this task changes them first. It is done by the integrator before the wave's lanes start.

- [[Language/Standard-library]] holds every module's section today. It becomes an index table (module, what it holds, its page), with one page per module below it.
- `test_json.py`'s `StdTests` runs the cases of `std.num` and `std.json` from a list. It becomes a test that runs `myla test` on every `lib/std/*.my` that has cases (the runtime and platform modules excluded), in the interpreter and with `--native`. A new module is then covered without editing a list.

- **Owns:** `docs/Language/Standard-library.md`, `docs/Language/Standard-library/`, `tests/burn/test_json.py` (its `StdTests`)
- **Needs:** nothing; it can start as soon as its wave does

- [x] The page split, each existing module's section moved unchanged, links to the old anchors updated
- [x] The module test finds every module with cases, interpreted and native
- [x] Both checked: `test_doc_blocks` and the new test pass

## Done (2026-11-07)

- [[Language/Standard-library]] keeps the built-in functions, the conventions (D164) and an index table. The 13 module sections moved unchanged to `docs/Language/Standard-library/<Module>.md`, each heading one level up, and Io, Fs and Process got a one-line intro. The one link to an old anchor (`#stdtest`, in [[Language/Attributes-and-testing]]) points at the new page.
- `tests/burn/test_std_modules.py` replaces `test_json.py`'s `StdTests`. It finds every `lib/std/*.my` with `#test` cases and runs `myla test` on each, interpreted and with `--native`. `std.rt` runs interpreted only, and the aarch64 and wasm32 platform modules aren't run. It finds 12 modules (fmt, fs, io, json, math, num, platform, process, rt, slice, test, toml), and all pass in 1.9 s. A broken case in `std.slice` failed it, interpreted and natively, with the case's report.
- `test_doc_blocks` passes.
