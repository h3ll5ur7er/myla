---
id: MYLA-35
title: justfile recipes drop arguments and leave files behind
type: bug
status: review
priority: low
labels: [scripts, selfhost]
---
- [x] `just run source *args` never passes `{{args}}` to the program
- [x] `build/myla build` leaves `<out>.s` and `<out>.o` next to the binary
- [x] `build/myla` defaults the stdlib root to the relative `src/myla`, so it only works from the repository root (see [[MYLA-31]])
- [x] `just bootstrap` duplicates `scripts/bootstrap.sh` (and adds the stage-4 CLI build and timers); keep one of them as the source of truth

## How

- The self-hosted CLI takes `--stdlib <dir>` as an option, so `myla run <file> [args…]` passes the remaining arguments to the program (argv = the file, then them), as the Python `myla run` does; `just run source *args` passes `{{args}}` ([[selfhost/main.my]], [[justfile]]). `build` rejects unknown options.
- `myla build` removes `<out>.s` and `<out>.o` after linking (through `rm -f`, as there is no unlink primitive in the standard library yet).
- The stdlib default works from any directory: [[MYLA-31]].
- `scripts/bootstrap.sh` is the source of truth: it now also builds `build/myla` after the fixed point, and `just bootstrap` just runs it (the timers of the old recipe are gone; `timer.py` stays in the repository but nothing uses it now).

## Evidence

[[tests/burn/test_selfhost_cli.py]]: `run prog.my a "b c"` prints `3 prog.my a b c 42`; `build` leaves only the binary in its output directory; `test` passes. Before, every case failed outside the repository root, and arguments after the file were taken as the stdlib root.
