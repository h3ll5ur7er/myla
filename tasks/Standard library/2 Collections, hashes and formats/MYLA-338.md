---
id: MYLA-338
title: Stream traits, memory streams and buffering
type: feature
status: review
priority: medium
labels: [stdlib, io, streams, wave-2]
---
Wave 2 of [[Project/Standard-library-roadmap]], roadmap #41. The base of the streams in waves 3 and 4. A design note goes on the task before code: Myla has no references, so a stream is held in a `var` and an adapter owns the stream it wraps (`Buffered<R: Read>`, `Gzip<R: Read>`).

- **Owns:** `lib/std/io.my`, `docs/Language/Standard-library/Io.md`
- **Needs:** nothing; it can start as soon as its wave does
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

## Design

Myla has no references, so a stream is a value in a `var` (or a field), read and written through `var self` methods. An adapter owns the stream it wraps, by value. What the language allows, tried with `build/myla check` and run both ways:

- A trait may have `var self` methods, and a bound admits them (MYLA-291): `fun f<R: Read>(r: R)` can `var s = r; s.read(n)`.
- A struct can't have bounds on its parameters (`type-parameter bounds are not supported on a struct`), but its impls can: `struct Buffered<R>` with `impl<R: Read> Buffered<R>`. A second impl block may ask for more, `impl<R: Read + Pollable> Buffered<R>`, and the checker holds a call of its methods to that bound (`type 'Mem' does not satisfy the bound 'R: Pollable' required by 'Wrap.which'`). A generic struct may implement a trait generically, `impl<R: Read> Read for Buffered<R>`, so adapters stack.
- `typealias` works on an instantiation, so `pub typealias Reader = Buffered<FdStream>` keeps the name `Reader`, and `from std.io import Reader` and a field `input: Reader` keep working.

So:

