---
id: MYLA-88
title: Directory functions in std.fs
type: feature
status: done
priority: medium
labels: [stdlib, runtime, selfhost]
---
The project tool ([[MYLA-64]], [[Architecture/Project-tool]]) has to find manifests and sources, create `build/` and `.myla/deps/`, and check what exists. `std.fs` could only read and write whole files.

- [x] Primitives `__list_dir`, `__mkdir` and `__stat` in the Python checker, the Python interpreter, the Python backend, and the self-hosted checker, interpreter and backend
- [x] `std.fs`: `list_dir`, `make_dir`, `make_dir_all`, `exists`, `is_dir`, `is_file`, written in Myla, with errors through `__io_errno` and `from_errno`
- [x] Unit tests (type rules, behaviour in the interpreter) and parity tests in all four implementations
- [x] [[Language/Standard-library]] documents the functions and the primitives

## How

D64's pattern: one small primitive per system call in each implementation, the rest Myla code shared by all of them.

| Primitive | System calls | Result |
| --- | --- | --- |
| `__list_dir(path) -> str` | open (`O_RDONLY\|O_DIRECTORY\|O_CLOEXEC`), getdents64 until it returns 0, close | Every name, each followed by a NUL byte, in the file system's order; `.` and `..` may be among them; `""` on an error |
| `__mkdir(path, mode)` | mkdir | Nothing |
| `__stat(path) -> int32` | stat (links followed) | `st_mode`, or -1 on an error |

Each sets `__io_errno` (0 on success). A name can't contain NUL, so NUL separates the names; the alternative, returning `[str]` from native code, would have needed a growable list in assembly. `list_dir` splits the names, drops `.` and `..` and sorts them by their bytes (a merge sort in `std.fs`), so `os.listdir` in the Python interpreter, getdents64 natively and every file system agree. `exists`, `is_dir` and `is_file` test `__stat`'s mode (`S_IFMT` bits); `make_dir_all` (like `mkdir -p`) makes each missing prefix with `make_dir`.

- Native helper: the path is copied onto the stack with a NUL (shared by the three helpers), getdents64 reads 4 KB of records at a time into a stack buffer, and the names are appended to a str cell that is reallocated at twice the needed size when full (starting at 4 KB). The self-hosted backend's copy is the same assembly.
- The Python interpreter cuts the path at its first NUL byte, as the native C string does, so the two can't disagree on such a path.
- `IoError` keeps its three variants: adding `AlreadyExists` or `NotADirectory` would break every exhaustive `match` on it, so EEXIST is `Other(17)` and ENOTDIR `Other(20)`.
- No `()` type (D35), so `make_dir` and `make_dir_all` return `Result<int32, IoError>` with `Ok(0)`.

## Evidence

- `tests/unit/test_fs.py`: 7 new tests (the type rules with their messages, `__list_dir`'s NUL-separated names and errno, `__stat` and `__mkdir`, the `FS_TOUR` program, byte order, `?` across the functions). Red before the change: 7 failures and 5 errors ("unknown function '__list_dir'").
- `tests/burn/test_fs.py`: `FS_TOUR` (empty directory, `make_dir` twice, a missing parent, `make_dir_all` with and without a trailing slash, through a file and over a file, names with non-ASCII bytes, spaces, dots and digits, a file and a missing path, the empty path, 300 long names) and a directory of 655 names of every length from 1 to 255 bytes print the same in the Python interpreter, the Python native backend, the self-hosted interpreter and the self-hosted native backend.
- The checker gate's snippet corpus has the 7 new messages; the self-hosted checker gives the same messages and positions.
- `std.fs`'s helpers have no `#test` cases on purpose: `myla test` runs the cases of every linked module, and every program that prints links `std.fs` through `std.io`, so nine extra cases would show up in every program's test run. The project tool's `myla test` should run only each file's own cases ([[Architecture/Project-tool]]).

## Follow-ups

- [[MYLA-97]]: the language server's workspace index lists files with `find`; it can use `list_dir` now.
- Removing files and directories (`myla clean`, replacing a fetched dependency) needs `unlink` and `rmdir` primitives, or `rm -r` through `std.process`: an open question on [[Architecture/Project-tool]].
