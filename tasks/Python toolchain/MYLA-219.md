---
id: MYLA-219
title: "Retire the Python toolchain"
type: chore
status: review
priority: high
labels: [bootstrap, python, tests]
---
D101 ([[MYLA-201]]): from now on the Python toolchain gets no new features; once the seed bootstrap works ([[MYLA-218]]) it is removed, interpreter included ([[MYLA-202]]). The self-hosted interpreter becomes the reference the gates compare native code with. Doing this before the language round ([[MYLA-215]]) halves the cost of every change in it.


Backup: the branch `backup/python-toolchain-final` (commit d94f948) is the last state before this work, with the whole Python toolchain ([[Development/Bootstrap]]).
- [x] The `#test` harvester of [[MYLA-184]] has run (it needs the Python interpreter)
- [x] An inventory of everything that runs `myla.py` or imports `src/myla`: the bootstrap, the burn gates (stage-by-stage comparison with the Python compiler, the parity corpus, the error corpus, the `myla test` parity gate), the unit and integration tests, CI, the extension's tests, scripts and the justfile
- [x] The gates compare the self-hosted interpreter with native code built by the self-hosted backend; the error corpus is pinned by its expected texts; what only the Python tests covered gets a burn test or is dropped on purpose (listed)
- [x] Commands only `myla.py` has (`tokenize`, `parse`, …) exist in `build/myla` where a test or a user needs them
- [x] The standard library moves out of `src/myla/std/`, and the gdb pretty-printer out of `src/myla/debug/` (both compilers embed it, D82)
- [x] `src/myla/`, `myla.py` and their tests removed; [[Architecture]], [[Development/Testing]], [[Development/Bootstrap]], [[Getting-started]], the README, `AGENTS.md` and the `myla` skill updated

## Evidence

- **Commits.**
  - b6a47d6: the burn tests answer from the Python toolchain's recorded answers.
  - 95c74d1: the removal of `src/myla/`, `myla.py`, `tests/unit`, `tests/integration` and the Python-only scripts.
  - 118acf2 and 4e2b0db: no checkout path in generated cases or recorded keys.
  - 354875c: `lib/std`, `lib/debug`.
  - 850e6ae: the documentation.
  - In the batch after it, the test fixes that recordings made necessary (below).
- **Harvester.** It ran to 80 % coverage before the removal (bd06542, [[MYLA-184]]); `scripts/test_coverage.py` now counts without the Python parser.
- **Inventory and what replaced each part.**
  - The bootstrap starts from `bootstrap/seed.s` ([[MYLA-218]]), not from the Python compiler.
  - CI runs the burn, bootstrap and vscode-extension jobs; the unit job is gone.
  - The extension finds the repository by `selfhost/main.my` and has no `python3 myla.py` fallback.
  - `scripts/bootstrap.sh` and `update-seed.sh` lost `--from-python`; `gen_unicode_tables.py` writes only `selfhost/unicode.my`.
  - The burn gates compile with the self-hosted compiler ([[MYLA-235]]).
  - Where a gate asked the Python toolchain (interpreter output, checker verdicts, diagnostics, lexer tokens), its answers are recorded: 27 files, `tests/burn/data/golden/`, keyed by arguments and file contents (`tests/burn/_golden.py`). A file that changes with the compiler (`selfhost/`, `tools/`, `lib/std/`) and has no answer skips; any other missing answer fails.
- **What only the Python tests covered.**
  - 97 single-module programs from the unit tests, with their output and exit status, run in the self-hosted interpreter and natively (`test_unit_programs.py`).
  - The type-error snippets were regenerated before the removal (141 → 204).
  - The rest of the unit tests tested the Python modules themselves and went with them, deliberately.
- **Commands.** No test or user needs `tokenize`, `parse` or `--keep-asm` in `build/myla`. The gates' drivers (`lex_main`, `parse_main`, `gen_main --emit-ir`) do that job, as [[Development/Debugging]] says.
- **Verification.** The burn suite passed without the Python toolchain (834 tests then, 841 now), also cold, in a checkout at another path (what CI sees).
- **Recordings go stale as the compiler changes; two tests that leaned on them were fixed.**
  - `test_lsp`'s resolution corpus now tokenizes with the self-hosted lexer: changed files had been skipped until it fell under its floor ([[MYLA-171]]'s commit).
  - The error corpus holds a file without a recording to the self-hosted CLI's diagnostics. Before this, any new or changed corpus file failed. On the 214 recorded files the self-hosted diagnostics equal the recorded ones (a test compares them); a new file gets the CLI's answer (a test writes one).
  - The skips that remain (about 20) are recorded answers about `selfhost/` files changed since; they shrink the oracle, not the suite's own checks.

