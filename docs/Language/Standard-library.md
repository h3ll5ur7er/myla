# Standard library

Myla has built-in functions known to the checker, and a small standard library written in Myla under [[lib/std/io.my|lib/std/]]. Both work without libc: natively they rest on the platform layer `std.platform`, raw Linux system calls on x86-64 and aarch64 and WASI's imports on wasm32 ([[Architecture/Native-backend]]), and so does the interpreter, which is a native program itself. What a target lacks shows as an error of its own, `Unsupported` (D129, D132): on wasm32 `run` and `spawn` fail with `SpawnError.Unsupported`, as there are no processes; how targets differ is to be specified ([[MYLA-266]]).

[TOC]

## Built-in functions

These names are reserved: no declaration may reuse them.

| Function | Signature | Notes |
| --- | --- | --- |
| `print(x)` | one integer, float, `char`, `bool` or `str` | Writes the value and a newline to stdout |
| `len(x)` | list, map, `str` or `StringBuilder` → `int` | Strings and builders: bytes |
| `push(xs, v)`, `pop(xs)` | list | Need a `var` place |
| `contains(m, k)`, `keys(m)`, `remove(m, k)` | map | `remove` needs a `var` place |
| `get(m, k)` | map → `Option<V>` | The one entry here that is a prelude function, not a built-in: an ordinary generic function every program sees (a declaration of another `get` is a duplicate), so its errors read like any call's |
| `chars(s)` | `str` → `[char]` | |
| `format(fmt, args…)` | → `str` | `fmt` is a literal; see [[Language/Collections-and-strings]] |
| `StringBuilder()`, `append(sb, s)`, `append(sb, s, start, end)`, `append_byte(sb, b)`, `build(sb)` | | The four-argument `append` adds the bytes `s[start..end]` ([[Language/Collections-and-strings]]) |
| `assert(cond[, msg])`, `panic(msg)`, `unreachable()` | | See [[Language/Attributes-and-testing]] |

The low-level primitives `__write`, `__read`, `__poll`, `__exit`, `__args`, `__read_file`, `__write_file`, `__list_dir`, `__mkdir`, `__stat`, `__getcwd`, `__getenv`, `__sqrt`, `__f64_bits`, `__f64_from_bits`, `__unlink`, `__rmdir`, `__rename`, `__io_errno`, `__run`, `__run_stderr`, `__run_exit_code`, `__run_signal`, `__run_errno` and `__task_cancelled`, and the primitives behind `std.time`, `std.task`'s timers and `std.process.spawn` (`__clock_ns`, `__sleep`, `__spawn`, …) exist for the standard library; call the `std` functions instead. A call of one from a program outside the standard library compiles, with a warning (D100, [[MYLA-186]]): it is for code that knows what it does, such as a new std function in the making.

## std.io

```myla
from std.io import println, eprintln, write

fun main() {
    println("to stdout")
    eprintln("to stderr")
    write(1, "no newline\n")
}
// output:
// to stdout
// no newline
```

| Function | Effect |
| --- | --- |
| `write(fd: int32, s: str)` | Writes the bytes of `s` to file descriptor `fd` |
| `println(s)` | `s` and a newline to stdout |
| `eprint(s)`, `eprintln(s)` | To stderr, without / with a newline |

Output isn't buffered: what a program wrote is out before it waits for input.

### Reading

Reading goes through a buffered `Reader` ([[MYLA-78]]). Keep it in a `var`, or in a field of a struct whose `var self` methods read from it (Myla has no references, so a function can't take a reader to read from). A read blocks until there is input or the input ends; the bytes come back verbatim, and an error is the errno as an `IoError` from `std.fs`.

| Item | Result |
| --- | --- |
| `stdin() -> Reader` | A reader of the standard input |
| `reader(fd: int32) -> Reader` | A reader of file descriptor `fd` |
| `r.read_line() -> Result<Option<str>, IoError>` | The next line without its `"\n"` (a `"\r"` before it stays); a last line without `"\n"` counts; `None` at the end |
| `r.read_exact(n: int32) -> Result<Option<str>, IoError>` | Exactly the next `n` bytes (`""` for `n <= 0`); `None` if the input ends first (those bytes stay unread) |
| `r.read_to_end() -> Result<str, IoError>` | The rest of the input (`""` once it has ended) |
| `r.ready(timeout_ms: int32) -> bool` | Whether a read won't block: bytes are buffered, or within `timeout_ms` milliseconds input arrives, the input ends or reading fails (0: don't wait; negative: wait as long as it takes) |

