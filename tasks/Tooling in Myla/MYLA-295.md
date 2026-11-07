---
id: MYLA-295
title: "Standard-library polish: task.cancel's signature, Command.env's name, tests for io, time, task and toml"
type: chore
status: review
priority: low
labels: [stdlib]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]).

- `task.cancel(child: int)` ([[lib/std/task.my]]) is still the fake signature the October review flagged: the compiler intercepts the call, and hover shows `int`
- `Command.env("A=B", "c")` yields `A=B=c`: the name isn't validated ([[lib/std/process.my]])
- `#test` coverage is zero in `io.my`, `task.my`, `time.my` and the 646-line `toml.my`; `rt.my` has 8 cases for 136 functions (`digit_count`, `str_hash`, `timer_sift`, `map_lookup` are pure); `ownership.my` has none
- `from_errno` maps `EPERM` to `PermissionDenied`, undocumented
- the `std.rt` paragraph of [[Language/Standard-library]] is one 400-word sentence; a table, or Architecture

- [x] Each item

## Evidence

- `task.cancel<T>(child: T)` ([[lib/std/task.my]]): the child's binding has its task's result type, so the signature says what the compiler takes (hover shows `cancel<T>(child: T)`); the call is still taken by the compiler and the body never runs.
- `Command.env` and `env_remove` ([[lib/std/process.my]]): a name no variable can have (empty, with `=` or a NUL byte) makes `output` and `output_async` give `Err(SpawnError.InvalidInput)` (D160, the owner's decision; EINVAL from the system maps to it too) and run nothing; a value may hold `=`. `test_an_environment_name_no_variable_can_have` in `tests/burn/test_process.py`, interpreter and native. The one exhaustive match on `SpawnError`, `examples/subprocess/main.my`'s, names it.
- `#test` cases: `toml.my` 14 (`line_col`, `path_key`, `with_key`, `dotted`, `hex4`, `is_bare_key`), `rt.my` 8 more (`digit_count`, `errno_text`, `has_word`), all passing under `myla test`. `io.my`, `time.my` and `task.my` are I/O and the executor, which their burn tests cover (`test_stdio`, `test_time`, `test_task_yield`); `str_hash`, `timer_sift` and `map_lookup` read raw memory, which a `#test` in the interpreter can't give them.
- `fs.my`'s header no longer names Python; the "v0.5.4" headers had gone with the review's patches.
- [[Language/Standard-library]]: `PermissionDenied` is EACCES and EPERM both; `SpawnError.InvalidInput` for a bad name; the `std.rt` paragraph is a table by what each part is behind, then the primitives and the platform layer as before.
