---
id: MYLA-722
title: "Windows: random bytes over bcrypt"
type: feature
status: todo
priority: medium
labels: [platforms, windows]
---
A part of [[MYLA-165]], the Windows target, found by [[MYLA-704]]: Windows' `random_fill` in [[lib/std/platform_windows.my]] is still `UNSUPPORTED`. D212 names `bcrypt` for it (`BCryptGenRandom` with `BCRYPT_USE_SYSTEM_PREFERRED_RNG`), a second import library beside kernel32's, which the driver doesn't make yet (`def_text` writes `LIBRARY kernel32.dll` only; wave 4 brings `ws2_32` too, [[MYLA-706]]).

Until then a Windows program has no `__random_bytes`, so `std.random`'s seeding from the system, `std.uuid`, and the names of `std.fs`'s temporary files and directories (`make_temp_dir`, `make_temp_file`, and with them `std.test`'s `temp_dir()` and `temp_file()`) are `Unsupported` there. `tests/burn/_targets.py` excuses `test_platform_primitives.Entropy` and std's `random`, `uuid`, `fs` and `test` modules for it (`_WIN_RANDOM`); `test_windows.py`'s `test_what_isnt_there_yet_says_so` checks it.

- [ ] An import library per DLL the program calls (the code generator's `windows_imports` names each function's DLL), linked together
- [ ] `random_fill` over `BCryptGenRandom`; the excuses above lifted, std.fs's and std.test's cases run under Wine