- `trait Read { fun read(var self, n: int) -> Result<[uint8], IoError>; fun read_str(var self, n: int) -> Result<str, IoError> }`: up to `n` bytes, `[]` (`""`) at the end. `trait Write { fun write(var self, b: [uint8]) -> Result<int, IoError>; fun write_str(var self, s: str) -> Result<int, IoError>; fun flush(var self) -> Result<(), IoError> }`: a write writes all or fails, and gives the length. `trait Seek { fun seek(var self, pos: SeekFrom) -> Result<int64, IoError> }` with `enum SeekFrom { Start(int64), Current(int64), End(int64) }`, the new offset from the start.
- **Why a `str` method beside each `[uint8]` one.** The first version had only `read` and `write` on `[uint8]`, with `Reader` as `Buffered<FdStream>`. A descriptor reads a `str` (`__read`), and `str` and `[uint8]` turn into each other only byte by byte (no primitive does it), so every line `stdin()` read was converted twice. Measured on 50 MB of lines, natively: 96 ms with the old `Reader`, 331 ms then (257 ms with a line gathered in a `StringBuilder`); interpreted, on 2 MB: 3.3 s, then 13 s. With `read_str`, `Buffered` keeps a `str` buffer and reads text from a descriptor without converting anything: 75 ms natively and about 3.3 s interpreted, as before. Strings are bytes (D164), so a `str` from `read_str` is any bytes. A stream that has one kind natively converts for the other (three lines, as on the page). A memcpy primitive between the two would make the second method unnecessary, but the traits can stay as they are.
- `trait Pollable { fun descriptor(self) -> int32 }`: a stream that is a descriptor the runtime can wait for. Waiting needs one (`__poll`, `__wait_readable`), and a trait method can't be async (D89), so `ready` and the async reads are in the `R: Read + Pollable` impl of `Buffered`. A `File` (MYLA-339) and a child's pipes (MYLA-340) implement `Read`, `Write`, `Seek` where they can, and `Pollable`, as `FdStream` does.
- `FdStream`: an unbuffered descriptor, `fd_stream(fd)`; `Read`, `Write`, `Seek`, `Pollable`. The model for MYLA-339 and MYLA-340.
- `MemoryStream`: `[uint8]` and a cursor; `Read`, `Write` (overwrites at the cursor, extends at the end, fills a gap after a seek past the end with zeros), `Seek`. `memory_stream()`, `from_bytes(b)`, `from_str(s)`, `m.bytes()`, `m.text()`, `m.position()`.
- `Buffered<R>`: `buffered(r)`; `read_line`, `read_exact`, `read_to_end` and `fill` as `Reader` had them, `into_inner`, and `Read` itself; `Seek` with `R: Seek`. With `R: Pollable` also `Pollable`, `ready` and the async forms. `Reader` is `Buffered<FdStream>`; `stdin()` and `reader(fd)` build one.
- `BufferedWriter<W>`: `buffered_writer(w)` (8 KiB), `buffered_writer_with(w, capacity)`; `Write`, `into_inner` (flushed); `Seek` with `W: Seek`.
- **The stream an adapter owns is the one element of a list** (`src: [R]`), and each read pops it, uses it and pushes it back. As a plain field, `var r = self.inner; r.read(n); self.inner = r` shares the stream's bytes with `self.inner` while `r` changes them, so each write to a `BufferedWriter<MemoryStream>` copied all its bytes: 104 s for 47 MB, 0.15 s with the list. (And `self.inner.read(n)` itself fails in the interpreter: the first bug below.)
- `read_all<R: Read>(r: R) -> Result<[uint8], IoError>` and `copy<R: Read, W: Write>(r: R, w: W) -> Result<W, IoError>` are free functions: they take the streams by value, so the caller's `var` doesn't move (a descriptor's offset, kept by the kernel, does), and `copy` gives the writer back, flushed, which is how a `MemoryStream`'s bytes come out of it.

## Bugs found

Both in the interpreter; native code is right. Worked around in `io.my`, not fixed here (`selfhost/` isn't this task's).

1. A method call whose receiver is a field (not a plain name) of a type-parameter type finds no method: `recv_key` falls back to `eval_pure`, which evaluates only a `Name` (`selfhost/interp.my`), so the key is wrong and the call gives `()`.

   ```myla fragment
   trait Step { fun step(var self) -> int }
   struct Wrap<R> { inner: R }
   impl<R: Step> Wrap<R> {
       fun go(var self) -> int { return self.inner.step() }   // interpreted: ()
   }
   ```

   Worked around by calling the method on a local.
2. `?` inside the argument of a call of a function: `return Ok(twice(inner()?))` or `let y = twice(inner()?)` with `inner()` an `Err` is `runtime error: index out of bounds` at `selfhost/interp.my:3113` in the interpreter (the call goes ahead after the `?` set its return: `eval_name_call` doesn't check `self.stop()` after `eval_args`, as `eval_method_call` does); in a `var self` method of `std.io` it gave `Ok` of an empty value instead of the `Err`. Worked around by a `let` with the `?` before the call.

The language server didn't resolve a trait named in a bound (`<R: Read>`: the AST keeps a bound as a bare name), and gave an impl's trait the first token of its name after `impl`, which is the bound's in `impl<R: Read> Read for …`. `tools/lsp/resolve.my` now does both (the `test_the_corpus_resolves` burn test failed on `io.my` without it).

## Checklist

- [x] `Read`, `Write`, `Seek` traits; `MemoryStream` (bytes and a cursor)
- [x] `Buffered<R>` and `BufferedWriter<W>` generic over them; today's `Reader` expressed as one, its API unchanged
- [x] `copy(r, w)` and `read_to_end` on any `Read`
- [x] Async forms where today's reader has them
- [x] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [x] Its page below [[Language/Standard-library]], with a doc block that runs

## Evidence

- Before: the test functions failed to check (`unknown function 'text_of'`, and so on). After, `build/myla test lib/std/io.my --stdlib lib`: 24/24 interpreted, 24/24 `--native`, 24/24 `--target aarch64-linux` (qemu), 24/24 `--target wasm32-wasi` (Node). 14 cases on methods, 10 test functions. A mutation (no `Current` correction in `Buffered`'s `seek`) fails `buffered_seeks`.
- `scripts/bootstrap.sh`: byte-identical fixpoint (11102325 bytes).
- `python3 -m unittest tests.burn.test_stdin tests.burn.test_stdio tests.burn.test_lsp tests.burn.test_std_modules tests.burn.test_doc_blocks`: 179 tests, OK.
- Natively, 50 MB of lines (0 to 120 bytes), best of 3:

  | What | Time |
  | --- | --- |
  | `stdin().read_line()`, the old `Reader` | 96 ms |
  | `stdin().read_line()`, `Buffered<FdStream>` | 75 ms |
  | `read_line` through `Buffered<MemoryStream>` | 128 ms |
  | 1 000 000 `write_str` of 48 bytes into `BufferedWriter<MemoryStream>` | 143 ms |
  | `copy(fd_stream(0), fd_stream(1))` to `/dev/null` | 13 ms |
  | `copy` from a memory stream to another | 256 ms |

  Interpreted, 2 MB of the same, two runs each: 3.3 and 3.4 s with the old `Reader`, 3.6 and 3.2 s with the new.
