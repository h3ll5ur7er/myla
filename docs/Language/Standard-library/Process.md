# std.process

The process itself and the programs it runs.

| Item | Meaning |
| --- | --- |
| `args() -> [str]` | Command-line arguments; `args()[0]` is the program as invoked |
| `exit(code: int32)` | Ends the process; the low 8 bits become the exit status |
| `env(name: str) -> Option<str>` | The value of the environment variable `name` the process started with (`""` included), or `None` when there is none ([[MYLA-243]]; the primitive `__getenv`, which reads the environment the process started with, or `""` with `__io_errno` 2) |
| `run(program: str, args: [str]) -> Result<Output, SpawnError>` | Runs a program, waits, captures its output. A name without a `/` is looked for in each directory of `PATH` (`/bin:/usr/bin` without one), as a shell looks; one with a `/` is that path (D147). The child inherits the environment, the directory and stdin |
| `run_async(program: str, args: [str]) -> Result<Output, SpawnError>` (async) | `run` in a task: the task waits for the child (its output read as it comes, then its end) suspended, the other tasks running (D124, [[MYLA-230]]); outside a task it blocks as `run` does. A task asked to stop stops waiting: the child is killed and reaped, `Err(SpawnError.Cancelled)` |
| `command(program)` → `Command` | Builder: `.arg(a)`, `.args([…])`, `.cwd(dir)`, `.env(name, value)`, `.env_remove(name)`, `.env_clear()`, `.stdin(text)`, then `.output()` or `.output_async()` (async, as `run_async`) (D147). A `Command` is a value: each builder method gives a new one and leaves the one it was called on as it was. Without `stdin` the child reads this process's stdin; with it, the whole text; `env_clear()` starts from an empty environment, which later `env` calls add to. On wasm32 all of it is `Unsupported` |
| `struct Output { stdout: [uint8], stderr: [uint8], status: ExitStatus }` | Output is raw bytes |
| `enum ExitStatus { Exited(int32), Signaled(int32) }` | |
| `enum SpawnError { NotFound, PermissionDenied, Unsupported, Cancelled, InvalidInput, Other(int32) }` | Why a program couldn't be run (D129): not there, not allowed (EACCES or EPERM), no processes on this target, or the waiting task was stopped; `InvalidInput`: what no process can take, such as a `Command` given an environment variable name no variable can have (empty, with `=` or a NUL byte), which then runs nothing (D160); `Other` holds the platform's own code for anything else |

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

## Process primitives

A child whose input and output are streams rests on these ([[MYLA-336]]; `Command.spawn` over them is [[MYLA-340]]'s). `run` and `Command.output` use `__run_with`, `run_async` uses `__spawn_with`, `__wait_either`, `__reap` and `__close`.

| Primitive | Does | Result |
| --- | --- | --- |
| `__spawn_piped(program: str, argv: [str], opts: [str]) -> [int]` | `program` looked for as `run` looks for it (D147), started with fork and exec (aarch64: clone) and not waited for; its stdin, stdout and stderr each a pipe; `opts` as `__spawn_with` takes them (a directory, an environment), but for the input, which the pipe is instead | `[errno, pid, in, out, err, exited]`: `in` the write end of the child's stdin, `out` and `err` the read ends of its stdout and stderr, all closed on exec, `exited` a descriptor that becomes readable when it ends (a pidfd). `[errno, 0, -1, -1, -1, -1]` when it couldn't be started (ENOENT: not there) |
| `__read(fd, n)`, `__write(fd, s)`, `__close(fd)` | read(2), write(2), close(2) on those descriptors | As for a file ([[Language/Standard-library/Fs#descriptor-and-entropy-primitives]]); a write to a child that closed its stdin is EPIPE (32), and doesn't end the program |
| `__reap(pid: int) -> int` | wait4(2), blocking | Its exit code (0 to 255), or minus the signal that ended it |
| `__try_reap(pid: int) -> int` | wait4(2) with `WNOHANG` | What `__reap` gives when the child has ended (it is reaped then); 256 while it runs, with errno 0; 256 with the errno on an error (ECHILD: not a child of this process, or reaped already) |
| `__kill(pid: int, sig: int)` | kill(2) | Nothing; the errno (ESRCH: no such process) |

On wasm32 each of them is `Unsupported`, as `run` is (D129, D132): `__spawn_piped` gives `[38, 0, -1, -1, -1, -1]`, `__try_reap` 256 and `__kill` nothing, both with the errno ENOSYS (38). `__spawn_piped` gives its errno first, `__try_reap` and `__kill` set `__io_errno()` (0 on success); the interpreter calls the same primitives of its own.
