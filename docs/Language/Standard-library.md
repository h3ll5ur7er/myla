# Standard library

Myla has built-in functions known to the checker, and a small standard library written in Myla under [[src/myla/std/io.my|src/myla/std/]]. Both work without libc: natively they are raw Linux system calls ([[Architecture/Native-backend]]), in the interpreter Python I/O.

[TOC]

## Built-in functions

These names are reserved: no declaration may reuse them.

| Function | Signature | Notes |
| --- | --- | --- |
| `print(x)` | one integer, float, `char`, `bool` or `str` | Writes the value and a newline to stdout |
| `len(x)` | list, map, `str` or `StringBuilder` → `int` | Strings and builders: bytes |
| `push(xs, v)`, `pop(xs)` | list | Need a `var` place |
| `contains(m, k)`, `keys(m)`, `remove(m, k)` | map | `remove` needs a `var` place |
| `get(m, k)` | map → `Option<V>` | A prelude function, not a built-in |
| `chars(s)` | `str` → `[char]` | |
| `format(fmt, args…)` | → `str` | `fmt` is a literal; see [[Language/Collections-and-strings]] |
| `StringBuilder()`, `append(sb, s)`, `append_byte(sb, b)`, `build(sb)` | | |
| `assert(cond[, msg])`, `panic(msg)`, `unreachable()` | | See [[Language/Attributes-and-testing]] |

The low-level primitives `__write`, `__exit`, `__args`, `__read_file`, `__write_file`, `__io_errno`, `__run`, `__run_stderr`, `__run_exit_code`, `__run_signal` and `__run_errno` exist for the standard library; call the `std` functions instead.

## std.io

```myla
from std.io import println, eprintln, write

fun main() {
    println("to stdout")
    eprintln("to stderr")
    write(1, "no newline\n")
}
```

| Function | Effect |
| --- | --- |
| `write(fd: int32, s: str)` | Writes the bytes of `s` to file descriptor `fd` |
| `println(s)` | `s` and a newline to stdout |
| `eprint(s)`, `eprintln(s)` | To stderr, without / with a newline |

## std.process

| Item | Meaning |
| --- | --- |
| `args() -> [str]` | Command-line arguments; `args()[0]` is the program as invoked |
| `exit(code: int32)` | Ends the process; the low 8 bits become the exit status |
| `run(program: str, args: [str]) -> Result<Output, SpawnError>` | Runs a program found by its exact path (no `PATH` search) with the current environment, waits, captures its output |
| `command(program)` → `Command` | Builder: `.arg(a)`, `.args([…])`, `.output()` |
| `struct Output { stdout: [uint8], stderr: [uint8], status: ExitStatus }` | Output is raw bytes |
| `enum ExitStatus { Exited(int32), Signaled(int32) }` | |
| `enum SpawnError { NotFound, PermissionDenied, Other(int32) }` | `Other` carries the errno |

```myla
from std.process import command, ExitStatus

fun main() {
    match command("/bin/echo").arg("hello").output() {
        Ok(out) => {
            let code = match out.status {
                Exited(c) => c
                Signaled(sig) => 128 + sig
            }
            print(len(out.stdout))
            print(code)
        }
        Err(e) => print("could not start")
    }
}
```

## std.fs

| Function | Result |
| --- | --- |
| `read_to_string(path: str) -> Result<str, IoError>` | The whole file |
| `write_to_file(path: str, contents: str) -> Result<int32, IoError>` | Creates or truncates (mode 0644); `Ok` holds the number of bytes |
| `enum IoError { NotFound, PermissionDenied, Other(int32) }` | Mapped from the OS errno |

The file's bytes become the string unchanged; nothing checks that they are valid UTF-8 ([[MYLA-12]]).
