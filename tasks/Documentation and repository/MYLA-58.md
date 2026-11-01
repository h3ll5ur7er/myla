---
id: MYLA-58
title: "Test tooling: pytest vs unittest, and a slow burn suite"
type: chore
status: done
priority: low
labels: [tests]
---
- [x] `pyproject.toml` says the suite is unittest-only, but `uv run pytest` is what people (and agents) run; it works only through a globally installed pytest. Either add pytest as a dev dependency or document `python3 -m unittest discover -s tests -t .` as the way ([[Development/Testing]])
- [x] The burn suite takes about 135 s (native builds of every example and of the self-hosted tools); split a fast tier from the slow one
- [x] Runtime errors in the error corpus are only checked in the interpreter; module errors (`module error`) have no corpus stage

## How

- pytest is in the `dev` dependency group of `pyproject.toml` (`uv run pytest` installs it); the tests stay plain `unittest`, so `python3 -m unittest` still needs nothing else.
- Most of the burn time went into building the same self-hosted tools (`gen_main`, `interp_main`, the gate drivers) once per test module. `tests/burn/_tools.py` builds each tool once into `build/test-tools/<name>-<hash>`, keyed by a hash of every source that can change it, and all burn modules use it.
- `scripts/test.sh [fast|all]`: `fast` leaves out the self-hosting gates (`tests/burn/test_selfhost_*`).
- The error corpus has a `module` stage (driven by the loader with the bundled stdlib; two new files) and a `//~ native: <text>` directive on every runtime file: the case is also built with the Python backend, which must exit 1 and print the text on stderr.

## Evidence

- Burn suite: 78 s before (the 135 s in the task predates other speedups), 53 s with an empty tool cache, 35 s with a warm one.
- `scripts/test.sh fast`: about 20 s.
- `uv run pytest tests/unit -q`: 466 passed.
- The corpus test fails when a native directive is wrong (`'runtime error: WRONG' not found in 'runtime error: pop from an empty list\n'`) and passes with the real text; the 134 corpus tests pass.
- Full run after the change: unit 466, integration 4, burn 384 (36 s, warm cache), all OK.

## Since

The burn suite grew back to about 4 minutes in CI (811 tests); a new tiering pass and honest timings are [[MYLA-153]].
