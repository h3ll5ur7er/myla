---
id: MYLA-744
title: "Windows: std.signal's pipe looked at every millisecond while someone listens"
type: improvement
status: done
priority: low
labels: [platforms, windows, concurrency]
---
Found when wave 4's lanes were merged ([[MYLA-165]]). [[MYLA-707]]'s console control handler (`__win_on_ctrl`, [[selfhost/runtime_x86.my]]) writes a caught signal's number to an anonymous pipe (`CreatePipe`, `__sig_pipe`), which std.signal's reactor watches. [[MYLA-706]]'s poller waits on an I/O completion port, which can't wait on an anonymous pipe, so it looks at that pipe every millisecond while a program listens for signals: a program that only waits for Ctrl-C wakes a thousand times a second.

- [x] The handler tells the poller without the per-millisecond look: e.g. it posts a packet to the port (`PostQueuedCompletionStatus`, a kernel32 call that needs no state block, the port's handle in a process word), or the pipe becomes a named pipe whose read end is overlapped, as a child's pipes are
- [x] A program awaiting `std.signal` alone uses about no CPU under Wine (compared with this branch's, D197), and test_windows' `Console` cases pass on 1, 4 and 16 workers

## What changed

- **The handler** (`__win_on_ctrl`, `emit_windows_ctrl_handler` in [[selfhost/runtime_x86.my]]): after `WriteFile` has put the byte in the pipe, it posts a packet of no operation with the completion key 1 to the process's port, read from `__win_net`'s second word (`NET_PORT`), when there is one: `PostQueuedCompletionStatus(port, 0, 1, NULL)`, eight lines, on Windows' own thread without a state block as before. A program that calls it imports `PostQueuedCompletionStatus` from kernel32 too (every Windows program's import list has one more function). `__win_wait_posted` is unchanged.
- **The poller** ([[lib/std/platform_windows.my]]): std.signal's pipe gets a watched handle of its own kind, `K_SIGNAL` (`ws_watch`: the handle `signal_fd()` names), which is never looked at each millisecond (`ws_peeked` is for `K_PIPE`), and is read as a pipe is (`ws_level`). `poller_take` takes a packet whose key is `SIGNAL_KEY` (1) and has no OVERLAPPED as "look at the signal pipe": its watched handle, if armed and not looked at this wait, is looked at; `poller_wake`'s packet (key 0) is a wake-up as before.
- **Why no packet is lost:** the byte is in the pipe before the packet is posted, so a look the packet makes finds it; a packet taken while the watch isn't armed is dropped, and the arm that follows posts its own packet and looks at the pipe, which holds the byte. A signal that comes before the port exists posts nothing; the arm, which comes after the port, looks. Two workers: the packet is taken under the net lock as every other.

## Proposals (accepted 2026-11-17: D244)

1. **The handler posts a packet to the port** (built): the port's handle in a word of the process's (`__win_net`), `PostQueuedCompletionStatus` from Windows' handler thread, a key of its own. Alternatives: an overlapped named pipe as a child's pipes are (`K_PIPE_IN`: a read of no bytes in flight that ends when the byte comes): no assembly changed, but `signal_take`'s blocking `read` would then read an overlapped handle (the Host lane's `read`), and the pipe would be made with `CreateNamedPipeW` and `CreateFileW` and a name of its own; an event the handler sets and a wait of the thread pool's on it that posts (`RegisterWaitForSingleObject`, as a child's end): a second hop through the pool for what the handler can post itself.

Suggested decision row: "**Windows' console control handler tells the poller of a signal with a packet** ([[MYLA-744]], D230, D236): after writing the byte to std.signal's pipe, `__win_on_ctrl` posts a packet of no operation with the key 1 to the process's completion port (its handle in `__win_net`), and the poller looks at the pipe for it; the pipe is never looked at each millisecond | The owner's acceptance of the recommendation (2026-11-16). A program that only waits for a signal woke a thousand times a second; an overlapped named pipe would make `signal_take`'s read an overlapped one and the pipe a named one, for the same packet"

## Evidence

- **Test first**: `test_windows.Console.test_a_listener_alone_uses_no_cpu` (the console program's `interrupted` case under Wine, waiting for a Ctrl-C; the CPU of the program's process and of Wine's server of the prefix over 2 s, then the Ctrl-C taken and the default again), at BASE `478d656`'s compiler and library: `FAIL` on 1, 4 and 16 workers, 0.21, 0.21 and 0.23 s of CPU in 2 s (the limit then 0.1 s); after: `PASS` (limit 0.05 s).
- **Measured** (2026-11-16, 0adad44, Wine 9.0, this 4-CPU machine): a program whose only task awaits `signal.interrupted()`, 5 s waiting, built with BASE's library against this branch's: BASE's process 0.22, 0.23, 0.25 s of CPU and Wine's server 0.32, 0.29, 0.32 s on 1, 4 and 16 workers; this branch's 0.00 s and 0.01 s on each. Both took the Ctrl-C then (`got interrupt`).
- **The cases**: `test_windows.Console` 11 OK (the storm of 10 Ctrl-Cs, `interrupted`, `readline`, `close`, ctrl while raw and listening, on 1, 4 and 16 workers where the case runs them); `test_windows` and `test_windows_runner` 50 OK (1 skipped); `lib/std/platform_windows.my`'s 159 cases interpreted. The runner's `terminal/*` cases are Windows' own (skipped under Wine, as before): not run here; CI's `windows` job runs them.
- The suites of the lane's run are in [[MYLA-755]]'s evidence (one run for both).

Signed off by [[Project/Review-2026-11-17]] (done).
