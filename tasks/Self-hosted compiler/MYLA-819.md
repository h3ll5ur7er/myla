---
id: MYLA-819
title: "A test child's own children outlive a killed harness, and on Windows a timed-out case"
type: bug
status: todo
priority: low
labels: [testing, harness, windows]
---
Found by [[MYLA-792]] (D259). Natively each case runs in a child of the harness. On Linux the child leads a process group of its own (`std.test`'s `own_group`), which the harness kills when the case ends or passes its time limit, and it gets `PR_SET_PDEATHSIG` (SIGKILL), as the harness does towards `myla test`: killing `myla test --native` kills the harness and the case. Two gaps are left:

- **Linux, the harness killed:** the case dies with it, but a process the case started is in the case's group and isn't signalled (nobody is left to kill the group). For example a case running `sh -c "sleep 300"` while `myla test --native` is killed with SIGKILL leaves the `sleep`.
- **Windows:** there are no process groups: past the time limit the harness kills the case's process only (`Child.kill`, TerminateProcess), and a case's children are left; nothing ties the harness to `myla test` either.

- [ ] Linux: a case's group is killed when the harness dies too (a subreaper, `PR_SET_CHILD_SUBREAPER`, in a small parent that outlives the harness, or the case's PDEATHSIG handled by a handler of the runtime's that kills its group)
- [ ] Windows: each case in a job object killed with the job (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`), the harness in one of `myla test`'s
- [ ] Tests on both (the Windows one where only the `windows-latest` job can show it, said so)
