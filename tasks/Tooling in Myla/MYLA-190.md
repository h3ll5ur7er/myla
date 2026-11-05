---
id: MYLA-190
title: std.io writes report errors; unit results; std.process.run with PATH, cwd, env and stdin
type: improvement
status: backlog
priority: low
labels: [stdlib]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). Three API gaps in the standard library:

- `write`, `println` and `eprintln` ([[lib/std/io.my]]) return nothing, so `EPIPE` on a closed pipe is invisible, while every read returns `Result<_, IoError>`;
- `write_to_file`, `make_dir`, `remove_*` and `rename` return `Result<int32, IoError>` with an `int32` that is always 0: a unit result wants a decision (D35 left the unit type out);
- `std.process.run` has no PATH search, working directory, environment or stdin for the child; the project tool works around PATH with `/usr/bin/env git`. `Command` is an immutable builder (`arg` returns a new one), which the page doesn't say.

- [ ] Each decided and done, with the parity tests of `test_stdio.py`, `test_fs.py` and `test_process.py` extended

Decided by D113 ([[MYLA-211]]): I/O and process functions return `Result<T, IoError>` with an enum of causes; file handles have an explicit `close` and a scoped helper; `defer` follows [[MYLA-229]].

## From the new targets (2026-11-04, [[Project/Reflection-2026-11]])

- `IoError.Other` carries Linux's errno numbers, which programs can print; wasm maps WASI's errnos onto them (anything unmapped becomes EIO), macOS's differ (EAGAIN 35, ENOSYS 78). D113's enum of causes should be the whole interface, with a cause for "unsupported on this target": wasm's `run` and `spawn` give `Other(38)` today. [[MYLA-266]] asks for that decision; [[MYLA-265]] gives the platform layer causes instead of errnos.
- PATH search on Windows also means `PATHEXT` ([[MYLA-165]]).
