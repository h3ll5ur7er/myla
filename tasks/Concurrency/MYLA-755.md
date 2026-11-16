---
id: MYLA-755
title: "A busy worker glances at the poller every 64 frames, not by time: under load no worker polls for seconds"
type: bug
status: todo
priority: medium
labels: [concurrency, performance]
---
Found by [[MYLA-753]]. std.rt's poller is waited in by an idle worker, and a busy one glances at it every 64 frames it runs (`exec_run`'s `turns & 63`, [[lib/std/rt.my]], D124). When every worker stays busy and frames are slow (a loaded machine, [[MYLA-754]]'s convoy), the glances come seconds apart, and so does every wake-up for I/O: in a traced run of `SOCKETS 200 50` on 16 workers under Wine (the machine's load average about 60, [[MYLA-753]]'s fix in), no worker took a packet from 6143846 ms to 6147222 ms, while the workers armed about 100 handles, and the server's parked connection, whose request had come at once, was dropped at its 5 s.

- [ ] A busy worker glances once a time has passed since the last poll of any worker (a millisecond, read from the clock every so many turns, or the timers' clock), as Go's `sysmon` and tokio's event interval bound a ready descriptor's wait whatever the run queues hold
- [ ] A test that holds every worker busy and measures how long a ready socket waits

## Not done in [[MYLA-753]]'s round (2026-11-16)

Not small: in the traced run each of the 16 workers ran about six frames in those 3.4 s, so a glance every so many turns, however few, wouldn't have come; bounding the wait by time needs the clock read at every turn (a `clock_gettime` system call in this runtime on Linux, which has no vDSO path), a cost on every task switch, or a time another thread keeps (a runtime variable, so a seed staged, D207). With [[MYLA-754]] and [[MYLA-756]] fixed the loaded runs above hung none, so this waits.

