---
id: MYLA-943
title: "myla test on Windows: a drive's path taken for a relative one, exit(-1) reported as a signal, std/platform.my named Windows'"
type: bug
status: done
priority: high
labels: [test, windows]
---
Found by [[MYLA-926]] step 2's port of the burn suites (2026-11-24, group E), in the native Windows run 277 of test_test_native (nine of its ten failures):

1. **A drive's path taken for a relative one.** `selfhost/driver.my`'s `absolute` took only a path starting with `/` for absolute, so a standard library root given as `D:\a\myla\myla\lib` (`--stdlib`, MYLA_STDLIB) became `D:/a/myla/myla/D:/a/myla/myla/lib`. `own_library` makes the root absolute when the file is written relative to it another way, so `myla test lib\std\yaml.my --stdlib D:\…\lib` loaded a second copy of std.json (a type error, no report), `myla test lib\std\rt.my --native` and `lib\std\platform.my --target wasm32-wasi` weren't recognised as std.rt and std.platform (raw memory's type errors instead of their refusals), and `myla test D:\…\lib\std\platform_wasm.my --stdlib lib --target wasm32-wasi` said `cannot read module 'D:/a/myla/myla/D:/a/myla/myla/lib/std/platform_wasm.my'`. `absolute` and `written_under` now ask the loader's `is_absolute` (a drive and a share are roots on Windows, [[MYLA-931]]).
2. **`exit(-1)` reported as a signal.** On Windows a status has its 32 bits (D224), so a case's `exit(-1)` ended its process with 0xFFFFFFFF, `Exited(-1)`; std.test's runner and the driver's wasm32 runs turn a status into one number, minus the signal for a signal, and reported `FAIL  leaves #3: killed by signal 1` where `#test(-1)[exit(255)]` passes on Linux. `std.test.run_code` now takes an exit status modulo 256, as D216 has tests compare it (on Linux a status is 0 to 255 already); the runner, the native harness's run and the wasm32 runs use it.
3. **std/platform.my named Windows'.** `myla test lib/std/platform.my --native` on Windows is refused, rightly (S3: for x86_64-windows std.platform is `platform_windows.my`), but the refusal said `… is std.platform for x86_64-windows; for x86_64-windows it is …/std/platform_windows.my`: it named the host as the one whose module the file is. It now names x86_64-linux on a host with a platform module of its own (`plain_platform_target`); on Linux the host, as before.

The tenth failure, TestWasm32's scratch directories, is [[MYLA-944]].

- [x] `absolute`, `written_under` through `is_absolute`; `run_code` in std.test with its cases; the refusal's target
- [x] test_test_native's Windows expectations: the refusal names x86_64-linux there, and the corpus's `lib/std/platform.my` is refused natively on Windows (its interpreted cases still run)
- [x] Evidence on Linux: `myla test lib/std/test.my --only run_code` 4/4, driver.my's `absolute`, `written_under`, `hosts_platform` cases pass, the bootstrap's fixed point, test_test_native as before. On Windows itself: the next `burn-windows` run
