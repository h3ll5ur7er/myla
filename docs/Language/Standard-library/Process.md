# std.process

The process itself and the programs it runs.

| Item | Meaning |
| --- | --- |
| `args() -> [str]` | Command-line arguments; `args()[0]` is the program as invoked |
| `exit(code: int32)` | Ends the process; the low 8 bits become the exit status |
| `env(name: str) -> Option<str>` | The value of the environment variable `name` the process started with (`""` included), or `None` when there is none ([[MYLA-243]]; the primitive `__getenv`, which reads the environment the process started with, or `""` with `__io_errno` 2) |
| `run(program: str, args: [str]) -> Result<Output, SpawnError>` | Runs a program, waits, captures its output. A name without a `/` is looked for in each directory of `PATH` (`/bin:/usr/bin` without one), as a shell looks; one with a `/` is that path (D147). The child inherits the environment, the directory and stdin |
| `run_async(program: str, args: [str]) -> Result<Output, SpawnError>` (async) | `run` in a task: the task waits for the child (its output read as it comes, then its end) suspended, the other tasks running (D124, [[MYLA-230]]); outside a task it blocks as `run` does. A task asked to stop stops waiting: the child is killed and reaped, `Err(SpawnError.Cancelled)` |
| `command(program)` → `Command` | Builder: `.arg(a)`, `.args([…])`, `.cwd(dir)`, `.env(name, value)`, `.env_remove(name)`, `.env_clear()`, `.stdin(text)`, `.stdin_from(how)`, then `.output()` or `.output_async()` (async, as `run_async`) (D147), `.spawn()` or `.pipe(next)` (below). A `Command` is a value: each builder method gives a new one and leaves the one it was called on as it was. Without `stdin` the child reads this process's stdin; with it, the whole text; `stdin_from(Stdio.Null)` (or `Piped`, which `output` has nobody to write) an empty one; `env_clear()` starts from an empty environment, which later `env` calls add to. On wasm32 all of it is `Unsupported` |
| `struct Output { stdout: [uint8], stderr: [uint8], status: ExitStatus }` | Output is raw bytes |
| `enum ExitStatus { Exited(int32), Signaled(int32) }` | `Eq` |
| `enum SpawnError { NotFound, PermissionDenied, Unsupported, Cancelled, InvalidInput, Other(int32) }` | Why a program couldn't be run (D129): not there, not allowed (EACCES or EPERM), no processes on this target, or the waiting task was stopped; `InvalidInput`: what no process can take, such as a `Command` given an environment variable name no variable can have (empty, with `=` or a NUL byte), which then runs nothing (D160); `Other` holds the platform's own code for anything else. `Eq`, `message()` and `Format` (D168) |

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
        input.write_str(word + "\n")
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
| `c.spawn() -> Result<Child, SpawnError>` | The command started, not waited for. Its output and error are pipes; its input is a pipe too, unless `stdin(text)` gave a text or `stdin_from` `Inherit` or `Null`. The errors are `output`'s; on wasm32 `Unsupported` |
| `c.stdin_from(how: Stdio)` | The child's input: `Stdio.Piped` (a pipe this process writes; `spawn`'s default), `Inherit` (this process's; `output`'s default) or `Null` (empty: it ends at once). It replaces a text `stdin` gave, and `stdin` replaces it |
| `child.take_stdin() -> Option<ChildStdin>`, `take_stdout() -> Option<ChildStdout>`, `take_stderr() -> Option<ChildStderr>` | The stream, given out once; `None` after that, and for an input that isn't a pipe |
| `child.wait() -> Result<ExitStatus, IoError>` | Waits (blocking) and reaps. First it closes the input the `Child` still holds, so a child that reads to the end of its input finishes, and reads the output and error it still holds to their end and drops them, so a child that writes much to a stream nobody took doesn't stop; that waits for every process that holds them, as `output` does. A second `wait` gives the same status |
| `child.wait_with_output() -> Result<Output, IoError>` | `wait`, keeping what the held output and error gave (a stream taken before is empty in it) |
| `child.try_wait() -> Result<Option<ExitStatus>, IoError>` | The status if the child has ended (it is reaped then), `None` while it runs; it doesn't wait |
| `child.kill() -> Result<(), IoError>` | SIGKILL; `wait` then gives `Signaled(9)`. A child reaped already isn't signalled (its ID may be another process's by now): `Ok` |
| `child.id() -> int32` | Its process ID |
| `await child.wait_async()`, `await child.wait_with_output_async()` | The waits in a task: the task suspended until the streams have bytes and the child ends (its pidfd), the other tasks running (D124); outside a task they block. A task asked to stop stops waiting, `Err(IoError.Cancelled)`, and leaves the child running |
| `ChildStdin` | `Write` (`write`, `write_str`, `flush`), `close()`. A write blocks while the pipe is full; one to a child that closed its input is `BrokenPipe` |
| `ChildStdout`, `ChildStderr` | `Read` (`read`, `read_str`; `""` at the end), `Pollable` (so a `Buffered` over one has the async reads), `close()` |

