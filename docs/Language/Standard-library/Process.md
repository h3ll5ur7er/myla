# std.process

The process itself and the programs it runs.

| Item | Meaning |
| --- | --- |
| `args() -> [str]` | Command-line arguments; `args()[0]` is the program as invoked |
| `exit(code: int32)` | Ends the process; the low 8 bits become the exit status |
| `env(name: str) -> Option<str>` | The value of the environment variable `name` the process started with (`""` included), or `None` when there is none ([[MYLA-243]]; the primitive `__getenv`, which reads the environment the process started with, or `""` with `__io_errno` 2) |
| `run(program: str, args: [str]) -> Result<Output, SpawnError>` | Runs a program, waits, captures its output. A name without a `/` is looked for in each directory of `PATH` (`/bin:/usr/bin` without one), as a shell looks; one with a `/` is that path (D147). The child inherits the environment, the directory and stdin |
| `run_async(program: str, args: [str]) -> Result<Output, SpawnError>` (async) | `run` in a task: the task waits for the child (its output read as it comes, then its end) suspended, the other tasks running (D124, [[MYLA-230]]); outside a task it blocks as `run` does. A task asked to stop stops waiting: the child is killed and reaped, `Err(SpawnError.Cancelled)` |
| `command(program)` → `Command` | Builder: `.arg(a)`, `.args([…])`, `.cwd(dir)`, `.env(name, value)`, `.env_remove(name)`, `.env_clear()`, `.stdin(text)`, `.stdin_from(how)`, `.stdout_from(how)`, `.stderr_from(how)`, `.stdin_from_stdout(out)` (below), then `.output()` or `.output_async()` (async, as `run_async`) (D147), `.spawn()` or `.pipe(next)` (below). A `Command` is a value: each builder method gives a new one and leaves the one it was called on as it was. Without `stdin` the child reads this process's stdin; with it, the whole text; `stdin_from(Stdio.Null)` (or `Piped`, which `output` has nobody to write) an empty one; `env_clear()` starts from an empty environment, which later `env` calls add to. On wasm32 all of it is `Unsupported` |
| `struct Output { stdout: [uint8], stderr: [uint8], status: ExitStatus }` | Output is raw bytes |
| `enum ExitStatus { Exited(int32), Signaled(int32) }` | `Eq` |
| `enum SpawnError { NotFound, PermissionDenied, Unsupported, Cancelled, InvalidInput, WorkingDir(int32), Other(int32) }` | Why a program couldn't be run (D129): not there, not allowed (EACCES or EPERM), no processes on this target, or the waiting task was stopped; `InvalidInput`: what no process can take, such as a `Command` given an environment variable name no variable can have (empty, with `=` or a NUL byte), or a NUL byte in the program's name, an argument or the directory, which then runs nothing (D160, [[MYLA-419]]); `WorkingDir`: the directory `cwd` gave can't be entered, with its errno (2 not there, 20 not a directory, 13 denied; [[MYLA-419]]: it was `NotFound`); `Other` holds the platform's own code for anything else. `Eq`, `message()` and `Format` (D168) |

```myla
from std.process import command, ExitStatus

fun main() {
    match command("/bin/echo").arg("hello").output() {
        Ok(out) => {
            let code = match out.status {
                Exited(c) => c
                Signaled(sig) => 128 + sig
            }
            print(out.stdout.len())
            print(code)
        }
        Err(e) => print("could not start")
    }
}
// output:
// 6
// 0
```

## Children as streams

`Command.spawn()` starts a program and doesn't wait for it ([[MYLA-340]]). The `Child` it gives runs beside this process: write its input, read its output as it comes, wait for it or kill it. Its streams are `std.io` streams ([[Language/Standard-library/Io#streams]]): the input a `Write`, the output and error `Read`s, so `buffered(…)` reads their lines and `copy` and `read_all` take them.

```myla
from std.process import command, ExitStatus
from std.io import buffered
import std.bytes as bytes

fun main() {
    var child = match command("cat").spawn() {
        Ok(c) => c
        Err(e) => panic(f"could not start cat: {e}")
    }
    var input = child.take_stdin().expect("a pipe")
    var lines = buffered(child.take_stdout().expect("a pipe"))
    for word in ["one", "two"] {
        input.write(bytes.from_str(word + "\n"))
        match lines.read_line() {
            Ok(Some(line)) => print(f"cat said {line}")
            _ => print("no line")
        }
    }
    input.close()
    match child.wait() {
        Ok(ExitStatus.Exited(code)) => print(f"exited with {code}")
        _ => print("ended otherwise")
    }
    match command("printf").arg("pear\\nfig\\n").pipe(command("sort")).output() {
        Ok(out) => print(bytes.to_str(out.second.stdout).trim_end())
        Err(e) => print(f"{e}")
    }
}
// output:
// cat said one
// cat said two
// exited with 0
// fig
// pear
```

