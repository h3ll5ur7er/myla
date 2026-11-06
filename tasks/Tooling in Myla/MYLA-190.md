---
id: MYLA-190
title: std.io writes report errors; unit results; std.process.run with PATH, cwd, env and stdin
type: improvement
status: review
priority: low
labels: [stdlib]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). Three API gaps in the standard library:

- `write`, `println` and `eprintln` ([[lib/std/io.my]]) return nothing, so `EPIPE` on a closed pipe is invisible, while every read returns `Result<_, IoError>`;
- `write_to_file`, `make_dir`, `remove_*` and `rename` return `Result<int32, IoError>` with an `int32` that is always 0: a unit result wants a decision (D35 left the unit type out);
- `std.process.run` has no PATH search, working directory, environment or stdin for the child; the project tool works around PATH with `/usr/bin/env git`. `Command` is an immutable builder (`arg` returns a new one), which the page doesn't say.

- [x] Each decided and done, with the parity tests of `test_stdio.py`, `test_fs.py` and `test_process.py` extended

Decided by D113 ([[MYLA-211]]): I/O and process functions return `Result<T, IoError>` with an enum of causes; file handles have an explicit `close` and a scoped helper; `defer` follows [[MYLA-229]].

## From the new targets (2026-11-04, [[Project/Reflection-2026-11]])

- `IoError.Other` carries Linux's errno numbers, which programs can print; wasm maps WASI's errnos onto them (anything unmapped becomes EIO), macOS's differ (EAGAIN 35, ENOSYS 78). D113's enum of causes should be the whole interface, with a cause for "unsupported on this target": wasm's `run` and `spawn` give `Other(38)` today. [[MYLA-266]] asks for that decision; [[MYLA-265]] gives the platform layer causes instead of errnos.
- PATH search on Windows also means `PATHEXT` ([[MYLA-165]]).

## Decided (2026-11-05)

- **D129:** `IoError` and `SpawnError` name portable causes (`NotFound`, `PermissionDenied`, `AlreadyExists`, `IsADirectory`, `NotADirectory`, `NotEmpty`, `Interrupted`, `Unsupported`, …), plus `Other(code)` for the rest. wasm32's `run` gives `Unsupported`.
- **D138:** the always-0 `int32` results become `Result<(), IoError>` ([[MYLA-278]]).

- [x] The causes in `std.fs` and `std.process` from each platform module's codes ([[MYLA-265]]); the error tests on every target
  - **The causes:** `IoError` gains `AlreadyExists`, `NotADirectory`, `IsADirectory`, `NotEmpty`, `Interrupted`, `Cancelled` (a cancelled read; `Other(125)` before) and `Unsupported`. `SpawnError` gains `Unsupported` and `Cancelled`.
  - **The mapping:** `from_errno` and `spawn_error_from_errno` map the platform layer's codes, which are Linux's numbers on every target so far, wasm32's included. `#test` cases cover it.
  - **Tests:**
    - `test_fs.IoErrorCauses`, written first and failing, makes each common cause happen in the interpreter and natively;
    - `test_wasm.WasmCapabilities`: `run` on wasm32 is `Unsupported`;
    - the tests whose programs print causes now (`test_fs`, `test_process`, the `readfile` and `subprocess` examples) carry their own expectations, through `run_file_both_now` and `run_source_both_now` in `_native.py`, as no recorded answer covers them.

## Decided (2026-11-06)

- **D146:** `write(fd, s)` returns `Result<(), IoError>`; `print`, `println`, `eprint` and `eprintln` return nothing, and a broken pipe on them ends the program quietly on every target.
- **D147:** `PATH` search for a program name without a `/`; `Command` gains `cwd`, `env`, `env_remove`, `env_clear` and `stdin(text)`; `run` stays the shortcut; all of it `Unsupported` on wasm32.

- [x] D146 done, with `test_stdio` extended (a broken pipe, a write's error)
- [x] D147 done, with `test_process` extended (PATH, a directory, the environment, stdin), `Command`'s immutability documented

## Done (2026-11-06)

- **D146** (39a4b5f):
  - The runtime ignores SIGPIPE (`rt_sigaction` at `_start`, x86-64 and aarch64), so a write to a pipe nobody reads any more gives EPIPE.
  - std.rt's `write` and `print_str` take the error the platform's `write_all` and `write_line` now return. On the standard output or error it ends the program quietly: `broken_pipe` restores SIGPIPE's default and raises it natively, and exits with 141 on wasm32. On another descriptor it is the errno `__io_errno` reads.
  - `std.io.write` returns `Result<(), IoError>`. `IoError` gains `BrokenPipe`, which breaks an exhaustive `match` on `IoError`, as `test_fs`'s list of causes showed.
  - A child gets SIGPIPE's default back before its exec.
- **D147**, in two steps, as a primitive must be in a seed before the standard library the compiler uses can call it:
  - **39a4b5f**: `__run_with(program, argv, opts)` and `__spawn_with`.
    - PATH: `std.rt.program_paths` gives the candidates, and the child tries each, going on after ENOENT or ENOTDIR and keeping EACCES, as `execvp` does.
    - A directory: `chdir` in the child.
    - stdin: an anonymous file holding the text (`memfd_create`), so a large input can't deadlock against the child's output, and `spawn` gets it the same way.
    - The environment: kept, changed or cleared (`NAME=value` sets, a bare `NAME` removes).
  - **Then**: `std.process` uses them. `run` and `run_async` look on PATH. `Command` gains `cwd`, `env`, `env_remove`, `env_clear` and `stdin`, each giving a new `Command` (documented). The interpreter passes them to the host's primitives.
- **Found on the way**: a program without tasks (no `import std.task`) that called `run_async`, `output_async` or std.io's async reads failed to build natively ("a call through a value of that type"). `await __wait_either(...)` and `await __wait_readable(...)` reached the ordinary call path, where only the frame path knew them. Without tasks they now do nothing but evaluate their arguments, as `await_let`'s comment already said (`waits_without_tasks`).
- **Tests**:
  - `test_stdio.BrokenPipe`: printing into a closed pipe ends quietly; a write to fd 3 whose reader closed gives `BrokenPipe` (SIGPIPE killed the program before). The fd 3 test is excused on wasm32.
  - `test_process`:
    - `test_a_child_gets_sigpipe_back`;
    - `test_a_child_s_path_directory_environment_and_input`: PATH, a directory and one that isn't there, the environment changed, removed from and cleared, stdin, a program found nowhere, a base `Command` unchanged by what was built from it;
    - `test_a_child_waited_for_in_a_task`: with and without tasks; the second failed to build before.
- **Left**: the project tool still runs `/usr/bin/env git`, which it can now write `run("git", …)`.