A child and its pipes are values. The `Child` holds each stream until a `take_` method gives it out; from then on the caller holds it, closes it, and `wait` leaves it alone. That is why the streams come out by `take_` and aren't read from the fields: a copy taken from a field would be a second holder of the same descriptor, and `wait` couldn't know whether to close it. A stream used after `close`, or closed twice, gives `IoError.Other(9)` (EBADF), never a crash. A copy of a stream or of a `Child` names the same descriptor or process: closing or waiting through one doesn't tell the other (a second reap through a copy is `Other(10)`, ECHILD). A stream taken and dropped without `close` stays open until the program ends: a child reading an input nobody closes waits for it.

The child's output and error are always pipes: the primitives can't make them this process's or nothing (`__spawn_piped` and `__spawn_with` take no descriptors), so there is no `stdout_from` or `stderr_from`. A child that writes more than a pipe holds (64 KiB on Linux) to a stream nobody reads stops until somebody does: read the error too, or wait, which drains it.

## Pipelines

`a.pipe(b)` is a shell's `a | b`: a `Pipeline`, and its `output()` runs both and gives a `PipelineOutput { first: Output, second: Output }`. The pipeline's output is `second.stdout`; `first.stdout` is empty, as it went to the second. The first takes its input as `output` does; the second's is the pipe. When the second ends before its input does, the first gets SIGPIPE at its next write (`Signaled(13)`), as in a shell. A child that can't be started is its `SpawnError`, the other killed and reaped; a read or write that fails while copying is `Other` of its errno.

The primitives can't give a child a descriptor as its input, so the first child's output doesn't reach the second straight: this process copies it. It reads 64 KiB of the first's output when there are some, writes them to the second in pieces of 16 KiB, and between two pieces reads whatever the second wrote and both children's errors, so no child stops on a full pipe nobody reads. A second child that writes more than four times what it reads, or writes without reading, could still fill its output while a piece waits for room in its input, and the copy would then wait for it; a primitive that takes the input's descriptor would end that. Natively 256 MiB of `head -c` through `pipe(command("wc").arg("-c"))` takes 250 ms (1 GB/s; a shell's own pipe 105 ms). There is no async form yet.

## Speed

Natively on x86-64, best of five ([[MYLA-340]]): reading `head -c 268435456 /dev/zero` through a `ChildStdout`, 64 KiB a `read_str`, takes 118 ms, 2,160 MB/s (a shell's `head | cat > /dev/null` 105 ms). `read`, which gives a `[uint8]` and so converts each byte, reads 469 MB/s.

## Process primitives

A child whose input and output are streams rests on these ([[MYLA-336]]; `Command.spawn` over them is [[MYLA-340]]'s: `__spawn_piped` for a piped input, `__spawn_with` for the others, `__try_reap` and `__poll` on the pidfd for the waits, `__wait_readable` and `__wait_either` for their async forms). `run` and `Command.output` use `__run_with`, `run_async` uses `__spawn_with`, `__wait_either`, `__reap` and `__close`.

| Primitive | Does | Result |
| --- | --- | --- |
| `__spawn_piped(program: str, argv: [str], opts: [str]) -> [int]` | `program` looked for as `run` looks for it (D147), started with fork and exec (aarch64: clone) and not waited for; its stdin, stdout and stderr each a pipe; `opts` as `__spawn_with` takes them (a directory, an environment), but for the input, which the pipe is instead | `[errno, pid, in, out, err, exited]`: `in` the write end of the child's stdin, `out` and `err` the read ends of its stdout and stderr, all closed on exec, `exited` a descriptor that becomes readable when it ends (a pidfd). `[errno, 0, -1, -1, -1, -1]` when it couldn't be started (ENOENT: not there) |
| `__read(fd, n)`, `__write(fd, s)`, `__close(fd)` | read(2), write(2), close(2) on those descriptors | As for a file ([[Language/Standard-library/Fs#descriptor-and-entropy-primitives]]); a write to a child that closed its stdin is EPIPE (32), and doesn't end the program |
| `__reap(pid: int) -> int` | wait4(2), blocking | Its exit code (0 to 255), or minus the signal that ended it |
| `__try_reap(pid: int) -> int` | wait4(2) with `WNOHANG` | What `__reap` gives when the child has ended (it is reaped then); 256 while it runs, with errno 0; 256 with the errno on an error (ECHILD: not a child of this process, or reaped already) |
| `__kill(pid: int, sig: int)` | kill(2) | Nothing; the errno (ESRCH: no such process) |

On wasm32 each of them is `Unsupported`, as `run` is (D129, D132): `__spawn_piped` gives `[38, 0, -1, -1, -1, -1]`, `__try_reap` 256 and `__kill` nothing, both with the errno ENOSYS (38). `__spawn_piped` gives its errno first, `__try_reap` and `__kill` set `__io_errno()` (0 on success); the interpreter calls the same primitives of its own.
