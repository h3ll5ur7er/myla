# std.io

Writing, buffered reading ([[MYLA-78]]) and streams ([[MYLA-338]]).

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
| `write(fd: int32, s: str) -> Result<(), IoError>` | Writes the bytes of `s` to file descriptor `fd`, all of them, or the error that stopped it (D146); a pipe nobody reads any more is `BrokenPipe` |
| `println(s)` | `s` and a newline to stdout |
| `eprint(s)`, `eprintln(s)` | To stderr, without / with a newline |

Output isn't buffered: what a program wrote is out before it waits for input.

A write to the standard output or error whose pipe nobody reads any more (`myla run prog.my | head -1`) ends the program quietly, as Unix tools stop: natively by SIGPIPE, on wasm32 with the exit code 141 a shell shows for it (D146). Any other error of `print`, `println`, `eprint` and `eprintln`, which have no result (a full disk: `prog > /dev/full`), ends the program with `runtime error: write failed: <cause>` and status 1 (D153); `write` gives it to the program. A write to any other descriptor gives the error to the program instead: the runtime ignores SIGPIPE, and gives a child it starts the default back.

## Reading

Reading goes through a buffered `Reader` ([[MYLA-78]]), a `Buffered` over the descriptor (below). Keep it in a `var`, or in a field of a struct whose `var self` methods read from it (Myla has no references, so a function can't take a reader to read from). A read blocks until there is input or the input ends; the bytes come back verbatim, and an error is the errno as an `IoError` from `std.fs`.

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

## Streams

A stream is a value, as everything in Myla is ([[MYLA-338]]). Keep it in a `var` and use it through its methods, which take `var self`. An adapter owns the stream it wraps: `buffered(r)` takes `r` and holds it. There are no trait objects, so a function over any stream is generic, and it takes the stream by value.

```myla
from std.io import from_str, buffered, buffered_writer, memory_stream, copy, SeekFrom
from std.fs import IoError

// Two writes gathered in a buffer, then the bytes they made.
fun greeting() -> Result<str, IoError> {
    var w = buffered_writer(memory_stream())
    w.write_str("hello, ")?
    w.write_str("world")?
    let m = w.into_inner()?
    return Ok(m.text())
}

// The last `n` bytes of `text`, by a seek and a copy.
fun last(text: str, n: int64) -> Result<str, IoError> {
    var m = from_str(text)
    m.seek(SeekFrom.End(-n))?
    let out = copy(m, memory_stream())?
    return Ok(out.text())
}

fun main() {
    var r = buffered(from_str("fig 3\npear 5\nplum"))
    while true {
        match r.read_line() {
            Ok(Some(line)) => print(f"line: {line}")
            _ => { break }
        }
    }
    print(greeting().unwrap_or("failed"))
    print(last("0123456789", 3).unwrap_or("failed"))
}
// output:
// line: fig 3
// line: pear 5
// line: plum
// hello, world
// 789
```

### The traits

| Trait | Methods |
| --- | --- |
| `Read` | `read(var self, n: int) -> Result<[uint8], IoError>`: up to `n` bytes from the cursor on, `[]` at the end (and for `n <= 0`); fewer than `n` isn't the end. `read_str(var self, n: int) -> Result<str, IoError>`: the same as a `str`, `""` at the end |
| `Write` | `write(var self, b: [uint8]) -> Result<int, IoError>`: all of `b`, or the error that stopped it; `b.len()`. `write_str(var self, s: str) -> Result<int, IoError>`: the bytes of `s`. `flush(var self) -> Result<(), IoError>`: whatever is buffered passed on |
| `Seek` | `seek(var self, pos: SeekFrom) -> Result<int64, IoError>`: the cursor moved to `SeekFrom.Start(k)`, `Current(k)` or `End(k)`; the new offset from the start. Before the start is `InvalidInput`; past the end is allowed |
| `Pollable` | `descriptor(self) -> int32`: the descriptor a task can wait for. A `Buffered` over a `Pollable` stream has `ready` and the async reads |

Each of `Read` and `Write` has a method for `[uint8]` and one for `str`. Strings are bytes (D164), and the two kinds hold the same bytes; when the traits were made one became the other only byte by byte, and `read_str` and `write_str` spared text that cost. Since [[MYLA-369]] `std.bytes`'s `from_str` and `to_str` convert in one allocation and one copy (the primitives `__str_to_bytes` and `__bytes_to_str`), and a `[uint8]` costs about what a `str` does (the measurements below). A descriptor reads and writes a `str`, a memory stream holds a `[uint8]`, so each stream gives both the cheap way: a `Buffered` reads text with `read_str`, and text from a descriptor isn't converted at all. A stream that has only one kind gives the other by converting it (the example below).

### Streams of this module

| Item | What it is |
| --- | --- |
| `fd_stream(fd: int32) -> FdStream` | A descriptor, unbuffered: each read and write is a system call. `Read`, `Write`, `Seek` (a pipe can't: `Other(29)`, ESPIPE), `Pollable`. A write to a closed pipe is `BrokenPipe`, but on the standard output or error, where it ends the program quietly (D146) |
| `memory_stream() -> MemoryStream`, `from_bytes(b: [uint8])`, `from_str(s: str)` | Bytes in memory and a cursor at the start. `Read`, `Write` (over the bytes at the cursor, and on past the end; a gap a seek past the end left is zeros), `Seek` |
| `m.bytes() -> [uint8]`, `m.text() -> str`, `m.position() -> int64` | All its bytes, wherever the cursor is; as text; the cursor |
| `buffered(r: R) -> Buffered<R>` | A buffer in front of `r`: `read_line`, `read_exact`, `read_to_end` and `fill` as `Reader` has them (`Reader` is `Buffered<FdStream>`), `into_inner()` (the stream, without the bytes still buffered). `Read`; `Seek` if `r` can (the buffer dropped; `Current` counts from the next byte a read gives); `Pollable`, `ready` and the async reads if `r` is `Pollable` |
| `buffered_writer(w: W) -> BufferedWriter<W>`, `buffered_writer_with(w, capacity: int32)` | A buffer in front of `w`, 8 KiB or `capacity` bytes: writes are gathered and passed on when it is full, on `flush` and on `into_inner() -> Result<W, IoError>` (flushed). `Write`; `Seek` if `w` can (after the buffer is passed on). Nothing flushes it when the program ends |

### Any stream

| Function | Result |
| --- | --- |
| `read_all<R: Read>(r: R) -> Result<[uint8], IoError>` | Everything `r` gives up to its end |
| `copy<R: Read, W: Write>(r: R, w: W) -> Result<W, IoError>` | Everything `r` gives up to its end written to `w`, 64 KiB at a time, which is flushed and given back |

They take the streams by value, so the caller's `var` doesn't move: a memory stream read by `read_all` is where it was. A descriptor's offset, which the platform keeps, does move. `copy` gives the writer back, which is the way to the bytes of a memory stream it wrote, or to a `BufferedWriter`'s stream.

### A stream of your own

A type is a stream when it implements the traits. `Read` takes both methods; the one it hasn't got natively converts the other:

```myla
from std.io import Read, buffered, read_all
from std.fs import IoError
import std.bytes as bytes

// `left` more copies of one byte.
struct Repeat {
    byte: uint8,
    left: int,
}

impl Read for Repeat {
    fun read(var self, n: int) -> Result<[uint8], IoError> {
        var out: [uint8] = []
        while out.len() < n && self.left > 0 {
            out.push(self.byte)
            self.left -= 1
        }
        return Ok(out)
    }

    fun read_str(var self, n: int) -> Result<str, IoError> {
        let b = self.read(n)?
        return Ok(bytes.to_str(b))
    }
}

fun main() {
    match read_all(Repeat { byte: 'z', left: 5000 }) {
        Ok(b) => print(b.len())
        Err(_) => print("failed")
    }
    var r = buffered(Repeat { byte: 'a', left: 3 })
    match r.read_exact(2) {
        Ok(Some(s)) => print(s)
        _ => print("too short")
    }
}
// output:
// 5000
// aa
```

An adapter is a generic struct, `struct Buffered<R>` (a struct's parameters can't have bounds), with `impl<R: Read> Buffered<R>`, and `impl<R: Read> Read for Buffered<R>` so that adapters stack. Another impl block may ask for more, `impl<R: Read + Pollable> Buffered<R>`, and its methods are there only for such an `R`. `Buffered` keeps its stream as the one element of a list and takes it out for each read: a stream that is a plain field would share its bytes with the copy a read works on, and a read that changes them would copy them all each time.

### Speed

Natively on x86-64, 50 MB of lines of up to 120 bytes, best of three ([[MYLA-338]]):

| What | Time |
| --- | --- |
| `stdin().read_line()` over all of it | 75 ms (96 ms before streams) |
| `read_line` through a `Buffered<MemoryStream>` | 128 ms |
| 1 000 000 `write_str` of 48 bytes into a `BufferedWriter<MemoryStream>` | 143 ms |
| `copy(fd_stream(0), fd_stream(1))`, to `/dev/null` | 13 ms |
| `copy` from one memory stream to another | 256 ms |

With the conversions in one copy ([[MYLA-369]]; the same 50 MB, 2026-11-09, on a busier machine where `stdin().read_line()` took 129 to 153 ms, seven runs): `Buffered` reading through `read` (`[uint8]`) and `bytes.to_str` instead of `read_str` took 100 to 148 ms, median 106; with the conversions a byte at a time, as before, 289 to 487 ms, median 302 (MYLA-338's 331 ms). Interpreted, on 2 MB, 6.1 to 6.5 s through `read_str`, 6.6 s through `read`. So `read_str` and `write_str` no longer pay for themselves in speed: dropping them is the owner's decision ([[MYLA-399]]). In the same run, 1 000 000 `write`s of a 48-byte `[uint8]` into a `BufferedWriter` over a descriptor took 23 to 28 ms (110 to 118 ms before), and `read_all` gathers text and converts once.

`copy` reads 64 KiB at a time ([[MYLA-379]]; it was 4 KiB): a 256 MiB file copied by `copy(fs.open(a)?, fs.create(b)?)` into a new file took 88 ms natively, 162 ms with 4 KiB, and 40 ms instead of 56 to `/dev/null` (best of seven; 128 KiB gave 85 and 39, 16 KiB 104 and 42). From one memory stream to another it stays as it was.
