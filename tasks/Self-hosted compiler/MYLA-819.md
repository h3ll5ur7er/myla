---
id: MYLA-819
title: "A test child's own children outlive a killed harness, and on Windows a timed-out case"
type: bug
status: review
priority: low
labels: [testing, harness, windows]
---
Found by [[MYLA-792]] (D259). Natively each case runs in a child of the harness. On Linux the child leads a process group of its own (`std.test`'s `own_group`), which the harness kills when the case ends or passes its time limit, and it gets `PR_SET_PDEATHSIG` (SIGKILL), as the harness does towards `myla test`: killing `myla test --native` kills the harness and the case. Two gaps are left:

- **Linux, the harness killed:** the case dies with it, but a process the case started is in the case's group and isn't signalled (nobody is left to kill the group). For example a case running `sh -c "sleep 300"` while `myla test --native` is killed with SIGKILL leaves the `sleep`.
- **Windows:** there are no process groups: past the time limit the harness kills the case's process only (`Child.kill`, TerminateProcess), and a case's children are left; nothing ties the harness to `myla test` either.

- [x] Linux: a case's group is killed when the harness dies too (a subreaper, `PR_SET_CHILD_SUBREAPER`, in a small parent that outlives the harness, or the case's PDEATHSIG handled by a handler of the runtime's that kills its group)
- [ ] Windows: each case in a job object killed with the job (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`), the harness in one of `myla test`'s
- [ ] Tests on both (Linux: done) (the Windows one where only the `windows-latest` job can show it, said so)

## What changed (Linux)

A watcher beside the cases ([[lib/std/test.my]] `watch_mode`, `start_watcher`, `Watcher`, `group_named`, `last_line`): on Linux the runner (`run_in_children`) starts `<harness> --watch-groups` (under the emulator too), its input a pipe the runner holds, its output nothing. The watcher leads a group of its own (so a Ctrl-C meant for `myla test` doesn't end it first) and doesn't die with the runner. `output_within` takes the watcher's descriptor (`watch`, -1 for none) and writes the case's process ID on a line as it starts it and `0` once it has ended (and its group was killed). When the watcher's input ends, the runner has ended or died (killed, or with `myla test` through its PDEATHSIG), and the watcher kills the group named last (`end_group`), then ends. After its last case the runner closes the input and reaps the watcher. The harness's `#main` ([[selfhost/harness.my]] `harness_source`) calls `watch_mode` after `tool_mode`. Its cost is one process per run, not per case.

Chosen over a subreaper in a small parent of each case (a process more per case, and a way for it to learn the harness died) and over a catchable PDEATHSIG with a handler in the runtime that kills the group (a signal handler the runtime doesn't have: a runtime and seed change, D207). The pipe's write end is the runner's alone (O_CLOEXEC), so the input ends exactly when the runner does.

## Evidence

- `test_a_case_s_children_go_with_a_killed_run` ([[tests/burn/test_test_native.py]]): `myla test --native --timeout 0` of a case running `sh -c "sleep 318"`, killed with SIGKILL once the `sleep` runs; afterwards no `sleep 318` within 5 s. Before (BASE 3add216): fails, `['21568', '21569']` (`sh -c sleep 318` and `sleep 318`) left. After: passes.
- `test_a_case_s_children_go_with_it` counts the runner's processes before it kills `myla test`: three now (runner, watcher, case), and all are gone after it.

## Left open

- **Windows** (job objects, `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, and its test): the Concurrency and Windows lane's in round 7's follow-ups (it changes `lib/std/platform_windows.my`), not this lane's; this lane left it untouched. On Windows (and wasm32) `start_watcher` starts nothing.

## Proposals

- **A watcher per run** (built), as above. Alternatives: a subreaper parent per case; the case's PDEATHSIG caught by a runtime handler that kills its group.
- Not done, a small race noted: a runner killed between starting a case and the case's `setpgid`/`prctl` (the first statements of its `reporting`) leaves that case running without a group or a parent-death signal. Closing it needs the spawn to set both before `exec` (a spawn option of the platform's).
