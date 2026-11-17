---
id: MYLA-770
title: "SpawnError.Other's message says errno for Windows' own codes"
type: bug
status: todo
priority: low
labels: [platforms, windows, stdlib]
---
Found by [[MYLA-716]]. Since MYLA-716 an `Other` on Windows holds Windows' own code (`SpawnError.Other(193)` for a text file run as a program, `ERROR_BAD_EXE_FORMAT`), but `SpawnError.message()` ([[lib/std/process.my]]) still says `could not start the program: errno 193`, as on Linux, where the number is an errno. An `Other` can also hold one of std's own numbers (Linux's errno of a cause the type has no variant for, `code_number`: `Other(11)` would-block), so the message can't tell which it is from the number alone.

To reproduce: `tests/burn/test_windows.py`'s `ERRORS` program with `print(f"{e}")` for the spawn of `.\text.exe` prints `could not start the program: errno 193` under Wine.

`TermError` (`terminal error N`) and `SignalError` (`signal error N`) name no system and are fine; `IoError.message()` says `error N`.

- [ ] `SpawnError.Other`'s message names the number neutrally (`error 193`, as `IoError`'s), or by the target's words (std.system_error's `error_text` for a system's code); the `#test` cases of `SpawnError.message` (std.process's, the Tests lane's in Windows wave 6) and any pin updated
