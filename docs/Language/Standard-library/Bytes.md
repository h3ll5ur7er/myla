# std.bytes

Strings and bytes ([[MYLA-329]]), and binary data ([[MYLA-931]]). A `str` is bytes (D164), so a string becomes a `[uint8]` and back as its bytes are, whatever they are. UTF-8 is checked and built here, where it matters: `is_utf8`, `utf8_error`, `encode_char` and `decode_char`. The [second half](#binary-data) reads and writes binary formats: integers and floats of either byte order ([ByteReader](#bytereader), [ByteWriter](#bytewriter)) and bit streams of either bit order ([bit readers](#bit-readers), [bit writers](#bit-writers)), for the image codecs, fonts and anything else with a file format.

```myla
import std.bytes as bytes

fun main() {
    let b = bytes.from_str("né")
    print(b.len())
    print(bytes.is_utf8(b))
    if let Some((c, n)) = bytes.decode_char(b, 1) {
        print(f"{c} in {n} bytes")
    }
    var cut = b
    cut.pop()
    print(bytes.utf8_error(cut).unwrap_or(-1))
    var more = bytes.encode_char('€')
    more.push(33u8)
    print(bytes.to_str(more))
}
// output:
// 3
// true
// é in 2 bytes
// 1
// €!
```

| Function | Result |
| --- | --- |
| `from_str(s: str) -> [uint8]` | The bytes of `s` |
| `to_str(b: [uint8]) -> str` | The bytes as a string, unchanged: they needn't be UTF-8 |
| `is_utf8(b: [uint8]) -> bool` | Whether `b` is UTF-8 |
| `utf8_error(b: [uint8]) -> Option<int>` | The position of the first byte that doesn't start a UTF-8 character, so `b[:i]` is the longest valid prefix; `None` if all of `b` is UTF-8 |
| `encode_char(c: char) -> [uint8]` | The one to four UTF-8 bytes of `c` |
| `decode_char(b: [uint8], at: int) -> Option<(char, int)>` | The character that starts at `b[at]` and its length in bytes; `None` if none starts there or `at` is outside `b` |

UTF-8 is what the Unicode Standard's table 3-7 calls well-formed: the shortest form of each character, no surrogates (U+D800 to U+DFFF), nothing past U+10FFFF. So `[192u8, 128u8]`, an overlong NUL, isn't UTF-8, and neither is `[237u8, 160u8, 128u8]`, the surrogate U+D800. A sequence cut short is wrong at its first byte: `utf8_error([104u8, 226u8, 130u8])` is `Some(1)`.

`from_str` and `to_str` are one allocation and one copy each, on every target and in the interpreter: the primitives `__str_to_bytes` and `__bytes_to_str` ([[MYLA-369]]), which a library module calls (a program's call is the primitive warning, D100). Natively on x86-64 each converts 50 MB in 25 to 26 ms, about 2 GB a second, where `to_str` through a `StringBuilder` a byte at a time took 180 to 209 ms and `from_str` a push a byte 123 to 156 ms; interpreted, 2 MB in 0.07 and 0.12 s, where they took 9.5 and 12 s (2026-11-09).

## Binary data

```myla
import std.bytes as bytes

fun main() {
    // a PNG's signature, then the length and type of its first chunk
    var r = bytes.reader([0x89u8, 0x50u8, 0x4Eu8, 0x47u8, 0x0Du8, 0x0Au8, 0x1Au8, 0x0Au8,
        0u8, 0u8, 0u8, 13u8, 0x49u8, 0x48u8, 0x44u8, 0x52u8, 0u8, 0u8, 1u8])
    print(r.eat([0x89u8, 0x50u8, 0x4Eu8, 0x47u8, 0x0Du8, 0x0Au8, 0x1Au8, 0x0Au8]))
    let len = r.u32_be().unwrap_or(0)
    let tag = bytes.to_str(r.take(4).unwrap_or([]))
    print(f"{tag}, {len} bytes")
    // three bytes are left: a u32 doesn't fit, and nothing is read
    print(r.u32_be() == None && r.pos == 16)
    print(r.u24_be().unwrap_or(0))

    // little-endian, as BMP writes it, and a length filled in afterwards
    var w = bytes.writer()
    w.put_str("BM")
    w.put_u32_le(0u32)
    w.put_f32_le(0.5f32)
    w.set_u32_le(2, w.len() as uint32)
    var back = bytes.reader(w.finish())
    print(back.skip(2) && back.u32_le() == Some(10u32) && back.f32_le() == Some(0.5f32))

    // bits: the highest of each byte first (JPEG, TIFF), or the lowest (GIF, DEFLATE)
    var m = bytes.msb_reader([0b10101100u8])
    var l = bytes.lsb_reader([0b10101100u8])
    print(f"{m.bits(3).unwrap_or(9)} {l.bits(3).unwrap_or(9)}")

    // JPEG: 0xFF 0x00 is the byte 0xFF, and the data ends at a marker (here RST0)
    var j = bytes.jpeg_reader([0xFFu8, 0u8, 0x12u8, 0xFFu8, 0xD0u8, 0x34u8])
    print(f"{j.bits(16).unwrap_or(0):#x}, then {j.bits_left()} bits")
    if let Some(code) = j.skip_marker() {
        print(f"marker {code:#x}, then {j.bits(8).unwrap_or(0):#x}")
    }

    // written and read back, 5 bits a value
    var bw = bytes.msb_writer()
    for v in [3, 14, 15, 9, 26] {
        bw.put_bits(v as uint32, 5)
    }
    let packed = bw.finish()
    var br = bytes.msb_reader(packed)
    var vs: [str] = []
    for i in 0..5 {
        vs.push(f"{br.bits(5).unwrap_or(0)}")
    }
    let text = vs.join(" ")
    print(f"{packed.len()} bytes, {br.bits_left()} bits of padding: {text}")
}
// output:
// true
// IHDR, 13 bytes
// true
// 1
// true
// 5 4
// 0xff12, then 0 bits
// marker 0xd0, then 0x34
// 4 bytes, 7 bits of padding: 3 14 15 9 26
```

Every read gives an `Option`: `None` when the data is too short, and then nothing is read (the position stays where it was). So a decoder of untrusted input can't end in a runtime error by reading too far, and turns each `None` into its own error: `let Some(w) = r.u32_be() else { return Err(ImageError.Truncated) }`, or `?` in a function that returns an `Option`. Parameters are immutable, so a decoder keeps its reader in a field of its own struct and reads in `var self` methods (`self.r.u16_be()`).

### ByteReader

`ByteReader { data: [uint8], pos: int }` reads `data` from `pos` on. `pos` is public and may be set by hand; outside `0..data.len()` nothing can be read. `be` is big-endian, the most significant byte first (PNG, JPEG, TIFF's "MM", fonts), `le` little-endian (BMP, GIF, TIFF's "II", RIFF).

| Function or method | Result |
| --- | --- |
| `reader(data: [uint8]) -> ByteReader` | A reader at position 0 |
| `r.remaining() -> int` | The bytes left: `data.len() - pos`, or 0 at the end or with `pos` outside the data |
| `r.has(n: int) -> bool` | Whether `n` more bytes can be read; `false` for `n < 0` |
| `r.at_end() -> bool` | Whether nothing is left |
| `r.seek(p: int) -> bool` | To position `p`, from 0 to `data.len()` (the end); `false`, and nothing changed, outside that |
| `r.skip(n: int) -> bool` | `n` bytes on, or back for a negative `n`; `false`, and nothing changed, if that leaves `0..data.len()` |
| `r.take(n: int) -> Option<[uint8]>` | The next `n` bytes (a copy); `None` if fewer are left or `n < 0` |
| `r.take_rest() -> [uint8]` | All the bytes left (a copy); the position is then the end |
| `r.eat(sig: [uint8]) -> bool` | Whether the next bytes are `sig` (a signature, a tag); if so they are read, else nothing is |
| `r.peek_u8() -> Option<uint8>` | The next byte, not read |
| `r.u8() -> Option<uint8>`, `r.i8() -> Option<int8>` | The next byte, unsigned or two's complement |
| `r.u16_be()`, `r.u16_le() -> Option<uint16>` | Two bytes |
| `r.i16_be()`, `r.i16_le() -> Option<int16>` | Two bytes, two's complement |
| `r.u24_be()`, `r.u24_le() -> Option<uint32>` | Three bytes (OpenType's `uint24`), in the low 24 bits |
| `r.u32_be()`, `r.u32_le() -> Option<uint32>` | Four bytes |
| `r.i32_be()`, `r.i32_le() -> Option<int32>` | Four bytes, two's complement |
| `r.u64_be()`, `r.u64_le() -> Option<uint64>` | Eight bytes |
| `r.i64_be()`, `r.i64_le() -> Option<int64>` | Eight bytes, two's complement |
| `r.f32_be()`, `r.f32_le() -> Option<float32>` | Four bytes as an IEEE 754 single (std.float's `from_bits32`) |
| `r.f64_be()`, `r.f64_le() -> Option<float64>` | Eight bytes as an IEEE 754 double (`from_bits`) |

A `uint32` length turns negative as an `int` past 2^31 - 1 (`len as int`), and `take` and `skip` refuse a negative count, so `r.take(len as int)` is safe as it is.

### ByteWriter

`ByteWriter { out: [uint8] }` appends to `out`. The `put_` methods take the value in the type the reader gives back (`put_u24_*` writes the low 24 bits of a `uint32`).

| Function or method | Result |
| --- | --- |
| `writer() -> ByteWriter` | An empty writer |
| `w.len() -> int` | The bytes written so far: where the next one goes |
| `w.finish() -> [uint8]` | The bytes written |
| `w.put_u8(v: uint8)`, `w.put_i8(v: int8)` | One byte |
| `w.put_u16_be(v: uint16)`, `put_u16_le`, `put_i16_be(v: int16)`, `put_i16_le` | Two bytes |
| `w.put_u24_be(v: uint32)`, `put_u24_le` | The low three bytes of `v` |
| `w.put_u32_be(v: uint32)`, `put_u32_le`, `put_i32_be(v: int32)`, `put_i32_le` | Four bytes |
| `w.put_u64_be(v: uint64)`, `put_u64_le`, `put_i64_be(v: int64)`, `put_i64_le` | Eight bytes |
| `w.put_f32_be(v: float32)`, `put_f32_le`, `put_f64_be(v: float64)`, `put_f64_le` | The IEEE 754 bits; a NaN is written as the quiet NaN (D128) |
| `w.put_bytes(b: [uint8])`, `w.put_str(s: str)` | The bytes as they are |
| `w.put_zeros(n: int)` | `n` zero bytes (padding); none for `n <= 0` |
| `w.set_u8(at: int, v: uint8)`, `set_u16_be`, `set_u16_le`, `set_u32_be`, `set_u32_le` | Bytes written before replaced, from `at` on: a length or an offset filled in once it is known. Outside `0..len()` this is a runtime error, as an index is: the encoder chose `at` |

### Bit readers

Two types with the same methods: `MsbBitReader` takes each byte's highest bit first (JPEG, TIFF's LZW, PNG's packed samples), `LsbBitReader` its lowest bit first (DEFLATE, GIF's LZW). A value of `k` bits read at once is the same as `k` reads of one bit, put together highest first for the MSB reader, `(b1 << (k - 1)) | … | bk`, and lowest first for the LSB one, `b1 | (b2 << 1) | …`. Both keep up to 63 bits in a `uint64` buffer and load bytes into it when a read needs more.

| Function or method | Result |
| --- | --- |
| `msb_reader(data: [uint8], start: int = 0) -> MsbBitReader` | A reader of `data`'s bits from byte `start` on (a `start` outside the data is moved to 0 or the end); `data` isn't copied |
| `lsb_reader(data: [uint8], start: int = 0) -> LsbBitReader` | The same, lowest bit first |
| `jpeg_reader(data: [uint8], start: int = 0) -> MsbBitReader` | A reader of the JPEG entropy-coded segment that starts at `start`: [below](#jpeg) |
| `b.bits(k: int) -> Option<uint32>` | The next `k` bits, `k` from 0 to 32 (`bits(0)` is `Some(0)`); `None`, and nothing read, if fewer are left or `k` is outside 0 to 32 |
| `b.peek(k: int) -> uint32` | The next `k` bits (0 to 32) without reading them; past the end of the data they are 0 bits, and outside 0 to 32 the result is 0. For a Huffman decoder, which looks ahead by its longest code: `let v = b.peek(16)`, the code's length `n` from a table, then `b.skip_bits(n)` |
| `b.skip_bits(k: int) -> bool` | `k` bits passed over, any number of them; `false`, and nothing read, if fewer are left or `k < 0` |
| `b.align_byte()` | The rest of the byte being read passed over; nothing at a byte's start. PNG's rows, DEFLATE's stored blocks |
| `b.bits_left() -> int64` | The bits not read yet (an `int64`: 8 bits a byte overflow an `int` past 256 MiB) |
| `b.byte_pos() -> int` | The position in `data` of the byte that holds the next bit; after `align_byte`, of the next byte to read; `data.len()` at the end. Where a byte-level parser goes on after a bit stream |
| `b.refill()` | Bytes loaded into the buffer until it holds at least 56 bits or the data ends. The reads call it themselves: see [In a hot loop](#in-a-hot-loop) |
| `m.marker() -> Option<uint8>` | `MsbBitReader` only. JPEG: the marker (the byte after its 0xFF) where the segment ends, known from the start, before the bits up to it are read; `None` if the data ends without one, and always for `msb_reader` |
| `m.marker_pos() -> int` | Where that marker is: the position of the 0xFF just before its code; `data.len()` without one |
| `m.skip_marker() -> Option<uint8>` | JPEG: past the marker where the segment ends (a restart marker), the bits not read before it dropped, and on to the next segment; gives the marker, or `None` (nothing changed) without one |

### JPEG

In JPEG's entropy-coded data (ITU T.81, B.1.1.5 and F.1.2.3) a byte 0xFF is written as 0xFF 0x00, and 0xFF followed by any other byte is a marker, maybe after fill bytes 0xFF. `jpeg_reader` scans the segment once when it is made (a pass over its bytes, much less than decoding them), so it knows where the data ends and how many of its bytes are stuffing: `bits_left()` counts only the data, `marker()` is known at once, and reads past the marker give `None` (and `peek` 0 bits), as if the data ended there. A 0xFF at the very end of the data, with nothing after it, is no data either. `byte_pos()` counts the 0x00 after each 0xFF, so at the end of the segment it is where the marker's bytes (its fill bytes first) begin.

A scan with restart markers decodes its restart interval, then checks for the marker and goes on:

```myla fragment
// in a `var self` method of the decoder, which keeps `br: MsbBitReader`
match self.br.skip_marker() {
    Some(m) if m == 0xD0u8 + ((k % 8) as uint8) => {}   // RSTk: reset the DC predictions
    _ => return Err(ImageError.Corrupt("restart marker expected"))
}
```

At the end of the scan, `marker_pos()` is where the byte-level parser goes on (EOI, or the next scan's tables and SOS). Each scan of a progressive JPEG gets a `jpeg_reader(data, start)` of its own on the same `data`, which isn't copied.

### Bit writers

`MsbBitWriter` and `LsbBitWriter` write bits as the readers read them, so `put_bits(v, k)` and then `bits(k)` give the low `k` bits of `v` back.

| Function or method | Result |
| --- | --- |
| `msb_writer() -> MsbBitWriter`, `lsb_writer() -> LsbBitWriter` | An empty writer |
| `jpeg_writer() -> MsbBitWriter` | A writer of JPEG entropy-coded data: each 0xFF byte written is followed by 0x00, and the padding is 1 bits (T.81, F.1.2.3) |
| `w.put_bits(v: uint32, k: int)` | The low `k` bits of `v`, `k` from 0 to 32 (outside that a panic: the encoder chose `k`); the higher bits of `v` are ignored |
| `w.align_byte()` | The byte being written filled up: with 0 bits, with 1 bits for `jpeg_writer` |
| `w.put_bytes(b: [uint8])` | After `align_byte`, `b` as it is, not stuffed |
| `w.put_marker(code: uint8)` | `MsbBitWriter` only. After `align_byte`, the marker 0xFF `code` (a restart marker RSTn is 0xD0 to 0xD7) |
| `w.bit_len() -> int64` | The bits written, padding included, stuffing not |
| `w.finish() -> [uint8]` | The bytes, the last one filled up as `align_byte` does (the writer is left so) |

### In a hot loop

Every read is a call: the compiler doesn't inline a function of another module, and keeps a struct's fields in memory rather than registers. In a decoder's innermost loop that costs about twice the time of the same loop with its bit buffer in local variables ([Speed](#speed)). The bit readers' fields are their documented state, so a loop that needs the speed can copy `acc`, `n` and `next` into locals, load `data[next]` itself, and store them back after the loop:

- `MsbBitReader`: the next bit to read is bit `n - 1` of `acc` (`n` is at most 63); a byte goes in at the bottom, `acc = (acc << 8) | byte`, `n += 8`, `next += 1`; a read of `k` bits is `n -= k`, then `(acc >> n) & mask`. With `jpeg_reader`, leave loading to `refill()`: the fields `end` (where the data ends), `extra` (bytes of stuffing before it), `mark` and `mark_pos` are the methods' business.
- `LsbBitReader`: the next bit is bit 0 of `acc`, and its bits from `n` up are zeros; a byte goes in at the top, `acc |= byte << n`, `n += 8`, `next += 1`; a read is `acc & mask`, then `acc >>= k`, `n -= k`.

Using the fields without locals, with a call of `refill()` only when they run low, gains about 15 %. Checking `has(n)` before a run of `ByteReader` reads gains nothing, as each read checks anyway; the `Option` itself costs nothing measurable.

## Speed

`benchmarks/bytes_std.my`, natively on x86-64, the best of five runs over 100 MiB (104,857,600 bytes, 64,527,753 codes of 13 bits) of pseudo-random bytes, on a machine shared with other work (2026-11-24). Each library loop is beside the same loop written by hand, its state in local variables:

| What | Library | By hand | Ratio |
| --- | --- | --- | --- |
| The data as `u32_be`s, `while let Some(v) = r.u32_be()` | 136 ms, 770 MB/s | 78 ms, 1340 MB/s | 1.7 |
| The same, `while r.has(4)` first | 181 ms | | 2.3 |
| 13-bit codes, MSB first, `bits(13)` | 405 ms, 159 M codes/s | 153 ms | 2.6 |
| 13-bit codes, LSB first, `bits(13)` | 483 ms, 134 M codes/s | 216 ms | 2.2 |
| The same with the reader's fields in the loop, `refill()` when low | 411 ms | | 1.9 |
| A Huffman step: `peek(16)`, then `skip_bits` of 1 to 16 bits | 1090 ms | | |
| 13-bit codes written, MSB first, `put_bits` | 508 ms | 298 ms | 1.7 |

So the task's aim, within 20 % of the hand-written loop, isn't reached: the readers take 1.7 to 2.6 times as long. The time goes to the shape, not to the checks: the same reader declared in the benchmark's own module is as slow, so is a `bits` without the `Option` (-1 past the end), and the fields used inline still take 1.9 times as long. Each read is a call that loads and stores the buffer through a pointer, where the hand-written loop keeps it in registers. Inlining across modules, or keeping a struct's fields in registers through a loop, is compiler work that would help every library type, not this one alone. Until then a codec whose bit reading dominates (JPEG's Huffman decoding, inflate) can keep the buffer in locals as [In a hot loop](#in-a-hot-loop) says; header parsing, chunk walking and table reading don't need to.

## Tests

The module's 183 cases pass interpreted, natively (where they run checked) and on wasm32 under Node: `#test` cases on every method with values to compare, and test functions for each bit reader against a bit-by-bit reference (reads of every width from 0 to 32, skips and alignments, from a start inside the data, in both orders), the writers round-tripping through the readers (400 values of random widths, in both orders and JPEG's), every integer and float type both ways, the position after reads that don't fit, and JPEG's stuffing, fill bytes, markers and restarts. A fuzz test runs 300 random sequences of every operation, with invalid widths and starts among them, on random bytes rich in 0xFF, 0x00 and markers, against a byte-at-a-time reference of the segment; natively, 200,000 such sequences (12 million operations) pass, built plain and `--checked`.
