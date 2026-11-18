---
id: MYLA-770
title: "SpawnError.Other's message says errno for Windows' own codes"
type: bug
status: review
priority: low
labels: [platforms, windows, stdlib]
---
Found by [[MYLA-716]]. Since MYLA-716 an `Other` on Windows holds Windows' own code (`SpawnError.Other(193)` for a text file run as a program, `ERROR_BAD_EXE_FORMAT`), but `SpawnError.message()` ([[lib/std/process.my]]) still says `could not start the program: errno 193`, as on Linux, where the number is an errno. An `Other` can also hold one of std's own numbers (Linux's errno of a cause the type has no variant for, `code_number`: `Other(11)` would-block), so the message can't tell which it is from the number alone.

To reproduce: `tests/burn/test_windows.py`'s `ERRORS` program with `print(f"{e}")` for the spawn of `.\text.exe` prints `could not start the program: errno 193` under Wine.

`TermError` (`terminal error N`) and `SignalError` (`signal error N`) name no system and are fine; `IoError.message()` says `error N`.

- [x] `SpawnError.Other`'s message names the number neutrally (`error 193`, as `IoError`'s), or by the target's words (std.system_error's `error_text` for a system's code); the `#test` cases of `SpawnError.message` (std.process's, the Tests lane's in Windows wave 6) and any pin updated

## What changed

[[lib/std/process.my]]'s `SpawnError.message()` says `could not start the program: error N` for an `Other(N)`, as `IoError`'s `error N`: the number is std's own (a cause without a variant, `code_number`) or the system's, an errno on Linux and Windows' code there, so it names neither (done in [[MYLA-798]]'s lane, round 7). A `#test` for `Other(193)`; `test_windows.ERRORS` prints the message of the spawn of a text file.

## Proposals

1. **Neutral `error N`** (built). Alternatives: std.system_error's `error_text(N)` (`Windows error 193`, `errno 12`), which says the system's words but is wrong for std's own numbers on Windows (`Other(24)` is std's TOO_MANY_OPEN there, D252, and Windows' 24 is ERROR_BAD_LENGTH); or a separate variant for the system's codes, which breaks every exhaustive `match`.

## Evidence

- **Test first.** The new `#test(SpawnError.Other(193))["could not start the program: error 193"]` and the changed one for `Other(12)` fail against BASE's `message` (`errno 193`, `errno 12`); `test_windows.Errors` with its new line failed at BASE (`not a program: Other(193): could not start the program: errno 193`).
- **After.** std.process's cases 53/53 interpreted; `test_windows.Errors` under Wine 9.0 passes. No other pin named the old text (`grep -rn "could not start the program"` in tests, docs and examples).
