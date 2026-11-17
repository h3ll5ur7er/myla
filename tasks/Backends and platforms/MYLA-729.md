---
id: MYLA-729
title: "myla.exe's scratch directories on Windows: TEMP, not /tmp"
type: bug
status: done
priority: low
labels: [platforms, windows, testing]
---
Found by [[MYLA-728]], which moved a Windows test harness's case directories under `%TEMP%` (std.fs's `temp_root`). The toolchain's own scratch directories still take `TMPDIR`, else `/tmp`, joined with `/`: `myla test --native`'s harness build in [[selfhost/driver.my]] (`format("{}/myla-test-{}", base, now_ns())`), a project's in [[selfhost/project_cmd.my]], and the interpreter's case root in [[selfhost/interp.my]] (`__getenv("TMPDIR")`, `/tmp`). On Linux nothing changes; `myla.exe` running on Windows itself ([[MYLA-708]]'s runner) would make `\tmp\myla-test-…` on the current drive instead of a directory under `%TEMP%`.

- [x] The three take std.fs's `temp_root()` (the interpreter its own equivalent) and join with the target's separator, as std.test's `run_in_children` does since [[MYLA-728]]
- [x] Checked by `myla.exe test` on the Windows runner, outside Wine's `Z:` — built and run under Wine here (whose `%TEMP%` is on `C:`, not `Z:`); the native harness's step needs the runner's LLVM, so it runs on the pull request's `windows` job (below)

## What changed

The driver's `scratch_dir()` ([[selfhost/driver.my]]) is `myla-test-<ns>` under std.fs's `temp_root()` (`$TMPDIR` or `/tmp`; on Windows `%TMPDIR%`, `%TEMP%`, `%TMP%`, else `.`, D227), joined with `scratch_sep()`, the separator of the machine the tools run on (`\` on Windows, D229, std.path_style's `WINDOWS` of the tools' own library). `native_tests` builds its harness there (`…\myla-test-<ns>\harness.exe` on Windows) and a project's test program built natively ([[selfhost/project_cmd.my]], `run_test_program_natively`) its program. The interpreter's case root ([[selfhost/interp.my]], `__test_dir`'s first call) is `temp_root()` and `myla-test-<ns>` joined the same way. On Linux the paths are as before but for a `$TMPDIR` ending in `/`, whose trailing separators `temp_root` drops. The names stay `myla-test-<ns>` (as std.test's case roots); `make_temp_dir_in`'s random names would be safer against two runs in one nanosecond, but would change what `test_test_native` globs for. The wasm32 runs of a harness (`resumed_tests`) keep `/` for their `run<k>`: the path is a WASI program's, under Linux's rules.

**Tests.** `HostModules` ([[tests/burn/test_windows.py]], with [[MYLA-723]]'s): an interpreted case whose `test.temp_dir()` starts with `%TEMP%\myla-test-`, and `myla.exe test sq.my --native`, whose harness doesn't build under Wine (no LLVM for Windows there) and is kept, its path in the message: `C:\users\<user>\Temp\myla-test-<ns>\harness.exe.my`. [[scripts/windows-runner.py]]: `tools/myla-host-modules` runs the interpreted case on Windows (`TMPDIR` removed from its environment: a step's variable that is `None` is now removed), and `tools/myla-build` a native case that its harness runs from under `%TEMP%` (`temp.my`, `TMPDIR` removed), besides the case with `TMPDIR` set.

## Evidence

- **Test first.** With BASE's code: `HostModules.test_test_interpreted` gave `FAIL  under_temp #1: expected True, got False`; BASE's `myla.exe test t.my --native` under Wine said `(kept at /tmp/myla-test-1614928263700/harness.exe.my)`. After: both pass (`kept at C:\users\root\Temp\myla-test-1560281671000\harness.exe.my`, removed by the test).
- `scripts/windows-runner.py run --wine --runs 3`: `tools/myla-host-modules` ok; `tools/myla-build` skipped under Wine (needs the LLVM tools).
- The shared checks are in [[MYLA-734]]'s evidence.

Signed off by [[Project/Review-2026-11-17]] (done).