| Item | Meaning |
| --- | --- |
| `c.spawn() -> Result<Child, SpawnError>` | The command started, not waited for. Its output and error are pipes unless `stdout_from` or `stderr_from` said otherwise; its input is a pipe too, unless `stdin(text)` gave a text, `stdin_from` `Inherit` or `Null`, or `stdin_from_stdout` another child's output. The errors are `output`'s; on wasm32 `Unsupported` |
| `c.stdin_from(how: Stdio)` | The child's input: `Stdio.Piped` (a pipe this process writes; `spawn`'s default), `Inherit` (this process's; `output`'s default) or `Null` (empty: it ends at once). It replaces a text `stdin` gave, and `stdin` replaces it |
| `c.stdout_from(how: Stdio)`, `c.stderr_from(how: Stdio)` | The child's output, its error: `Piped` (a pipe this process reads; the default), `Inherit` (this process's) or `Null` (dropped, /dev/null) ([[MYLA-378]]). A stream that isn't a pipe can't fill up, so a child writing much to it never waits for this process. `output` takes them too: such a stream is empty in its `Output` |
| `c.stdin_from_stdout(out: ChildStdout)` | The child's input another child's output, straight, as a shell's `a \| b` joins them ([[MYLA-378]]). `spawn` hands the stream over: this process's end is closed, so it can't be read here after (`Other(9)`), nor handed over again (`SpawnError.Other(9)`) |
| `child.take_stdin() -> Option<ChildStdin>`, `take_stdout() -> Option<ChildStdout>`, `take_stderr() -> Option<ChildStderr>` | The stream, given out once; `None` after that, and for an input that isn't a pipe. A stream holds a handle (D181): once closed, every copy of it is `Other(9)`, never the pipe that got its descriptor next, and so is a stream built by hand; a `kill` through a copy of a `Child` another copy reaped signals nothing |
| `child.wait() -> Result<ExitStatus, IoError>` | Waits (blocking) and reaps. First it closes the input the `Child` still holds, so a child that reads to the end of its input finishes, and reads the output and error it still holds to their end and drops them, so a child that writes much to a stream nobody took doesn't stop; that waits for every process that holds them, as `output` does. A second `wait` gives the same status |
| `child.wait_with_output() -> Result<Output, IoError>` | `wait`, keeping what the held output and error gave (a stream taken before is empty in it) |
| `child.try_wait() -> Result<Option<ExitStatus>, IoError>` | The status if the child has ended (it is reaped then), `None` while it runs; it doesn't wait |
| `child.kill() -> Result<(), IoError>` | SIGKILL; `wait` then gives `Signaled(9)`. A child reaped already isn't signalled (its ID may be another process's by now): `Ok` |
| `child.id() -> int32` | Its process ID |
| `await child.wait_async()`, `await child.wait_with_output_async()` | The waits in a task: the task suspended until the streams have bytes and the child ends (its pidfd), the other tasks running (D124); outside a task they block. A task asked to stop stops waiting, `Err(IoError.Cancelled)`, and leaves the child running |
| `ChildStdin` | `Write` (`write`, `flush`; text through `bytes.from_str` or a `buffered_writer`), `write_async(b)` (async), `Pollable`, `close()`. A write blocks while the pipe is full; one to a child that closed its input is `BrokenPipe`. `write_async` waits for room with the task suspended, PIPE_BUF bytes (4096) at a time, so a task feeding a child's input and another reading its output go on together on one worker and interpreted too, where a blocking write never let the reader run ([[MYLA-340]], [[MYLA-419]]); a cancelled task gets `Cancelled` |
| `ChildStdout`, `ChildStderr` | `Read` (`read`; `[]` at the end; text through `buffered`), `Pollable` (so a `Buffered` over one has the async reads), `close()` |

`Command`'s `spawn_opts`, `opts_with`, `stdio_letters` and `spawn_for_output`, and `Child`'s `close_input`, `drain`, `drain_async`, `reap_async` and `forget_exited`, are the steps of `spawn`, `output` and `wait`, public only because a method can't be private yet ([[MYLA-433]]); a program has no need of them.

A child and its pipes are values. The `Child` holds each stream until a `take_` method gives it out; from then on the caller holds it, closes it, and `wait` leaves it alone. That is why the streams come out by `take_` and aren't read from the fields: a copy taken from a field would be a second holder of the same descriptor, and `wait` couldn't know whether to close it. A stream used after `close`, or closed twice, gives `IoError.Other(9)` (EBADF), never a crash. A copy of a stream or of a `Child` names the same descriptor or process: closing or waiting through one doesn't tell the other (a second reap through a copy is `Other(10)`, ECHILD). A stream taken and dropped without `close` stays open until the program ends: a child reading an input nobody closes waits for it.

A child that writes more than a pipe holds (64 KiB on Linux) to a stream nobody reads stops until somebody does: read the error too, or wait, which drains it, or make the stream `Inherit` or `Null` (`stdout_from`, `stderr_from`): 1 MB to a `Null` output nobody reads ends at once.

