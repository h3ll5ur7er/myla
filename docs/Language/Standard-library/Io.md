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
| `errno_text(code: int32) -> str` | The `<cause>` of `write failed: <cause>` below, for the errno of a failed write: `errno_text(28)` is `"no space left on device"`, an errno it doesn't name `"errno 77"` |

Output isn't buffered: what a program wrote is out before it waits for input.

A write to the standard output or error whose pipe nobody reads any more (`myla run prog.my | head -1`) ends the program quietly, as Unix tools stop: natively by SIGPIPE, on wasm32 with the exit code 141 a shell shows for it (D146). Any other error of `print`, `println`, `eprint` and `eprintln`, which have no result (a full disk: `prog > /dev/full`), ends the program with `runtime error: write failed: <cause>` and status 1 (D153); `write` gives it to the program. A write to any other descriptor gives the error to the program instead: the runtime ignores SIGPIPE, and gives a child it starts the default back.

## Reading

Reading goes through a buffered `Reader` ([[MYLA-78]]), a `Buffered` over the descriptor (below). Keep it in a `var`, or in a field of a struct whose `var self` methods read from it (Myla has no references, so a function can't take a reader to read from). A read blocks until there is input or the input ends; the bytes come back verbatim, and an error is the errno as an `IoError` from `std.fs`.

| Item | Result |
| --- | --- |
| `stdin() -> Reader` | A reader of the standard input |
| `reader(fd: int32) -> Reader` | A reader of file descriptor `fd` |
| `r.read_line() -> Result<Option<str>, IoError>` | The next line without its `"\n"` (a `"\r"` before it stays); a last line without `"\n"` counts; `None` at the end |
| `r.read_exact(n: int32) -> Result<Option<str>, IoError>` | Exactly the next `n` bytes (`""` for `n <= 0`); `None` if the input ends first (those bytes stay unread, as after a failed read) |
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

A line or a count longer than what is buffered is gathered in a builder, read by read, so each byte is copied once: `read_line` and `read_exact` take time linear in the length, however few bytes a read gives ([[MYLA-420]], the review's M17 and S5). Before, each read copied the bytes gathered so far again. Natively on x86-64 (2026-11-10): an 8 MiB line 1,291 ms before, 31 ms now; a 16 MiB line from a pipe 21,346 ms, 97 ms; `read_exact(16 MiB)` from a pipe 1,489 ms, 43 ms (from a file 32 and 36 ms). Interpreted, `read_exact(16 MiB)` from a pipe 34,179 ms before, 350 ms now; an 8 MiB line didn't end in 100 s before and takes 16.7 s now, the interpreter's time to look at each byte for the `"\n"`. Lines of up to 120 bytes read as fast as before (50 MB in 112 to 128 ms either way). A failed read in the middle of a line or a count gives its error and leaves what was read of it unread.

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
| `Read` | `read(var self, n: int) -> Result<[uint8], IoError>`: up to `n` bytes from the cursor on, `[]` at the end (and for `n <= 0`); fewer than `n` isn't the end |
| `Write` | `write(var self, b: [uint8]) -> Result<int, IoError>`: all of `b`, or the error that stopped it; `b.len()`. `flush(var self) -> Result<(), IoError>`: whatever is buffered passed on |
| `Seek` | `seek(var self, pos: SeekFrom) -> Result<int64, IoError>`: the cursor moved to `SeekFrom.Start(k)`, `Current(k)` or `End(k)`; the new offset from the start. Before the start is `InvalidInput`; past the end is allowed |
| `Pollable` | `descriptor(self) -> int32`: the descriptor a task can wait for. A `Buffered` over a `Pollable` stream has `ready` and the async reads |

`Read` and `Write` deal in bytes only (D177): a stream implements `read`, or `write` and `flush`, and nothing for text. Strings are bytes (D164), and since [[MYLA-369]] `std.bytes`'s `from_str` and `to_str` convert in one allocation and one copy (the primitives `__str_to_bytes` and `__bytes_to_str`), so a `[uint8]` costs about what a `str` does (the measurements below); the streams of a descriptor (`FdStream`, `fs.File`, a child's pipes) read into a `[uint8]` and write from one themselves (the primitives `__read_bytes` and `__write_bytes`), so their bytes aren't converted at all. Text goes through the adapters: a `Buffered` pulls bytes, keeps them as text and gives `read_line`, `read_exact` and `read_to_end`; a `BufferedWriter` takes text with `write_str`. To write a few bytes of text to an unbuffered stream, `w.write(bytes.from_str(s))` (`import std.bytes as bytes`). Until [[MYLA-399]] each trait had a `str` twin, `read_str` and `write_str`, from when the two kinds converted only byte by byte ([[MYLA-338]]).

A read that gives fewer bytes than it asks for gives a list, or a string, of their size: `__read_bytes`, `__read` and `__sock_recv` keep the cell they allocated for the request only when they filled at least half of it, else they copy what they got into a cell of its size ([[MYLA-420]], the 2026-11-10 review's S1). Before, 33 MB read from a pipe 64 KiB at a time with reads of 16 MiB kept 504 cells of 16 MiB and ran out of memory on wasm32; now it reads them in 105 MB there.

### Streams of this module

| Item | What it is |
| --- | --- |
| `fd_stream(fd: int32) -> FdStream` | A descriptor, unbuffered: each read and write is a system call. `Read`, `Write`, `Seek` (a pipe can't: `Other(29)`, ESPIPE), `Pollable`. A write to a closed pipe is `BrokenPipe`, but on the standard output or error, where it ends the program quietly (D146) |
| `memory_stream() -> MemoryStream`, `from_bytes(b: [uint8])`, `from_str(s: str)` | Bytes in memory and a cursor at the start. `Read`, `Write` (over the bytes at the cursor, and on past the end; a gap a seek past the end left is zeros), `Seek`. It holds up to 2,147,483,647 bytes: a seek past that, by an offset of any size, is `InvalidInput`, and a write past it `Other(27)` (EFBIG), not an overflow (D184) |
| `m.bytes() -> [uint8]`, `m.text() -> str`, `m.position() -> int64` | All its bytes, wherever the cursor is; as text; the cursor |
| `buffered(r: R) -> Buffered<R>` | A buffer in front of `r`: `read_line`, `read_exact`, `read_to_end` and `fill` as `Reader` has them (`Reader` is `Buffered<FdStream>`), `into_inner()` (the stream, without the bytes still buffered). `Read`; `Seek` if `r` can (the buffer dropped; `Current` counts from the next byte a read gives); `Pollable`, `ready` and the async reads if `r` is `Pollable` |
| `short_reads(r: R, most: int32) -> ShortReads<R>` | `r` read at most `most` bytes at a time (at least 1), as a pipe, a socket or a decompressor may give them: for the tests of code that reads streams, which must not count on a read giving all it asked for. `Read`; `into_inner()` |
| `buffered_writer(w: W) -> BufferedWriter<W>`, `buffered_writer_with(w, capacity: int32)` | A buffer in front of `w`, 8 KiB or `capacity` bytes: writes are gathered and passed on when it is full, on `flush` and on `into_inner() -> Result<W, IoError>` (flushed). `Write`; `write_str(s: str) -> Result<int, IoError>`, the bytes of `s` (`s.len()`); `Seek` if `w` can (after the buffer is passed on). Nothing flushes it when the program ends |

`MemoryStream`'s `read_end` and `fill_gap`, `Buffered`'s `pull`, `pull_bytes`, `newline_from` and `take_line`, and `BufferedWriter`'s `push_out`, `drain` and `make_room` are the streams' own steps, public only because a method can't be private yet ([[MYLA-433]]); a program has no need of them.

### Any stream

| Function | Result |
| --- | --- |
| `read_all<R: Read>(r: R) -> Result<[uint8], IoError>` | Everything `r` gives up to its end |
| `copy<R: Read, W: Write>(r: R, w: W) -> Result<W, IoError>` | Everything `r` gives up to its end written to `w`, 64 KiB at a time, which is flushed and given back |

They take the streams by value, so the caller's `var` doesn't move: a memory stream read by `read_all` is where it was. A descriptor's offset, which the platform keeps, does move. `copy` gives the writer back, which is the way to the bytes of a memory stream it wrote, or to a `BufferedWriter`'s stream.

### A stream of your own

A type is a stream when it implements the traits: a `Read` has one method, `read`, and `buffered` gives it lines and text:

```myla
from std.io import Read, buffered, read_all
from std.fs import IoError

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

With the conversions in one copy ([[MYLA-369]]; the same 50 MB, 2026-11-09, on a busier machine where `stdin().read_line()` took 129 to 153 ms, seven runs): `Buffered` reading through `read` (`[uint8]`) and `bytes.to_str` instead of `read_str` took 100 to 148 ms, median 106; with the conversions a byte at a time, as before, 289 to 487 ms, median 302 (MYLA-338's 331 ms). Interpreted, on 2 MB, 6.1 to 6.5 s through `read_str`, 6.6 s through `read`. So `read_str` and `write_str` no longer paid for themselves in speed. In the same run, 1 000 000 `write`s of a 48-byte `[uint8]` into a `BufferedWriter` over a descriptor took 23 to 28 ms (110 to 118 ms before), and `read_all` gathers text and converts once.

Without them (D177, [[MYLA-399]]; 2026-11-09, natively on x86-64, the medians of eleven runs interleaved; before: through `read_str` and `write_str`; then: the bytes converted from and to the descriptor's `str`; now: the descriptor read into and written from a `[uint8]` by `__read_bytes` and `__write_bytes`):

| What | Before | Converted | Now |
| --- | --- | --- | --- |
| `stdin().read_line()` over the 50 MB | 130 to 139 ms | 119 to 121 ms | 131 to 133 ms |
| 1 000 000 `write_str` of 48 bytes into a `BufferedWriter` over `fd_stream(1)`, to `/dev/null` | 14 ms | 15 ms | 14 ms |
| `copy(fd_stream(0), fd_stream(1))` of the 50 MB, to `/dev/null` | 7 ms | 10 ms | 7 ms |
| `read_line` through a `Buffered<MemoryStream>` of the 50 MB (the file read too) | 268 ms | 279 ms | 288 ms |
| 4 GiB from `/dev/zero` to `/dev/null` through two `File`s, reads of 1 MiB | 109 ms (`read_str`, `write_str`); 471 ms (`read`, `write`) | 481 ms | 111 ms |

Interpreted, on 2 MB: 6.80 to 6.93 s before, 6.76 to 6.98 s converted, 6.67 to 6.80 s now. Converting costs nothing for lines but two copies of every byte in a bulk copy, four times the time for the 4 GiB, which the primitives give back. Why the converted lines are faster than either, with two copies more, isn't known (MYLA-369 saw it too).

`copy` reads 64 KiB at a time ([[MYLA-379]]; it was 4 KiB): a 256 MiB file copied by `copy(fs.open(a)?, fs.create(b)?)` into a new file took 88 ms natively, 162 ms with 4 KiB, and 40 ms instead of 56 to `/dev/null` (best of seven; 128 KiB gave 85 and 39, 16 KiB 104 and 42). From one memory stream to another it stays as it was.
