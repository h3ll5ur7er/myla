# std.signal

The interrupt and terminate signals as events a program awaits ([[MYLA-350]]). Until a program asks, a signal does what it always did: Ctrl-C or a request to terminate ends the program. Only what every system has is here: an interrupt (SIGINT; Ctrl-C and Ctrl-Break on Windows) and a request to terminate (SIGTERM; a closed console, a log-off or a shutdown on Windows), not SIGUSR1, SIGHUP or SIGCHLD. On Windows they are the console's control events ([[MYLA-707]], D216; [[#porting-to-another-system]]): a Ctrl-C nobody takes ends the program with the exit code `STATUS_CONTROL_C_EXIT` (0xC000013A), and after a close, a logoff or a shutdown a listener's program has the time Windows gives (5 seconds for a close) to end itself. On wasm32 (WASI has no signals) `listen` is `Unsupported`. While std.term holds the terminal raw, the runtime catches these two and SIGHUP and SIGQUIT to put the terminal's mode back before they end the program (D192, [[Language/Standard-library/Term#raw-mode-and-keys]]); a listener still gets the two it listens for.

[TOC]

## Listening

| Item | Meaning |
| --- | --- |
| `enum Signal { Interrupt, Terminate }` | A signal. `Eq`, `Hash`, `Format`: `interrupt`, `terminate` |
| `listen() -> Result<Signals, SignalError>` | Both caught from now on: they no longer end the program but wait in the `Signals`, in the order they came, until taken |
| `Signals`: `next() -> Result<Signal, SignalError>` (async) | The next signal, the task waiting for it while the other tasks run (outside a task the program waits); `Cancelled` when the task is asked to stop (`task.cancel`, `task.timeout`) |
| `Signals`: `try_next() -> Option<Signal>` | The next one if it came, without waiting |
| `Signals`: `close()` | No longer listening: once nobody listens, the signals end the program again, and those not taken are dropped. Several may be open, and they share what comes. A `Signals` is a handle of the runtime's table (D181, [[MYLA-548]]): a copy is the same listener, a second close (through any copy) lets go of nothing more, and one built by hand (`Signals { handle: 0 }`) takes no signal and no byte of the descriptor it names; before, it read a byte of stdin, and a second close stopped another listener's signals. Closing one built by hand does nothing, `Signals { handle: 1 }` too, whose close began to listen for good ([[MYLA-794]]) |
| `interrupted() -> Result<Signal, SignalError>` (async) | `listen`, `next` and `close` in one: the first interrupt or termination, after which a second Ctrl-C ends the program |
| `enum SignalError { Unsupported, Cancelled, Other(int) }` | `Eq`, `message()`, `Format` (D168) |

A server stops on Ctrl-C and finishes what it was doing:

```myla fragment
#main
async fun main() {
    async let server = serve(listener)
    match await signal.interrupted() {
        Ok(sig) => println(f"stopping on {sig}")
        Err(e) => println(f"no signals: {e}")
    }
    task.cancel(server)
    println(f"{await server} requests served")
}
```

```myla
import std.signal as signal

fun main() {
    match signal.listen() {
        Ok(s) => {
            let waiting = match s.try_next() {
                Some(sig) => f"{sig}"
                None => "nothing"
            }
            print(f"listening, {waiting} yet")
            s.close()
        }
        Err(e) => print(f"{e}")
    }
}
// output:
// listening, nothing yet
```

## Primitives

