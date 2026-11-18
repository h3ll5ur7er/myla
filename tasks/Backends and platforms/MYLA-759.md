---
id: MYLA-759
title: "The x86_64-windows suites once hung in CI: test_selfhost_codegen still running after 64 minutes under Wine"
type: bug
status: todo
priority: medium
labels: [windows, wine, ci, round-7]
---
CI's `Burn suites on x86_64-windows` on 4c91ba2 (run 44241182727, 2026-11-18) printed nothing from 05:11, when the suites started, to the job's 75-minute limit at 06:15, and was cancelled. `scripts/test-target.py` then printed results in the suites' order, and the first, `test_selfhost_codegen`, never ended. On the run before, 04d8956, the same suite took 609 s, and the code under test was the same: between the two commits only CI's time limits and the SOCKETS program of `test_windows` changed, and `test_windows` isn't one of the target's suites. After the hang, on 5075488, the suites passed in 7 minutes. Python processes and several `wine64` processes were still running when the job was cancelled.

Here, at 4c91ba2 under Wine 9.0, no hang:
- the whole suite, 3 runs of 70 to 79 s;
- `test_tasks_on_any_number_of_workers`, its slowest test (13 to 18 s; programs on 1 to 16 workers, each run with a 60 s `timeout`), 16 runs, two at a time with a Wine prefix each.

That test's 60 s doesn't bound it under Wine. `subprocess.run` with a `timeout` kills the process it started, then waits for its pipes to close. A Wine process that inherited them and keeps running can make it wait forever.

Since [[MYLA-798]]'s 5075488, each suite is stopped after `--limit` seconds (1,500 by default) and fails with its log, which names each test as it starts. A recurrence now names its test.

Two runs on one Wine prefix kill each other's programs. Each run's `prepare_wine` stops the prefix's server at exit (`wineserver -k`), and a program still running in the other run ends with nothing printed and exit code 0. That is what a first stress run here showed: `task_tree` printed nothing in 7 of 16 runs. With a prefix each, 16 of 16 passed. This is a hazard for whoever runs the suites twice at once, not a bug in Myla's code.

**On master, 2026-11-18, twice more:**
- `e6e1b9e` (run 44258065912): `test_tasks_on_any_number_of_workers` failed with `scopes_wait_for_children` past its 60 s, the timeout firing this time. The hung test is most likely this one, its program not ending under Wine.
- `dd57b05` (run 44272004148): two programs at once. A `test_compiler_parity` program's stderr began with Wine's own `wine: failed to open L"C:\windows\syswow64\rundll32.exe": c0000135` and `wine: configuration in L".../build/wineprefix" has been updated.`; a `--checked` program of `test_generated_extremes` printed its error and was still running at its 20 s. So Wine set its prefix up again while the suites ran.

**The setup's fault** (`_native.wine_env`, fixed here): it started the persistent server (`wineserver -p`) before the prefix existed, and on a prefix that isn't there the server stops at once (`wineserver: chdir to …: No such file or directory`, exit 1). CI's runners start with no prefix, so their suites ran on the short-lived server of the boot, with nothing waiting for the prefix's setup to end. Now a new prefix is made and its setup waited for (`wineboot --init`, then `wineserver -w`), and the server is started then. `tests.burn.test_windows.WinePrefix` (a fresh prefix keeps its server 6 s after `wine_env`) failed before and passes after.

(Here, in this container since its restart, `TMPDIR=/tmp` set alone makes `wine64` abort with `free(): invalid pointer`; unset it to run Wine here.)

- [x] The hung test: `scopes_wait_for_children` in `test_tasks_on_any_number_of_workers` (master's `e6e1b9e`)
- [x] The setup's fault: the persistent server started before a new prefix existed (fixed, with `WinePrefix`)
- [ ] Why `scopes_wait_for_children` doesn't end under Wine (on 1 to 16 workers, until it hangs), and whether the setup's fault caused it: a program that doesn't end under Wine, or a `subprocess.run` whose timeout waits for a pipe a Wine process holds
- [ ] A fix, and the program's run bounded under Wine (kill the process group or the Wine prefix's processes at the timeout)
