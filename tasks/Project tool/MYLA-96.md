---
id: MYLA-96
title: Remove and rename files and directories in std.fs
type: feature
status: review
priority: low
labels: [stdlib, runtime, selfhost]
---
Not needed for now: question 4 on [[Architecture/Project-tool]] was settled for `rm -rf` and `mv` through `std.process`. Kept for when primitives are wanted: `myla clean` removes `build/` and `.myla/`, and a Git checkout is renamed from `.partial` to its final name. The proposal is to run `rm -rf` and `mv` through `std.process` instead, as the CLI already runs `rm -f`.

If done, follow [[MYLA-88]]: primitives in all six places (both checkers, both interpreters, both backends), errors through `__io_errno`, the rest in Myla.

- [x] `__unlink(path)`, `__rmdir(path)`, `__rename(from, to)` (unlink(2), rmdir(2), rename(2))
- [x] `std.fs`: `remove_file`, `remove_dir`, `remove_dir_all` (walking with `list_dir`; symbolic links removed, not followed), `rename`
- [x] Unit tests and parity tests in all four implementations, as `tests/burn/test_fs.py` does for the directory functions
- [x] `myla clean`, the Git checkouts and `myla build`'s intermediate files use them instead of `rm` and `mv`

## How

- **Primitives:** `__unlink`, `__rmdir` and `__rename`, in all six places as [[MYLA-88]] laid out.
  - Both checkers check that they take one path (two for `__rename`), each a string, and have no result.
  - The Python interpreter calls `os.unlink`, `os.rmdir` and `os.rename`.
  - Both backends have helpers that copy each path to the stack as a C string (`emit_c_path`) and make the system call (87, 84, 82). The Python one emits them on demand; the self-hosted one emits all of its I/O helpers.
  - The self-hosted interpreter calls the primitives itself.
  - Each sets `__io_errno`.
- **std.fs:** `remove_file`, `remove_dir`, `rename`, and `remove_dir_all`. The last tries `unlink` first: a file or a symbolic link (even one to a directory) goes at once, and only EISDIR makes it list the directory, remove what is in it and then the directory itself. So it never follows a link, without needing `lstat`.
- **The CLI:** `fetch.my`'s `remove_tree` and the rename of a `.partial` checkout, `myla clean`, and `myla build`'s removal of the assembly and object file no longer run `rm` or `mv`.

## Evidence

- `tests/burn/test_fs.py::DirectoryParity::test_remove_and_rename` runs one program in the Python interpreter, the Python native backend, the self-hosted interpreter and the self-hosted native backend, each in a working directory prepared with a tree (nested directories, a link to a directory outside it, a dangling link): renames, removals, EISDIR, ENOTEMPTY, NotFound, and the tree removed while what the link names stays. All four print the same; before the change it didn't compile.
- `tests/unit/test_fs.py::TestRemovePrimitives`: the type rules and each primitive's errno.
