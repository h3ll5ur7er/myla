---
id: MYLA-96
title: Remove and rename files and directories in std.fs
type: feature
status: backlog
priority: low
labels: [stdlib, runtime, selfhost]
---
Not needed for now: question 4 on [[Architecture/Project-tool]] was settled for `rm -rf` and `mv` through `std.process`. Kept for when primitives are wanted: `myla clean` removes `build/` and `.myla/`, and a Git checkout is renamed from `.partial` to its final name. The proposal is to run `rm -rf` and `mv` through `std.process` instead, as the CLI already runs `rm -f`.

If done, follow [[MYLA-88]]: primitives in all six places (both checkers, both interpreters, both backends), errors through `__io_errno`, the rest in Myla.

- [ ] `__unlink(path)`, `__rmdir(path)`, `__rename(from, to)` (unlink(2), rmdir(2), rename(2))
- [ ] `std.fs`: `remove_file`, `remove_dir`, `remove_dir_all` (walking with `list_dir`; symbolic links removed, not followed), `rename`
- [ ] Unit tests and parity tests in all four implementations, as `tests/burn/test_fs.py` does for the directory functions