```myla
from std.io import stdin, println

fun main() {
    var input = stdin()
    var n = 0
    while true {
        match input.read_line() {
            Ok(Some(line)) => {
                n = n + 1
                println(format("{}: {}", n, line))
            },
            Ok(None) => { break },
            Err(e) => { break },
        }
    }
}
```

A protocol that frames messages with a `Content-Length` header reads the header lines with `read_line` and the body with `read_exact`; `tests/burn/test_stdin.py` has an example.

In a task, each read has an async version that waits for the input with the task suspended, so the other tasks run meanwhile (D124, [[MYLA-230]]): `await r.read_line_async()`, `await r.read_exact_async(n)`, `await r.read_to_end_async()`, `await r.fill_async(want)`. They give what the blocking reads give; outside a task they block as those do. A task asked to stop (`task.cancel`, a `task.timeout` that ran out) stops waiting at once and gets `Err(IoError.Cancelled)` (ECANCELED). Natively the executor's poller watches the descriptor (a regular file, which it can't watch, is always ready); the interpreter looks at the waiting tasks' descriptors before each turn.

## std.process

| Item | Meaning |
| --- | --- |
| `args() -> [str]` | Command-line arguments; `args()[0]` is the program as invoked |
| `exit(code: int32)` | Ends the process; the low 8 bits become the exit status |
| `env(name: str) -> Option<str>` | The value of the environment variable `name` the process started with (`""` included), or `None` when there is none ([[MYLA-243]]; the primitive `__getenv`, which reads the environment the process started with, or `""` with `__io_errno` 2) |
| `run(program: str, args: [str]) -> Result<Output, SpawnError>` | Runs a program found by its exact path (no `PATH` search) with the current environment, waits, captures its output |
| `run_async(program: str, args: [str]) -> Result<Output, SpawnError>` (async) | `run` in a task: the task waits for the child (its output read as it comes, then its end) suspended, the other tasks running (D124, [[MYLA-230]]); outside a task it blocks as `run` does. A task asked to stop stops waiting: the child is killed and reaped, `Err(SpawnError.Cancelled)` |
| `command(program)` → `Command` | Builder: `.arg(a)`, `.args([…])`, `.output()`, `.output_async()` (async, as `run_async`) |
| `struct Output { stdout: [uint8], stderr: [uint8], status: ExitStatus }` | Output is raw bytes |
| `enum ExitStatus { Exited(int32), Signaled(int32) }` | |
| `enum SpawnError { NotFound, PermissionDenied, Unsupported, Cancelled, Other(int32) }` | Why a program couldn't be run (D129): not there, not allowed, no processes on this target, or the waiting task was stopped; `Other` holds the platform's own code for anything else |

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

## std.fs