| Primitive | x86-64 and aarch64 Linux | Windows ([[MYLA-707]]) | wasm32 |
| --- | --- | --- | --- |
| `__signal_listen(on) -> int` | `on` 1: SIGINT and SIGTERM handled by the runtime's `__on_signal` (rt_sigaction, `SA_RESTART`), a new handle of the listener's for the descriptor they arrive on (a pipe's read end, made once), which the reactor waits on as on a descriptor's; `on` a listener's handle: it is closed, and the defaults are back once the last listener lets go, the pipe drained; any other `on` is `Other(9)` (BAD_HANDLE) | The console's control events through the runtime's `__win_on_ctrl` (`SetConsoleCtrlHandler`) to a pipe (`CreatePipe`, made once); the rest as on Linux | -1, UNSUPPORTED, BAD_HANDLE |
| `__signal_take(h) -> int` | The next signal on the listener's handle, the thread waiting: 2 (interrupt) or 15 (terminate); 0 when it ended; -1 with the cause (BAD_HANDLE for a handle that isn't a listener's) | The same (`ReadFile` of a byte) | -1, UNSUPPORTED, BAD_HANDLE |
| `await __wait_readable(h)` | The reactor's wait for input: epoll on the pipe | The poller's: the pipe, anonymous, looked at when the handler posts a packet to the poller's port (D236, [[MYLA-744]]) | — |

A self-pipe, not a signalfd: a signalfd needs the signals blocked in every thread, and the workers that run tasks are started before a program asks, so one of them would take the signal with its default action. The handler (assembly in each backend's runtime, `selfhost/runtime_x86.my` and `runtime_a64.my`) does one thing, async-signal-safely: it writes the signal's number as a byte to the pipe's write end, non-blocking, whichever thread it interrupts. The read end is what the reactor already waits on for input, so nothing in `std.rt`'s scheduler changed. A system call the signal interrupts is restarted (`SA_RESTART`), and those that never are (epoll, poll, nanosleep) were already retried on EINTR. A child started after `listen` gets the default dispositions back at `exec`.

## Porting to another system

A port gives `std.platform`'s `signal_listen(on)` and `signal_take(h)` again ([[Language/Targets#the-terminal-and-signals-on-another-system]]); `std.signal` and `std.rt` stay as they are. The contract: `signal_listen(1)` gives a handle the reactor can wait on as it waits for input (`poller_watch`), readable while a signal waits; `signal_take(h)` gives the next, 2 for an interrupt and 15 for a request to terminate, waiting for one; `signal_listen(0)` gives the defaults back when the last listener lets go; `signal_fd()` names the descriptor `signal_listen(1)` gives (-1 before), which std.rt checks a listener's handle holds. Windows' (`platform_windows.my`, [[MYLA-707]]):

- **The handler.** `SetConsoleCtrlHandler(__win_on_ctrl, TRUE)` the first time a program listens or makes the console raw (D192); it stays, and passes on (`FALSE`) what nobody listens for, as if it weren't there. Windows runs it on a thread of its own, which has no state block of the runtime's (the workers' TLS slot is empty there, D222), so it is assembly (`selfhost/runtime_x86.my`) that allocates nothing and reaches only the process's words, as Linux's `__on_signal` is. It maps `CTRL_C_EVENT` and `CTRL_BREAK_EVENT` to 2, and `CTRL_CLOSE_EVENT`, `CTRL_LOGOFF_EVENT` and `CTRL_SHUTDOWN_EVENT` to 15; while someone listens it writes the byte to the pipe (`WriteFile`), posts a packet to the poller's port (`PostQueuedCompletionStatus`, the key `SIGNAL_KEY`, once the port is there: its handle is a word of the process's, `__win_net`'s second) and returns `TRUE` (handled), so the program goes on; else, while std.term holds the console raw, it puts the mode back (`raw_signal`) and passes the event on; anything else it passes on.
- **Closing the console.** For `CTRL_CLOSE_EVENT` and the two others Windows ends the process once the handlers return (after about 5 seconds for a close). The handler therefore waits after it wrote the 15, until the program ends itself or Windows ends it: a program has the time Windows gives to shut down, as Go's runtime does.
- **Waiting.** The reactor waits on the pipe's read end as it waits on a child's pipe (`poller_watch`). It is an anonymous pipe, which [[MYLA-706]]'s completion port can't wait on: its watched handle is of its own kind (`K_SIGNAL`), looked at when the arm posts its packet and when the handler's packet (`SIGNAL_KEY`, no operation) comes, so a program that only waits for a signal waits without a time limit ([[MYLA-744]]: it was looked at every millisecond). The byte is in the pipe before the packet is posted, so a look the packet makes finds it, and a packet that comes before the arm is dropped and the arm's own look finds the byte. `signal_take` reads one byte.
- **A read of the console.** A Ctrl-C or a Ctrl-Break typed while a read of the console's lines waits ends that read with nothing read and no error; the console's control handler counts each such event, so `read` tells it from the input's end (Ctrl-Z) by the count, waiting up to 100 ms for the handler, as Python's console reader waits for its SIGINT (an `ERROR_OPERATION_ABORTED` counts as one too, MYLA-708). `read` then reads again, as Linux restarts a read a caught signal interrupts (`SA_RESTART`), so a listener's program goes on reading, and one without a listener is ended by the default meanwhile.
- **Default behaviour.** Without a listener (and outside raw mode) the handler passes every event on, so Ctrl-C ends the program as Windows' default handler does (`STATUS_CONTROL_C_EXIT`). A program started with Ctrl-C ignored (`CREATE_NEW_PROCESS_GROUP`) gets no Ctrl-C at all, a listener's neither; Ctrl-Break still comes.
