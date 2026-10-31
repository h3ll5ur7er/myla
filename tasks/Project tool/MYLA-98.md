---
id: MYLA-98
title: std.fs.current_dir and the __getcwd primitive
type: feature
status: done
priority: medium
labels: [stdlib, runtime, selfhost]
---
The project tool finds `myla.toml` from the working directory upwards and compares package directories ([[MYLA-93]], [[Architecture/Project-tool]]); both need the working directory, which Myla couldn't read. The self-hosted backend's DWARF compile unit wrote `.` for the same reason ([[MYLA-66]]).

- [x] Primitive `__getcwd() -> str` in the Python checker, the Python interpreter, the Python backend, and the self-hosted checker, interpreter and backend; it sets `__io_errno`
- [x] `std.fs.current_dir() -> Result<str, IoError>`, written in Myla
- [x] Unit tests (type rule, behaviour in the interpreter, a removed directory) and parity tests in all four implementations
- [x] The self-hosted compile unit records the working directory as the Python backend does
- [x] [[Language/Standard-library]] documents the function and the primitive; [[Development/Debugging]] no longer says the self-hosted compiler writes `.`

## How

As [[MYLA-88]] added its primitives (D64's pattern): one system call per implementation, the rest Myla.

| Implementation | `__getcwd` |
| --- | --- |
| Python interpreter | `os.getcwdb()`, the errno on `OSError` |
| Both native backends | getcwd(79) into a 4 KB stack buffer, then a fresh `str` cell of the length it returns less the NUL; on an error `""` and the errno (ENOENT when the directory was removed, ERANGE when its path is longer than 4 KB) |
| Both checkers | No arguments (`__getcwd() takes no arguments`), result `str` |

`current_dir` returns `Ok(dir)` when `__io_errno()` is 0 and `Err(from_errno(err))` otherwise, so a removed working directory is `NotFound`. The kernel's getcwd gives the absolute path without symbolic links, which is what `os.getcwd()` gives too.

The self-hosted backend emits its runtime helpers unconditionally, so the bootstrap's stage 2 assembly grows from 8,471,478 to 8,487,923 bytes (the helper, `current_dir`, and the compile unit's call).

## Evidence

- `tests/unit/test_fs.py`, class `TestCurrentDir`: 4 tests (the type rule and its message, `__getcwd` and `__io_errno` in a temporary working directory, `current_dir`, a removed working directory giving `not found`). Before the change: 4 errors, "unknown function '__getcwd'".
- `tests/burn/test_fs.py`, `DirectoryParity.test_current_dir` and `test_current_dir_removed`: the Python interpreter, the Python native backend, the self-hosted interpreter and the self-hosted native backend print the same working directory, and `not found` when started in a removed directory (`sh -c 'mkdir gone && cd gone && rmdir ../gone && exec …'`).
- `tests/burn/test_debug_info.py`, `test_the_compile_unit_names_the_working_directory`: readelf shows the working directory as `DW_AT_comp_dir` of a self-hosted `-g` build.
- The checker gate's snippet corpus (`tests/burn/data/type_error_snippets.json`) has the new message.
- `scripts/bootstrap.sh`: byte-identical fixed point.
