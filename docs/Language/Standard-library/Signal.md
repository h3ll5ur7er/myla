# std.signal

The interrupt and terminate signals as events a program awaits ([[MYLA-350]]). Until a program asks, a signal does what it always did: Ctrl-C or a request to terminate ends the program. Only what every system has is here: an interrupt (SIGINT; Ctrl-C and Ctrl-Break on Windows) and a request to terminate (SIGTERM; a closed console, a log-off or a shutdown on Windows), not SIGUSR1, SIGHUP or SIGCHLD. On wasm32 (WASI has no signals) `listen` is `Unsupported`. While std.term holds the terminal raw, the runtime catches these two and SIGHUP and SIGQUIT to put the terminal's mode back before they end the program (D192, [[Language/Standard-library/Term#raw-mode-and-keys]]); a listener still gets the two it listens for.

[TOC]

## Listening

| Item | Meaning |
| --- | --- |
| `enum Signal { Interrupt, Terminate }` | A signal. `Eq`, `Hash`, `Format`: `interrupt`, `terminate` |
| `listen() -> Result<Signals, SignalError>` | Both caught from now on: they no longer end the program but wait in the `Signals`, in the order they came, until taken |
| `Signals`: `next() -> Result<Signal, SignalError>` (async) | The next signal, the task waiting for it while the other tasks run (outside a task the program waits); `Cancelled` when the task is asked to stop (`task.cancel`, `task.timeout`) |
| `Signals`: `try_next() -> Option<Signal>` | The next one if it came, without waiting |
| `Signals`: `close()` | No longer listening: once nobody listens, the signals end the program again, and those not taken are dropped. Several may be open, and they share what comes. A `Signals` is a handle of the runtime's table (D181, [[MYLA-548]]): a copy is the same listener, a second close (through any copy) lets go of nothing more, and one built by hand (`Signals { handle: 0 }`) takes no signal and no byte of the descriptor it names; before, it read a byte of stdin, and a second close stopped another listener's signals |
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

| Primitive | x86-64 and aarch64 Linux | wasm32 |
| --- | --- | --- |
| `__signal_listen(on) -> int` | `on` 1: SIGINT and SIGTERM handled by the runtime's `__on_signal` (rt_sigaction, `SA_RESTART`), a new handle of the listener's for the descriptor they arrive on (a pipe's read end, made once), which the reactor waits on as on a descriptor's; `on` a listener's handle: it is closed, and the defaults are back once the last listener lets go, the pipe drained; any other `on` is EBADF | -1, ENOSYS, EBADF |
| `__signal_take(h) -> int` | The next signal on the listener's handle, the thread waiting: 2 (interrupt) or 15 (terminate); 0 when it ended; -1 with the errno (EBADF for a handle that isn't a listener's) | -1, ENOSYS, EBADF |
| `await __wait_readable(h)` | The reactor's wait for input: epoll on the pipe | — |

A self-pipe, not a signalfd: a signalfd needs the signals blocked in every thread, and the workers that run tasks are started before a program asks, so one of them would take the signal with its default action. The handler (assembly in each backend's runtime, `selfhost/runtime_x86.my` and `runtime_a64.my`) does one thing, async-signal-safely: it writes the signal's number as a byte to the pipe's write end, non-blocking, whichever thread it interrupts. The read end is what the reactor already waits on for input, so nothing in `std.rt`'s scheduler changed. A system call the signal interrupts is restarted (`SA_RESTART`), and those that never are (epoll, poll, nanosleep) were already retried on EINTR. A child started after `listen` gets the default dispositions back at `exec`.

## Porting to another system

A port gives `std.platform`'s `signal_listen(on)` and `signal_take(h)` again ([[Language/Targets#the-terminal-and-signals-on-another-system]]); `std.signal` and `std.rt` stay as they are. The contract: `signal_listen(1)` gives a handle the reactor can wait on as it waits for input (`poller_watch`), readable while a signal waits; `signal_take(h)` gives the next, 2 for an interrupt and 15 for a request to terminate, waiting for one; `signal_listen(0)` gives the defaults back when the last listener lets go; `signal_fd()` names the descriptor `signal_listen(1)` gives (-1 before), which std.rt checks a listener's handle holds. For Windows (`platform_windows.my`):

- **The handler.** `SetConsoleCtrlHandler(routine, TRUE)` on the first listener, `FALSE` after the last. Windows runs the routine on a thread of its own, so it may write to a pipe (`CreatePipe`) with `WriteFile` freely. It maps `CTRL_C_EVENT` and `CTRL_BREAK_EVENT` to 2, and `CTRL_CLOSE_EVENT`, `CTRL_LOGOFF_EVENT` and `CTRL_SHUTDOWN_EVENT` to 15, and returns `TRUE` (handled), so the program goes on.
- **Closing the console.** For `CTRL_CLOSE_EVENT` and the two others Windows ends the process once the routine returns (after about 5 seconds for a close). The routine therefore waits there, on an event `signal_take` sets once it has taken a 15, or until the program ends, so a program has the time Windows gives to shut down.
- **Waiting.** The reactor waits on the pipe's read end as it waits on any input handle (an event signalled with each write serves where a pipe can't be waited on). `signal_take` reads one byte.
- **Default behaviour.** Without a listener nothing is installed, so Ctrl-C ends the program as Windows' default handler does.
