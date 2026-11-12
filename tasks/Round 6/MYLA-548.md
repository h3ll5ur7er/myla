---
id: MYLA-548
title: "R6 The runtime: a line limit, the poller's creation, `Signals`, a failure beside a blocked read, raw mode and signals"
type: bug
status: todo
priority: medium
labels: [runtime, net, term, round-6]
---
Work package R6 of [[Project/Review-2026-11-12]]. Files: `lib/std/rt.my`, `lib/std/net.my`, `lib/std/term.my`, `lib/std/process.my`, the platform modules. Follows [[MYLA-419]] and [[MYLA-426]]. Decisions 2 and 5 of the review are the owner's.

- [ ] **`net.line_reader` has no line limit** and holds about three times the line (a 512 MiB line: 1.59 GB), so a peer that never sends `\n` ends the program with `out of memory`. A `net.line_reader_with(s, max_line)` that gives an `IoError` past the limit (`repro-r5/runtime/longline.my`)
- [ ] **The poller's creation isn't checked**: under `ulimit -n 64` with `MYLA_THREADS=1` and no descriptor left, the first `read_async` hangs for good; a failed `os.poller_new()` should fail the wait with its errno (`emfile2.my`)
- [ ] **A failure doesn't end the program while another task blocks in a key read**: the error is printed, the terminal stays raw, and a worker spins at 99 percent of a CPU until a key is pressed; `exit(4)` in a task waits the same way (`rawblock.my` with `t_rawblock.py`, 4 workers). In `wait_stopped`: run the exit hook before the wait, bound the wait, don't spin (D187)
- [ ] **Raw mode and signals** (decision 2): SIGINT, SIGTERM, SIGHUP, SIGQUIT leave the terminal raw, as the Term page says. Recommended: catch them while raw, restore, and end as the signal would
- [ ] **`Signals` as a D181 handle**: `Signals { handle: 0 }.try_next()` consumes a byte of stdin, and `close()` on any copy or forged value stops the real listening (`sig2.my`)
- [ ] **`Notifier.close()` beside a wait that is starting** (decision 5): six waiters closed 1 ms after they announced themselves died with `use of a closed notifier` in 2 of 9 runs (`nstress.my`). Recommended: a wait on a closed notifier returns at once; otherwise Concurrency.md must say that a closer has to know its waiters are parked
- [ ] More than 2^20 live notifiers is `too many notifiers open` interpreted and fine natively (`manyn.my`): one limit, documented
- [ ] A double close is `Ok` on a `TcpStream` and a `TcpListener`, `Other(9)` on a `File` and a `ChildStdin`
- [ ] `LineReader` gives a line cut off by the peer's close as an ordinary line; the caller can't tell
- [ ] `net.listen`'s backlog is fixed at 128 (100 connects at once on one loaded worker: up to a quarter reset by the kernel): a `listen_with(backlog)`
- [ ] `io.buffered(s).read_line()` in a task is a silent hang with more connections than workers; the type error for `buffered(s).read_line_async()` should point to `net.line_reader`
- [ ] `myla repl` loses a line longer than 4,095 bytes typed while the last one runs: the terminal is cooked between lines (`t_repl4.py`)