## Pipelines

`a.pipe(b)` is a shell's `a | b`: a `Pipeline`, and its `output()` runs both and gives a `PipelineOutput { first: Output, second: Output }`. The pipeline's output is `second.stdout`; `first.stdout` is empty, as it went to the second. The first takes its input as `output` does; the second's is the first's output. Either's `stderr_from`, and the second's `stdout_from`, are taken (a stream that isn't a pipe is empty here). When the second ends before its input does, the first gets SIGPIPE at its next write (`Signaled(13)`), as in a shell. A child that can't be started is its `SpawnError`, the other killed and reaped; a read that fails is `Other` of its errno.

The first child's output is the second's input straight (`stdin_from_stdout`, [[MYLA-378]]): nothing goes through this process, which only reads what it collects (the second's output and both errors) as it comes. Until November 2026 the primitives couldn't give a child a descriptor as its input, and this process copied the first's output in pieces: a second child that wrote 1 MB before reading its input stalled the copy for good, which now runs through. Natively 256 MiB of `head -c` through `pipe(command("wc").arg("-c"))` takes 109 to 127 ms, as a shell's own pipe does (117 to 148 ms on the same machine; the copy took 918 to 2,187 ms there, 2026-11-09). There is no async form yet.

## Speed

Natively on x86-64, best of five ([[MYLA-340]]): reading `head -c 268435456 /dev/zero` through a `ChildStdout`, 64 KiB a `read_str`, takes 118 ms, 2,160 MB/s (a shell's `head | cat > /dev/null` 105 ms). `read`, which gives a `[uint8]`, converted each byte and read 469 MB/s; since the conversion is one copy ([[MYLA-369]]) it reads as fast as `read_str` (101 to 118 ms against 115 to 125 ms, where it took 488 to 706 ms before; 2026-11-09). Since D177 a `ChildStdout` reads into a `[uint8]` (`__read_bytes`), and `read_str` is gone: 124 to 137 ms, against 126 to 134 ms through `read_str` on the same machine ([[MYLA-399]]).

## Process primitives

A child whose input and output are streams rests on these ([[MYLA-336]]; `Command.spawn` over them is [[MYLA-340]]'s: `__spawn_piped` for every child since [[MYLA-378]], `__try_reap` and `__poll` on the pidfd for the waits, `__wait_readable` and `__wait_either` for their async forms). `run` and `Command.output` use `__run_with` (`output` with a stream `stdout_from`, `stderr_from` or `stdin_from_stdout` chose, `spawn` and `wait_with_output`), `run_async` uses `__spawn_with`, `__wait_either`, `__reap` and `__close`.

| Primitive | Does | Result |
| --- | --- | --- |
| `__spawn_piped(program: str, argv: [str], opts: [str]) -> [int]` | `program` looked for as `run` looks for it (D147), started with fork and exec (aarch64: clone) and not waited for; `opts` as `__spawn_with` takes them (a directory, an environment). Its stdin, stdout and stderr each a pipe, or as three letters in `opts[1]` say ([[MYLA-378]]): `p` a pipe, `i` this process's, `n` nothing (/dev/null), and for stdin `t` the text `opts[2]` or `d` the descriptor whose number `opts[2]` is (handed over: closed in this process once the child has it; one that isn't open is EBADF). The child's three are `dup2`ed onto 0 to 2, every other descriptor the parent made is closed on exec | `[errno, pid, in, out, err, exited]`: `in` the write end of the child's stdin, `out` and `err` the read ends of its stdout and stderr (-1 for a stream that isn't a pipe), all closed on exec, `exited` a descriptor that becomes readable when it ends (a pidfd). `[errno, 0, -1, -1, -1, -1]` when it couldn't be started (ENOENT: not there) |
| `__read(fd, n)`, `__write(fd, s)`, `__close(fd)` | read(2), write(2), close(2) on those descriptors | As for a file ([[Language/Standard-library/Fs#descriptor-and-entropy-primitives]]); a write to a child that closed its stdin is EPIPE (32), and doesn't end the program |
| `__reap(pid: int) -> int` | wait4(2), blocking | Its exit code (0 to 255), or minus the signal that ended it |
| `__try_reap(pid: int) -> int` | wait4(2) with `WNOHANG` | What `__reap` gives when the child has ended (it is reaped then); 256 while it runs, with errno 0; 256 with the errno on an error (ECHILD: not a child of this process, or reaped already) |
| `__kill(pid: int, sig: int)` | kill(2) | Nothing; the errno (ESRCH: no such process) |

On wasm32 each of them is `Unsupported`, as `run` is (D129, D132): `__spawn_piped` gives `[38, 0, -1, -1, -1, -1]`, `__try_reap` 256 and `__kill` nothing, both with the errno ENOSYS (38). `__spawn_piped` gives its errno first, `__try_reap` and `__kill` set `__io_errno()` (0 on success); the interpreter calls the same primitives of its own.
