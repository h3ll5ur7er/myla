---
id: MYLA-728
title: "std.test's case directories on Windows: TEMP, not /tmp"
type: bug
status: done
priority: low
labels: [platforms, windows, testing]
---
Found by [[MYLA-705]], which runs a native test harness's cases as children on Windows (D217's `spawns`). `run_in_children` ([[lib/std/test.my]]) puts each case's scratch directory (MYLA_TEST_DIR) under `TMPDIR`, else `/tmp`. On Windows `TMPDIR` is rarely set, and `/tmp` is a directory of the current drive that isn't there. Under Wine it is `Z:\tmp`, which is Linux's, so it works there. Files come with [[MYLA-704]]; once they do, a case that uses `test.temp_dir()` on Windows needs a directory that exists.

- [x] On Windows the root is `TEMP` (else `TMP`, else the system's temporary directory), joined with `\`
- [x] A test of a case's `temp_dir()` under Wine and, on a Windows runner ([[MYLA-708]]), outside Wine's `Z:`

## What changed

`run_in_children` ([[lib/std/test.my]]) takes its root from std.fs's `temp_root()` (D227: `TMPDIR`, `TEMP`, `TMP`, else `.` on Windows; `TMPDIR` else `/tmp` elsewhere, as before) and joins `myla-test-<ns>` and each case's `c<k>` with `\` on Windows. Under Wine `%TEMP%` is `C:\users\<user>\Temp`, not on `Z:`, so the test under Wine already shows a directory outside Linux's tree; the Windows runner ([[MYLA-708]]) runs the same harness with Windows' own `%TEMP%`. The rest of the system's temporary directory (`GetTempPath2W`) isn't asked: D227's `.` stays the last resort.

Left as they are: the toolchain's own scratch directories (`myla test`'s harness build in [[selfhost/driver.my]], [[selfhost/project_cmd.my]], the interpreter's case root in [[selfhost/interp.my]]) still use `TMPDIR` else `/tmp`, which matters only for `myla.exe` running on Windows ([[MYLA-729]]).

## Evidence

- **Test first**: `test_windows`'s `Children.test_a_harness_runs_its_cases_as_children` with the new cases `case_dir` (`\c6`), `under_temp` (`MYLA_TEST_DIR` under `%TEMP%\myla-test-`, not on `Z:`) and `a_temp_dir` (a case's `temp_dir()` made and written in): on BASE `expected '\\c6', got '/c6'`, `under_temp` `expected True, got False`, `a_temp_dir` failed (no random bytes there yet, [[MYLA-722]]); 5/9 passed. After: 8/9 passed, as expected (`f #4` fails by design).
- `lib/std/test.my` 87/87 interpreted, `--native` and under Wine; `test_test_native` and `test_test_functions` (Linux's roots unchanged) in the suites below.

Signed off by [[Project/Review-2026-11-17]] (done).