| Function | Result |
| --- | --- |
| `read_to_string(path: str) -> Result<str, IoError>` | The whole file |
| `write_to_file(path: str, contents: str) -> Result<int32, IoError>` | Creates or truncates (mode 0644); `Ok` holds the number of bytes |
| `list_dir(path: str) -> Result<[str], IoError>` | The names of the directory's entries, without `.` and `..`, sorted by their bytes |
| `make_dir(path: str) -> Result<int32, IoError>` | Makes one directory (mode 0755 less the umask); its parent must exist; `Ok` holds 0 |
| `make_dir_all(path: str) -> Result<int32, IoError>` | Makes the directory and the parents it lacks, like `mkdir -p`; an existing directory is fine; `Ok` holds 0 |
| `exists(path: str) -> bool` | Whether the path names anything (symbolic links followed, so a dangling one doesn't count) |
| `is_dir(path: str) -> bool`, `is_file(path: str) -> bool` | Whether it names a directory, a regular file (links followed) |
| `current_dir() -> Result<str, IoError>` | The working directory: an absolute path without symbolic links, as the kernel gives it; a directory that was removed is `NotFound` ([[MYLA-98]]) |
| `remove_file(path: str) -> Result<int32, IoError>` | Removes a file, or a symbolic link itself; a directory is `IsADirectory`; `Ok` holds 0 ([[MYLA-96]]) |
| `remove_dir(path: str) -> Result<int32, IoError>` | Removes an empty directory; one that isn't is `NotEmpty`; `Ok` holds 0 |
| `remove_dir_all(path: str) -> Result<int32, IoError>` | Removes the path and, for a directory, everything in it, like `rm -r`; symbolic links are removed, not followed; `Ok` holds 0 |
| `rename(from_path: str, to: str) -> Result<int32, IoError>` | Renames or moves within one file system, replacing a file at `to`; `Ok` holds 0 |
| `enum IoError { NotFound, PermissionDenied, AlreadyExists, NotADirectory, IsADirectory, NotEmpty, Interrupted, Cancelled, Unsupported, Other(int32) }` | Why an operation failed, the same causes on every target (D129); `Cancelled`: a task's read stopped by `task.cancel` or a timeout (D96); `Unsupported`: the target can't do it; `Other` holds the platform's own code for anything else, whose numbers aren't portable |

The file's bytes become the string unchanged, even when they aren't valid UTF-8: strings work on bytes, and `chars` gives U+FFFD for the invalid ones ([[Language/Collections-and-strings]], [[MYLA-12]]).

`from_errno(code: int32) -> IoError` turns the platform layer's code (Linux's numbers on every target so far; wasm32's maps WASI's onto them) into its cause; `std.io` and `std.process` use it too.

```myla
from std.fs import list_dir, make_dir_all, is_dir, IoError

fun main() {
    match make_dir_all("build/out") {
        Ok(n) => {},
        Err(e) => { print("could not make build/out") },
    }
    match list_dir("src") {
        Ok(names) => {
            for n in names {
                if is_dir("src/" + n) { print(n + "/") } else { print(n) }
            }
        },
        Err(e) => { print("no src directory") },
    }
}
// output:
// no src directory
```

### Directory primitives

