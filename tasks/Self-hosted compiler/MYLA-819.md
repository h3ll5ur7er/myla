---
id: MYLA-819
title: "A test child's own children outlive a killed harness, and on Windows a timed-out case"
type: bug
status: in-progress
priority: low
labels: [testing, harness, windows]
---
Found by [[MYLA-792]] (D259). Natively each case runs in a child of the harness. On Linux the child leads a process group of its own (`std.test`'s `own_group`), which the harness kills when the case ends or passes its time limit, and it gets `PR_SET_PDEATHSIG` (SIGKILL), as the harness does towards `myla test`: killing `myla test --native` kills the harness and the case. Two gaps are left:

- **Linux, the harness killed:** the case dies with it, but a process the case started is in the case's group and isn't signalled (nobody is left to kill the group). For example a case running `sh -c "sleep 300"` while `myla test --native` is killed with SIGKILL leaves the `sleep`.
- **Windows:** there are no process groups: past the time limit the harness kills the case's process only (`Child.kill`, TerminateProcess), and a case's children are left; nothing ties the harness to `myla test` either.

- [ ] Linux: a case's group is killed when the harness dies too (a subreaper, `PR_SET_CHILD_SUBREAPER`, in a small parent that outlives the harness, or the case's PDEATHSIG handled by a handler of the runtime's that kills its group)
- [ ] Windows: each case in a job object killed with the job (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`), the harness in one of `myla test`'s (each case: done; the harness in one of `myla test`'s needs `myla test` itself, `selfhost/driver.my`, the Interpreter lane's, to call `own_job` on Windows: proposed below)
- [ ] Tests on both (the Windows one where only the `windows-latest` job can show it, said so)

## Evidence (Windows part, the Concurrency and Windows lane)

- `std.platform.own_job()` (Windows; `false` elsewhere): this process in a job object of its own, whose one handle it holds, with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`: what it starts from then on is in the job, and goes when the process ends, killed or not. std.test's test child calls it where it would lead a process group on Linux (`own_group`), so a case the runner kills past its time limit (`TerminateProcess`) takes its children along.
- Under Wine 9.0: a program that calls it, starts `helper.exe sleep 60123` and ends leaves no helper (`test_windows.PlatformFollowUps.test_a_job_of_its_own_takes_its_children_along`); without the call, the same child outlives it. A timed-out case's children can't be shown under Wine: `myla test` there kills the case's Unix process group, Wine processes included, so at BASE too nothing was left (checked: a case starting `helper.exe sleep 60000` and looping, `--timeout 6`, no helper after, before and after). Only CI's `windows` job runs one on Windows.

**Suites** (2026-11-18, this branch): `scripts/test.sh` 1,859 tests OK; `scripts/test-target.py` x86_64-windows 39 of 39 suites, aarch64-linux 38 of 39 then 39 (test_children_run_in_parallel, [[MYLA-745]]), wasm32-wasi 39 of 39; `tests.burn.test_windows` and `test_windows_runner` 73 tests OK under Wine; `scripts/windows-runner.py run --wine --runs 3`: 153 passed, 0 failed, 17 skipped of 170 cases (round 7's integration: 152 of 170, t15 failing); the bootstrap's fixed point, `scripts/check-seed.sh` and its Windows run.

## Proposals

- `myla test` on Windows calls `own_job()` at its start (`selfhost/driver.my`), so that killing it takes the harness and its cases along, as `PR_SET_PDEATHSIG` does on Linux; the runner (the harness) could too. Left to the Interpreter lane, whose files those are.
