---
id: MYLA-759
title: "The x86_64-windows suites once hung in CI: test_selfhost_codegen still running after 64 minutes under Wine"
type: bug
status: review
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
- [x] Why `scopes_wait_for_children` doesn't end under Wine (on 1 to 16 workers, until it hangs), and whether the setup's fault caused it: a program that doesn't end under Wine, or a `subprocess.run` whose timeout waits for a pipe a Wine process holds
- [x] A fix, and the program's run bounded under Wine (kill the process group or the Wine prefix's processes at the timeout)

## Evidence

**The program ends; its output doesn't.** `scopes_wait_for_children` built for x86_64-windows, run under Wine 9.0 here (2026-11-18, BASE `3add216`) on 1, 2, 4, 8 and 16 workers, 4 copies at once, each with a prefix of its own (load average 60 to 100 from the other lanes and these runs):

- with each prefix's server and services started first, as BASE's `wine_env` does (`wineserver -p`, then a quiet `wineboot`): 2,000 of 2,000 runs printed `0 1 2 after` and ended, none in more than a second;
- with the server started and nothing else (the services not yet there): in each copy the first run's program ended at once (`[swc.exe] <defunct>`) and its `communicate` waited past its 60 s; killing the run's process group didn't end it either (`pipes still held after killing the group`). `/proc/<pid>/fd` of `services.exe`, `winedevice.exe`, `plugplay.exe`, `svchost.exe` and `rpcss.exe`: fd 2 a pipe, the program's standard error, each in a session of its own (`setsid`), started by that program, the first of its server. The other 49 runs of each copy ended.

So it isn't where its workers stop: the first program of a Wine server starts the prefix's services, which hold its standard error for as long as the server lives. On CI's runners the setup's fault (BASE's fix) left no persistent server, so the server was the short-lived one of whichever program started it: after a pause it stopped, the next program started it again and the services with it, and they held that program's standard error while the other suites' programs kept the server alive. A run with a `timeout` then raised at 60 s, as on `e6e1b9e`; one without waited for good, as on `4c91ba2` (`subprocess.run` kills and waits for the process only, then for its pipes); and on `dd57b05` a `--checked` program "printed its error and was still running at its 20 s". BASE's fix alone keeps the services started quietly while `scripts/test-target.py`'s server runs (`-p`, for good). It doesn't cover a server started again during a run: `wine_env`'s `-p60` after a pause of a minute in a plain `unittest` run, or a second run on the same prefix stopping it (`wineserver -k` at its exit).

**The fix:** a Windows program runs behind `tests/burn/_wine_run.py` (`_native.wine_run`, used by `run_argv` and, through `MYLA_EMULATOR`, by `myla test --target x86_64-windows` in `scripts/test-target.py`). It `exec`s Wine, so the caller's pid, signals and time limits are the program's (`test_http`'s socket counts read `/proc/<pid>`). Before that it forks a copier, and the program's standard output and error, where they are pipes, are the copier's pipes (one pipe when the caller's two are one, so their order is kept; non-blocking when the caller's are; a terminal, a file or a device stays the program's own, and a pipe whose reader has gone is closed, so the program's next write fails as it would have: the first version copied those too, and `test-target.py x86_64-windows` caught it in test_term, test_stdio and test_reactor_scaling). The copier copies them to the caller's as they come, and once its parent, the program, has ended, copies what they still hold and ends, whoever else holds them. A time limit's kill is the program's own, and the caller's pipes end with the copier.

- `test_windows.WinePrefix.test_a_run_ends_with_its_program_whatever_the_services_hold` (a fresh prefix, its server kept 30 s with no services, a hello world run with a 60 s limit): with `wine()` alone, BASE's command, it failed, `32.8 not less than 20 : the run waited for the server's 30 s`; with `wine_run()` it passes, the class's two tests in 36.9 s.
- `scripts/test-target.py x86_64-windows test_selfhost_codegen` behind the relay: `ok (93 s) OK (skipped=26)`, `test_tasks_on_any_number_of_workers` among its tests.
- The rate, staged as on CI (each copy's first run the first program of its server): 4 of 4 waited past 60 s before. After: the program ends, so does the run (the test above).

**Suites** (2026-11-18, this branch): `scripts/test.sh` 1,859 tests OK; `scripts/test-target.py` x86_64-windows 39 of 39 suites, aarch64-linux 38 of 39 then 39 (test_children_run_in_parallel, [[MYLA-745]]), wasm32-wasi 39 of 39; `tests.burn.test_windows` and `test_windows_runner` 73 tests OK under Wine; `scripts/windows-runner.py run --wine --runs 3`: 153 passed, 0 failed, 17 skipped of 170 cases (round 7's integration: 152 of 170, t15 failing); the bootstrap's fixed point, `scripts/check-seed.sh` and its Windows run.

## Proposals

- Built: every test run of a Windows program goes behind `_wine_run.py` (a Python process `exec`ing Wine, its output copied where it is a pipe). Alternatives: (a) only the setup's fix (BASE): enough while a run's server never stops, which nothing enforces; (b) check before each run that the prefix's services are up and start them quietly if not: racy, and a run per program more; (c) temporary files for the output instead of pipes: breaks the tests that read a program's output as it comes.