The directory functions rest on seven primitives (D64's pattern: a small system call per implementation, the rest shared Myla code; [[MYLA-88]], [[MYLA-98]], [[MYLA-96]]):

| Primitive | Does | Result |
| --- | --- | --- |
| `__list_dir(path: str) -> str` | open(2) with `O_DIRECTORY`, getdents64(2) until the end, close(2) | Every name the directory lists, each followed by a NUL byte, in the file system's order (`.` and `..` may be among them); `""` on an error |
| `__mkdir(path: str, mode: int32)` | mkdir(2) | Nothing |
| `__stat(path: str) -> int32` | stat(2) | `st_mode` (file type and permission bits), or -1 on an error |
| `__getcwd() -> str` | getcwd(2) into a 4 KB buffer | The working directory, or `""` on an error (ENOENT for a removed directory, ERANGE for a path longer than the buffer) |
| `__unlink(path: str)` | unlink(2) | Nothing (a directory is EISDIR, which `remove_dir_all` uses to tell one without following links) |
| `__rmdir(path: str)` | rmdir(2) | Nothing |
| `__rename(from: str, to: str)` | rename(2) | Nothing |

The system calls named are x86-64 Linux's; aarch64 uses the generic `*at` forms (`openat`, `mkdirat`, `unlinkat`, `renameat2`), wasm32 WASI's (`path_open`, `fd_readdir`, …), translated into the same results. Each sets the errno that `__io_errno()` reads (0 on success), a Linux number on every target (WASI's are mapped onto them). A name can't hold a NUL byte, so NUL separates them. `list_dir` drops `.` and `..` and sorts the names by their bytes, so every file system gives the same list (and the Python interpreter, with `os.listdir`, gave it too).

## std.num

Numbers from text and back ([[MYLA-79]]). The conversions are exact, computed with big integers, so every implementation gives the same result; the self-hosted compiler converts its float literals with the same code.

| Function | Result |
| --- | --- |
| `parse_int(s: str) -> Option<int64>` | A decimal integer with an optional `-`; `None` for anything else or out of range |
| `parse_float(s: str) -> Option<float64>` | The nearest double to `-? digits (. digits)? ([eE] [+-]? digits)?`; too large is infinite |
| `format_float(x: float64) -> str` | The shortest decimal that reads back as `x`, as Python's `repr` writes it: `1.0`, `0.1`, `1e+16`, `1.5e-07`, `-0.0`, `nan`, `inf` |
| `pow2(k: int32) -> float64` | 2^k exactly, for -1022 <= k <= 1023 |
| `f64_literal_bits(text) -> uint64`, `f32_round_bits(bits) -> uint64`, `float_from_bits(bits) -> float64` | The bit-level steps (for the compiler) |

`format("{}", x)` writes a float with up to 17 significant digits (`0.10000000000000001`); `format_float` is the short form.

## std.math

Mathematical functions on `float64` ([[MYLA-248]]). `sqrt` is the processor's correctly rounded square root. The rest is written in Myla after fdlibm (the reference implementation behind most C math libraries), so the interpreter and native code give bit-identical results. `tests/burn/test_math.py` holds each to its stated error against the C library, NaN, the infinities and signed zeros included.

```myla
from std.math import sqrt, sin, atan2, pow, PI

fun main() {
    print(sqrt(2.0))
    print(sin(PI / 2.0))
    print(atan2(1.0, 1.0) * 4.0 == PI)
    print(pow(2.0, 10.0))
}
// output:
// 1.4142135623730951
// 1
// true
// 1024
```

| Function | Result |
| --- | --- |
| `PI`, `TAU`, `E`, `LN2`, `LN10`, `SQRT2` | The constants, rounded to `float64` |
| `sqrt(x)`, `hypot(x, y)` | The square root (correctly rounded); √(x² + y²) without overflow on the way (within 1 ulp) |
| `exp(x)`, `ln(x)`, `log2(x)`, `log10(x)`, `pow(x, y)` | Within 1 ulp; `log2` is exact for powers of two, `log10` for powers of ten up to 10²², `ln(0)` is `-inf`, `ln(-1)` NaN |
| `sin(x)`, `cos(x)`, `atan(x)` | Within 1 ulp, for every finite argument: arguments above 2^20·π/2 are reduced by Payne and Hanek's method |
| `tan(x)`, `asin(x)`, `acos(x)`, `atan2(y, x)` | Within 4 ulp |
| `abs(x)`, `copysign(x, s)`, `trunc(x)`, `floor(x)`, `ceil(x)`, `round(x)` | Exact; `round` takes halves away from zero, zeros keep their sign; `copysign` reads a NaN `s` as positive (D128) |
| `min(a, b)`, `max(a, b)` | The other argument when one is NaN |
| `ldexp(x, k)` | x·2^k |
| `is_nan(x)`, `is_infinite(x)`, `is_finite(x)`, `infinity()`, `nan()` | |
| `to_bits(x) -> uint64`, `from_bits(b) -> float64` | The IEEE 754 bits of a float and back; every NaN gives `0x7FF8000000000000`, so its sign and payload, which differ between processors, can't be seen (D128) |

## std.task

Child tasks whose number is known only at run time (D89, [[Language/Concurrency]]).

| Function | Result |
| --- | --- |
| `all<T>(fs: [async () -> T]) -> [T]` (async) | Runs each function of `fs` as a child task, all at once, and gives their results in the order of `fs` |
| `cancel(child)` | Asks the child task of the `async let` named `child` to stop (D96): sets a flag it and its children see, and goes on; the compiler takes the call itself |
| `cancelled() -> bool` | True when the running task, or a task above it, was asked to stop |
| `yield()` (async) | `await task.yield()` gives the other ready tasks a turn and goes on after them; a task stopped by a failure elsewhere stops there (D97, D107, [[MYLA-228]]) |
| `timeout<T>(ms: int, f: async () -> T) -> Option<T>` (async) | Runs `f` as a child task: `Some` of its result, or `None` when `ms` milliseconds passed first, the child then cancelled (its sleeps end) and awaited (D124) |
| `sleep(ms: int)` (async) | `await task.sleep(ms)`: the running task asleep for at least `ms` milliseconds (none for `ms <= 0`), the others running meanwhile (D124, [[MYLA-230]]); tasks whose time comes at once go on earliest first |

`all` is written in Myla with `async let` alone, halving the list until one function is left, so the tasks nest about log2(len(fs)) deep. Cancelling is cooperative: the child decides where to stop ([[Language/Concurrency]]).

## std.time

The clock (D124, [[MYLA-230]]): monotonic, so the difference of two readings is the time that passed; its zero is some fixed point in the past, not a date.

| Function | Result |
| --- | --- |
| `now_ns() -> int64` | The clock in nanoseconds |
| `now_ms() -> int64` | The clock in milliseconds |

The interpreter reads the same clock; with `MYLA_TIME=virtual` it reads one that moves only when no task is ready, to the next sleeper's deadline, so tests of timing logic take no time and order exactly.

## std.json

JSON values, parsing and writing ([[MYLA-79]]), following Python's `json` module: the burn tests compare them on thousands of random and broken texts.

```myla
from std.json import Json, parse, to_string, field

fun main() {
    match parse("{\"id\": 1, \"method\": \"initialize\"}") {
        Ok(msg) => {
            match field(msg, "method") {
                Some(Json.Str(m)) => { print(m) },
                _ => { print("no method") },
            }
            print(to_string(Json.Array([Json.Int(1), Json.Null])))
        },
        Err(e) => { print(format("{}:{}: {}", e.line, e.col, e.msg)) },
    }
}
// output:
// initialize
// [1,null]
```

| Item | Meaning |
| --- | --- |
| `enum Json { Null, Bool(bool), Int(int64), Float(float64), Str(str), Array([Json]), Object([(str, Json)]) }` | A number without fraction or exponent that fits in int64 is an `Int`, any other a `Float`; an object keeps its members in order, duplicates included |
| `parse(text: str) -> Result<Json, JsonError>` | One value, with whitespace around it allowed |
| `struct JsonError { msg: str, line: int32, col: int32 }` | Python 3.13's messages and positions (the column counts characters) |
| `to_string(j: Json) -> str` | Compact text, as `json.dumps(j, ensure_ascii=False, separators=(",", ":"))` writes it: floats in their shortest form, control characters escaped, other characters as they are |
| `field(j: Json, key: str) -> Option<Json>` | An object's member (the last one with that key, as Python keeps it) |

Like Python, `NaN`, `Infinity` and `-Infinity` are read and written. Unlike Python, a `\u` escape of a lone surrogate is an error, since a Myla string holds UTF-8, and nesting is limited to 200 levels (what every implementation's stack takes: the interpreters run the parser's recursion on their own).

## std.toml

The TOML subset of project manifests and lock files (D73, [[MYLA-89]]): tables and dotted headers, bare and quoted keys, basic and literal strings, decimal `int64` integers, booleans, arrays of strings, inline tables. The grammar is on [[Architecture/Project-tool]]. Every document it accepts means the same in TOML 1.0; the burn tests compare it with Python's `tomllib` on thousands of random and broken documents.

```myla
from std.toml import parse, field, Toml, TomlError

fun main() {
    match parse("[package]\nname = \"geo\"\nauthors = [\"Ada\"]\n") {
        Ok(doc) => {
            match field(doc, "package") {
                Some(pkg) => {
                    match field(pkg, "name") {
                        Some(Toml.Str(name)) => { print(name) },
                        _ => { print("no name") },
                    }
                },
                None => { print("no [package]") },
            }
        },
        Err(e) => { print(format("{}:{}: {}", e.line, e.col, e.msg)) },
    }
}
// output:
// geo
```

| Item | Meaning |
| --- | --- |
| `enum Toml { Str(str), Int(int64), Bool(bool), Array([Toml]), Table([(str, Toml)]) }` | A table keeps its keys in the order they were defined; the document is a `Table` |
| `parse(text: str) -> Result<Toml, TomlError>` | The document's table |
| `struct TomlError { msg: str, line: int32, col: int32 }` | Line and column count from 1, the column in characters |
| `field(t: Toml, key: str) -> Option<Toml>` | A table's value for `key`; `None` for a missing key or a value that isn't a table |
| `parse_doc(text: str) -> Result<TomlDoc, TomlError>` | The document's table (`root`) with where each key path was defined, so a program that checks a document can point at what is wrong ([[MYLA-93]]) |
| `key_pos(d: TomlDoc, path: [str]) -> Option<TomlPos>` | Where the key of the key path is (`["dependencies", "geo", "path"]`, also inside an inline table); for a table, its header (the one that opened it, else the first that implied it) |
| `value_pos(d: TomlDoc, path: [str]) -> Option<TomlPos>` | Where its value is (for a table opened by a header, the header) |
| `struct TomlPos { line: int32, col: int32, end_line: int32, end_col: int32 }` | From `line`:`col` to just before `end_line`:`end_col`, counted like `TomlError`'s position |

What TOML has beyond the subset is an error naming it: "floats are not supported", "dates and times are not supported", "hexadecimal, octal and binary integers are not supported", "multi-line strings are not supported", "dotted keys are not supported", "arrays of tables are not supported", "arrays may only hold strings". An integer beyond `int64` is "integer out of range", as TOML asks of a parser that can't hold it (`tomllib` reads it as a big integer). Other errors are TOML errors, such as `'a' is defined twice`, `table 'a' is defined twice` and `'a' is not a table that can be extended`.

## std.rt

Not for programs: the runtime written in Myla ([[MYLA-162]], D117), which a native build loads with every program and compiles where the code generator calls it in place of the assembly routine it replaces. So far string concatenation and equality (`str_concat`, `str_eq`) and the file system behind `std.fs` (`read_file`, `write_file`, `list_dir`, `stat`, `mkdir`, `unlink`, `rmdir`, `rename`, `getcwd`, on Linux's system calls) `std.process.env`'s `getenv` `std.io`'s reader (`read`, `poll`), `std.process.args`'s `args`, integers as text (`int_to_str`, `uint_to_str`, behind `format`), a string's characters (`str_chars`, behind `chars()`), a map's lookup (`map_lookup`, behind `m[k]` and `contains`), a string builder's append (`sb_append`), a map's keys (`map_keys`), `print` of every scalar but a float and `std.io.write` (`print_str`, `print_int`, …, `write`; a line and its newline in one `writev`, so the lines of tasks on other workers don't interleave) and the process runner behind `std.process.run` (`run`: fork, exec, both outputs read as they come through poll, wait). It works on raw memory through primitives the interpreter doesn't have (`__load8`, `__load32`, `__load64`, `__store8`, `__store32`, `__store64`, a list's cell and back (`__list_addr`, `__list_of`, the list type from the context), `__alloc`, `__free`, `__addr_of`, `__str_of`, and the bulk `__copy_bytes` and `__equal_bytes`, which each backend does natively; the atomics `__cas64`, `__xchg64` and `__fetch_add64`, full barriers, and `__load_acq64` and `__store_rel64`, a load with acquire and a store with release ordering: `ldar` and `stlr` on aarch64, plain moves on x86-64, whose ordering gives both, MYLA-267), makes system calls through `__syscall(n, a, b, c)` and records the errno `std.io` reports with `__set_io_errno` reads the arguments and the environment through `__argv()` and `__environ()` and leaves a run's stderr and status with `__set_run_stderr` and `__set_run_status`; addresses are `int64`. A standard library root without `std/rt.my` gets the copy the tools carry: the assembly routines it replaced are gone from the code generator. Under it, `std.platform` is the platform layer, one module per target ([[lib/std/platform.my]] for x86-64 Linux, [[lib/std/platform_aarch64.my]], [[lib/std/platform_wasm.my]]; the loader takes the target's for `std/platform.my`): every system call std.rt makes, the numbers, flags and record layouts with them, and the process runner (fork, exec, poll, wait), behind functions that give a result or a negative errno (`open_read`, `read`, `write_line`, `mode_of`, `dir_read`, `run`, `cpus_allowed`, `park`, `unpark_one`, `exit`, …). A port to another system gives that module again; std.rt stays as it is. Its interface is Linux's (negative errnos, `getdents64` records, `st_mode` bits), which wasm32's module imitates; [[MYLA-265]] is to make it Myla's.

