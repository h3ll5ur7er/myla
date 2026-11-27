# std.compress

DEFLATE decompression ([[MYLA-344]]) and compression ([[MYLA-352]]), and the gzip and zlib formats around them; LZW and PackBits, the codecs of GIF and TIFF ([[MYLA-958]], [below](#lzw-and-packbits)). tar and zip archives are [[Language/Standard-library/Archive]].

```myla
import std.compress as compress
import std.encoding as encoding
import std.bytes as bytes
from std.io import from_bytes, Read

fun main() {
    // gzip.compress(b"hello, world", mtime=0) in Python
    let gz = encoding.hex_decode("1f8b08000000000002ffcb48cdc9c9d75128cf2fca4901003a72abff0c000000").unwrap_or([])
    match compress.gunzip(gz) {
        Ok(b) => print(bytes.to_str(b))
        Err(e) => print(f"error: {e}")
    }

    // the same as a stream, read five bytes at a time
    var r = compress.gzip_reader(from_bytes(gz))
    while true {
        match r.read(5) {
            Ok(b) => {
                if b.len() == 0 { break }
                print(f"[{bytes.to_str(b)}]")
            }
            Err(_) => {
                print(f"error: {r.error().unwrap_or(compress.CompressError.Truncated)}")
                break
            }
        }
    }

    // zlib.compress(b"abcabcabcabcabcabc", 9), then with its last byte changed
    var z = encoding.hex_decode("78da4b4c4a4e444500417c06e5").unwrap_or([])
    print(bytes.to_str(compress.zlib_decompress(z).unwrap_or([])))
    z[^1] = 0
    match compress.zlib_decompress(z) {
        Ok(_) => print("accepted")
        Err(e) => print(f"error: {e}")
    }
}
// output:
// hello, world
// [hello]
// [, wor]
// [ld]
// abcabcabcabcabcabc
// error: checksum mismatch
```

## Functions

Each takes the whole compressed input and gives the whole output. The input must be exactly one stream: bytes after its end are `TrailingData`.

| Function | Result |
| --- | --- |
| `inflate(b: [uint8], max_output: int = 0x7FFFFFFF) -> Result<[uint8], CompressError>` | The raw DEFLATE stream `b` (RFC 1951) decompressed |
| `gunzip(b: [uint8], max_output: int = 0x7FFFFFFF) -> Result<[uint8], CompressError>` | The gzip data `b` (RFC 1952) decompressed: every member, one after the other. Zero bytes after a member are padding, as for `gzip` |
| `zlib_decompress(b: [uint8], max_output: int = 0x7FFFFFFF) -> Result<[uint8], CompressError>` | The zlib stream `b` (RFC 1950) decompressed |

`max_output` bounds the output: a stream that stands for more than `max_output` bytes is `TooLarge` ([[MYLA-423]]). Decoding stops a byte past the limit (a back reference past it copies at most 257 bytes more), so a few kilobytes of input that stand for gigabytes of output, a "decompression bomb", take no more memory than the limit: a caller that decompresses what it was sent passes the most it will take, `compress.gunzip(body, 1 << 20)`. The default is the longest list there is. A `max_output` below 0 is a runtime error, `compress.gunzip: max_output -1 is below 0` (D184). A stream's reader bounds itself: it reads as much as it wants.

The names are the operations' usual ones; [compressing](#compressing) has the other direction. A `str` read from a file is turned into bytes with `bytes.from_str` ([[Language/Standard-library/Bytes]]).

## Streams

A `Decoder<R>` is a `Read` stream ([[Language/Standard-library/Io#streams]]) of what the compressed stream `R` gives decompressed, so a file or a pipe is decompressed as it is read, in a window of 32 KiB, whatever its length. It owns its inner stream, as `buffered` does, and reads it in chunks of 32 KiB, so the inner stream is read past the end of the compressed data.

| Item | What it is |
| --- | --- |
| `inflate_reader<R: Read>(r: R) -> Decoder<R>` | Raw DEFLATE; the stream ends where DEFLATE's ends, and the bytes after it are left unread (in the decoder's chunk) |
| `gzip_reader<R: Read>(r: R) -> Decoder<R>` | gzip, member after member, to the end of `r`; anything there but another member or zero padding is `TrailingData` |
| `zlib_reader<R: Read>(r: R) -> Decoder<R>` | zlib; the stream ends where zlib's ends |
| `d.read(n)` | `Read`: up to `n` bytes of the output, `[]` at its end; `io.buffered(d)` reads it as text, by lines |
| `d.read_to_end() -> Result<[uint8], CompressError>` | The rest of the output, or why it couldn't be had |
| `d.error() -> Option<CompressError>` | Why a read failed |
| `d.into_inner() -> R` | The inner stream |

`Read` gives an `IoError`, so a read of corrupt data fails with `IoError.InvalidInput`, and `error()` says what was wrong; a failure of the inner stream is its own `IoError` (and `error()` is `Io` of it). A failure stays: every later read gives it again, and output decoded before it isn't given. `read_to_end` gives the `CompressError` itself.

`Decoder`'s `ready` and `fill` (decoding until output waits) and `Encoder`'s `push_out` (what is compressed so far written to the inner stream) are the streams' own steps, public only because a method can't be private yet ([[MYLA-433]]); a program has no need of them.

```myla fragment
import std.compress as compress
import std.io as io

// The decompressed standard input, to the standard output.
fun main() {
    var d = compress.gzip_reader(io.fd_stream(0))
    match io.copy(d, io.fd_stream(1)) {
        Ok(_) => {}
        Err(_) => io.eprintln("not gzip data")
    }
}
```

`io.copy` takes the decoder by value, so the caller's `d` can't say why it failed; a loop over `d.read(n)` can.

## Compressing

```myla
import std.compress as compress
import std.bytes as bytes
import std.io as io

fun main() {
    let text = bytes.from_str("to be or not to be, that is the question: to be or not to be")
    for level in [0, 1, 6, 9] {
        print(f"level {level}: {compress.deflate(text, level).len()} bytes")
    }
    let gz = compress.gzip(text)
    print(bytes.to_str(compress.gunzip(gz).unwrap_or([])))

    // as a stream: what is written is compressed into the stream it owns
    var w = compress.zlib_writer(io.memory_stream(), 9)
    for i in 0..1000 {
        match w.write(bytes.from_str(f"line {i}\n")) {
            Ok(_) => {}
            Err(e) => print("write failed")
        }
    }
    match w.finish() {
        Ok(m) => {
            let z = m.bytes()
            let back = compress.zlib_decompress(z).unwrap_or([])
            print(f"{back.len()} bytes in {z.len()}")
        }
        Err(e) => print("finish failed")
    }
}
// output:
// level 0: 65 bytes
// level 1: 42 bytes
// level 6: 41 bytes
// level 9: 41 bytes
// to be or not to be, that is the question: to be or not to be
// 8890 bytes in 1985
```

The level is zlib's: 0 stores the bytes as they are, 1 is the fastest, 9 the smallest, 6 the default; a level below 0 is 6 (zlib's -1), one above 9 is 9. Compressing can't fail.

| Function | Result |
| --- | --- |
| `deflate(b: [uint8], level: int = 6) -> [uint8]` | The raw DEFLATE stream (RFC 1951) of `b` |
| `gzip(b: [uint8], level: int = 6) -> [uint8]` | gzip data (RFC 1952) of `b`: one member, without a name or a time (0), the system "unknown" (255) |
| `zlib_compress(b: [uint8], level: int = 6) -> [uint8]` | The zlib stream (RFC 1950) of `b`, without a preset dictionary |

An `Encoder<W>` is a `Write` stream ([[Language/Standard-library/Io#streams]]) that compresses what is written to it and writes the compressed bytes to the stream `W` it owns, so a file is compressed as it is written, whatever its length. It gathers 64 KiB of input before it compresses, and 64 KiB of output before it writes; it keeps the input of the block it is gathering and the 32 KiB window before it. What the functions make and what a writer makes of the same bytes, in pieces of any size, are the same bytes, unless it was flushed.

| Item | What it is |
| --- | --- |
| `deflate_writer<W: Write>(w: W, level: int = 6) -> Encoder<W>` | A writer of raw DEFLATE |
| `gzip_writer<W: Write>(w: W, level: int = 6) -> Encoder<W>` | A writer of gzip data, one member |
| `zlib_writer<W: Write>(w: W, level: int = 6) -> Encoder<W>` | A writer of a zlib stream |
| `e.write(b)` | `Write`: the bytes taken; an error is the inner stream's. Text through `io.buffered_writer(e)` and its `write_str`, or `bytes.from_str` |
| `e.flush()` | `Write`: everything written so far compressed and written, ending with an empty stored block, as zlib's `Z_SYNC_FLUSH` does, so the output so far decodes to all of the input so far; then the inner stream flushed. Each flush costs a few bytes and the block it ends |
| `e.finish() -> Result<W, IoError>` | The end of the stream (the last block, the trailer) written, and the inner stream, flushed. Nothing finishes an `Encoder` when the program ends: finish it |

```myla fragment
import std.compress as compress
import std.io as io

// The standard input, gzipped, to the standard output.
fun main() {
    match io.copy(io.fd_stream(0), compress.gzip_writer(io.fd_stream(1), 9)) {
        Ok(w) => {
            match w.finish() {
                Ok(_) => {}
                Err(_) => io.eprintln("write failed")
            }
        }
        Err(_) => io.eprintln("write failed")
    }
}
```

`io.copy` flushes the writer it is given once at its end, which costs five bytes here.

## LZW and PackBits

The codecs inside GIF and TIFF files ([[MYLA-958]], for [[Project/Standard-library-roadmap/Images-vision-and-fonts]]): LZW in GIF's form and in TIFF's, and PackBits. Each works on one stream's bytes, whole; the image formats around them (sub-blocks, strips, predictors) are the image modules' work.

```myla
import std.compress as compress
import std.encoding as encoding

fun main() {
    // the LZW data of a 4x4 GIF image Pillow wrote, minimum code size 8
    let gif = encoding.hex_decode("00010410304020418305070e0808").unwrap_or([])
    match compress.lzw_decode_gif(gif, 8) {
        Ok(px) => print(f"{px.len()} pixels, the first row {px[0]} {px[1]} {px[2]} {px[3]}")
        Err(e) => print(f"error: {e}")
    }

    // a TIFF strip of 1000 bytes in runs of 100, through LZW and PackBits
    var strip: [uint8] = []
    for i in 0..1000 { strip.push((i / 100) as uint8) }
    let lzw = compress.lzw_encode_tiff(strip)
    print(f"LZW: {lzw.len()} bytes, back: {compress.lzw_decode_tiff(lzw, strip.len()) == Ok(strip)}")
    let pb = compress.packbits_encode(strip)
    print(f"PackBits: {pb.len()} bytes, back: {compress.packbits_decode(pb, strip.len()) == Ok(strip)}")

    // clear, then code 7 at 3 bits: past the table
    match compress.lzw_decode_gif([0x3cu8], 2) {
        Ok(_) => print("decoded")
        Err(e) => print(f"error: {e}")
    }
}
// output:
// 16 pixels, the first row 0 1 2 3
// LZW: 160 bytes, back: true
// PackBits: 20 bytes, back: true
// error: invalid code
```

| Function | Result |
| --- | --- |
| `lzw_decode_gif(b: [uint8], min_code_size: int, max_output: int = 0x7FFFFFFF) -> Result<[uint8], CompressError>` | The bytes (palette indices) the LZW data `b` of a GIF image stands for: its sub-blocks' bytes joined without their lengths, and the minimum code size the file gives before them (1 to 8, else `BadCodeSize`) |
| `lzw_encode_gif(b: [uint8], min_code_size: int) -> [uint8]` | The LZW data of the indices `b` for a GIF image of that minimum code size: 2 to 8, each byte below `1 << min_code_size` (else a runtime error, `compress.lzw_encode_gif: min_code_size 1 is not 2 to 8`, `compress.lzw_encode_gif: byte 4 doesn't fit min_code_size 2`). The file holds it in sub-blocks of at most 255 bytes |
| `lzw_decode_tiff(b: [uint8], max_output: int = 0x7FFFFFFF) -> Result<[uint8], CompressError>` | The bytes a TIFF strip or tile compressed with LZW (compression 5) stands for |
| `lzw_encode_tiff(b: [uint8]) -> [uint8]` | The LZW data of `b` for a TIFF strip or tile |
| `packbits_decode(b: [uint8], max_output: int = 0x7FFFFFFF) -> Result<[uint8], CompressError>` | The bytes the PackBits data `b` (TIFF's compression 32773, also MacPaint's, PSD's and ICNS's) stands for |
| `packbits_encode(b: [uint8]) -> [uint8]` | The PackBits data of `b` |

`max_output` bounds each decoder as it bounds `inflate`: more output is `TooLarge`, checked before a string or a run is copied, so a stream that stands for more takes no more memory than the limit. An image decoder passes the size its header gives. Below 0 it is a runtime error (`compress.lzw_decode_gif: max_output -1 is below 0`).

**LZW.** A code is a literal (below `clear = 1 << min_code_size`, 256 for TIFF), the clear code `clear`, the end code `clear + 1`, or an entry of the table, from `clear + 2` up: each code after the first since a clear adds an entry, the previous code's string and the first byte of its own. A code may be the entry it is about to add (the string of the previous code and its first byte, "KwKwK"); any later code is past the table, `BadCode`, and so is an entry right after a clear. Codes are `min_code_size + 1` bits wide after a clear and grow by a bit, up to 12, once the next entry is `1 << width` (GIF) or one before it (TIFF's "early change"). The two forms differ only there and in the bits' order:

| | GIF | TIFF | TIFF 5.0's old LZW |
| --- | --- | --- | --- |
| Bits of a code | the lowest first (LSB) | the highest first (MSB) | LSB |
| A wider code | when the next entry is `1 << width` | one entry earlier | when the next entry is `1 << width` |
| Minimum code size | the file's, 1 to 8 (2 to 8 written) | 8 | 8 |

`lzw_decode_tiff` reads the old LZW of TIFF 5.0, which some old files still hold, when the strip's first byte is 0 and its second's lowest bit is 1: that is a clear code (256) written LSB-first, where the MSB-first clear code starts with the byte 0x80. libtiff detects it the same way.

A decoder takes what the encoders of the wild write. A table full at 4096 entries stays as it is, its codes still in use, until a clear code comes (the "deferred clear"); codes stay 12 bits wide. The data ends with the end code, and whatever follows it in the stream is ignored, or where the input ends, with or without the end code and with the bits of a part code left over, as libtiff and browsers read it; an image decoder that counts its pixels sees a short stream for what it is. A stream needn't start with a clear code.

The encoders write a clear code first, the longest string the table has at each step, a clear code once the table is full (4096 entries for GIF; for TIFF before the 4094th, as libtiff does, so no code needs 13 bits), and the end code. A pair (an entry, the next byte) is found in a hash of 8192 slots, probed in turn, the hash Knuth's multiplier's top 13 bits; a clear empties it.

**PackBits.** A header byte `n`, as an `int8`, is followed by `n + 1` bytes as they are (0 to 127) or by one byte to repeat `1 - n` times (-127 to -1); -128 is a byte to skip. A run cut short by the end of the input is `Truncated`. `packbits_encode` writes a run of three or more equal bytes as a repeat of up to 128, a pair as a repeat only where no literal run is pending (inside one it costs as much as a repeat and ends no run), and the rest as literal runs of up to 128 bytes, so its output is never longer than the input and a byte for each 128 bytes of it. TIFF compresses each row on its own: the caller passes one row at a time.

## Errors

`CompressError` is a bare enum (D168), with `message()` and `Format`; it is `Eq` (two `Io` errors are equal when their causes are). Corrupt input of every kind is one of them, never a panic or a hang.

| Variant | Meaning |
| --- | --- |
| `Truncated` | The input ended inside the stream (a PackBits run cut short) |
| `BadHeader` | Not a gzip or zlib header: the magic bytes, a method other than DEFLATE, reserved gzip flags, zlib's header check, a window over 32 KiB |
| `PresetDictionary` | A zlib stream that needs a preset dictionary (FDICT), which this module doesn't take |
| `BadBlockType` | A block of the reserved type 3 |
| `BadStoredLength` | A stored block whose length and its complement don't match |
| `BadCodeLengths` | A dynamic block's code lengths: more than 286 or 30 codes, a repeat with nothing to repeat or past the end, lengths that over-subscribe a code, or leave it incomplete but for a single code of length 1, no code for the end of the block. A distance code with no lengths at all is allowed: its block has only literals |
| `BadCode` | Bits that aren't a code of the block, or a symbol DEFLATE doesn't define (lengths 286 and 287, distances 30 and 31); an LZW code past its table |
| `DistanceTooFar` | A distance back past the start of the output (of the member, for gzip) |
| `ChecksumMismatch` | The CRC-32 (gzip) or Adler-32 (zlib) of the output, or gzip's header CRC, isn't the stream's |
| `LengthMismatch` | The output's length isn't the one the gzip trailer gives (modulo 2^32: the length a stream sums wraps, D184) |
| `TrailingData` | Bytes after the end of the stream |
| `TooLarge` | More output than the function's `max_output` |
| `Io(IoError)` | The inner stream failed |
| `BadCodeSize` | A GIF LZW minimum code size outside 1 to 8 |

The rules are zlib's, so `gzip`, Python's `zlib` and this module accept and reject the same streams: the burn test checks 400 corrupted ones, each read three ways. Python's `gzip` module alone is more lenient: it ignores the header's CRC and its reserved flags. A gzip header's fields (name, comment, time, extra field) are checked as far as they have checks and skipped.

## How it works

One decoder does the work. It is given compressed bytes and decodes as far as they go: until the output it was asked for is there, the input runs out, or the stream ends. It stops only at a symbol's boundary, so a stream can be cut anywhere: before a symbol it waits for 48 bits, the most a length and a distance take, unless the input has ended, and before a block's header for 1024 bytes, more than a dynamic header takes. The functions give it all their input at once; a `Decoder` gives it each chunk its inner stream reads.

The output is a list the decoder appends to. A back reference copies from it, byte by byte, as a match may overlap itself. A stream hands the list out whole when it is read whole (no copy), and keeps it as the window if it holds 32 KiB, else copies its bytes into a ring of 32 KiB; a back reference that reaches before the list reads the window. The functions never hand the list out, so they keep everything and need no window.

Huffman codes are decoded with a table indexed by the next 10 bits: an entry gives the symbol and its length. A longer code (up to 15 bits) is decoded bit by bit from the code's counts, as `puff` does. The table pays: natively, `gunzip` of the benchmark below takes 1157 ms with no table (every code bit by bit), and with a table of 8, 9, 10 or 11 bits 744, 757, 735 and 746 ms. The widths differ by less than the noise; 10 bits is the fastest, and leaves few codes to the slow path.

CRC-32 and Adler-32 are std.checksum's algorithms ([[Language/Standard-library/Checksum]]), written here over a part of the output, with the CRC's tables kept in the decoder. std.checksum's functions take a whole list and make the tables at each call, while the decoder sums its output a part at a time: slicing each part out for them took `gunzip` of the benchmark from 526 to 802 ms, and `gzip_reader` read 16 KiB at a time from 663 to 868 ms ([[MYLA-376]]). A form over a part of a list in std.checksum would let this module call it.

### The compressor

`Deflate` is zlib's algorithm. A hash of each position's next three bytes (the top 15 bits of their product with Knuth's multiplier) heads a chain of the earlier positions with that hash, in a table of 32768 heads and one of 32768 links, by position modulo 32768. A match search walks the chain, back to 32767 bytes, as far as the level's `chain` entries (a quarter of them once a match is `good`), and stops at a match of `nice` bytes; a candidate is compared byte by byte only once its bytes at the current best length and the one before it match. Levels 1 to 3 take the longest match at each position, and put its strings into the chains only if it is short; levels 4 to 9 match lazily: a match is written only if the next position has no longer one, else its first byte is a literal and the next position's match waits in its turn. A match of three bytes more than 4096 bytes back is a literal (zlib's `TOO_FAR`). The levels' numbers are zlib's table. Unlike zlib, a chain may end at position 0, so the bytes at the very start can be matched.

A block gathers 16383 symbols (a literal, or a length and a distance, each an `int32`), counting their frequencies. Then it is written in the smallest of three forms, each costed in bits: its own Huffman codes (a dynamic block), whose code-length header is run-length coded across the two codes; the fixed codes; or stored, the block's input as it is, in pieces of 65535 bytes, which is why the input of a block is kept. The codes are optimal (two queues over the sorted frequencies) until one is longer than 15 bits (7 for the code-length code); then the lengths are moved up as JPEG's Annex K.3 does, which keeps the code complete. A code of fewer than two symbols gets a second one of length 1, so every decoder takes it.

A writer appends its input to the input it holds, byte by byte, and compresses it once it has 64 KiB more, leaving the 262 bytes a match search wants ahead of it; the end, or a flush, compresses the rest. Once the window and the block start more than 256 KiB into the input it holds, the input before them is dropped and the positions in the chains move down by the same multiple of 32768, so the links keep their places.

## Speed

Natively on x86-64, the best of five runs, decompressing 100 MB (100,000,000 bytes) of mixed text (the repository's sources, pages and tests, repeated), compressed at level 6 to 25 MB, on a machine shared with other work:

| What | Time | Speed |
| --- | --- | --- |
| `gunzip` | 757 ms | 131 MB/s |
| `zlib_decompress` | 704 ms | 142 MB/s |
| `inflate` (no checksum) | 623 ms | 160 MB/s |
| `gzip_reader` over a memory stream, reads of 64 KiB | 859 ms | 116 MB/s |
| `gzip_reader`, reads of 4 KiB | 987 ms | 101 MB/s |
| `gzip_reader(fd_stream(0))`, each `read_str(65536)` (since D177 `read`) written to the standard output, `< file.gz > /dev/null` (the whole program) | 1108 ms | 90 MB/s |
| `gzip -dc < file.gz > /dev/null` (GNU gzip 1.12, the whole program) | 635 ms | 157 MB/s |
| Python's `zlib.decompress(data, 31)` (the whole program, reading the file too) | 464 ms | 215 MB/s |

So `gunzip` is about 1.2 times as slow as `gzip -d`. Most of its time goes to the bytes of back references, a list `push` each, with its check of the capacity; the checksum takes about a tenth. A stream costs the copies a `Read` implies: the inner stream's chunks, the output of each read that isn't all the decoder had, and from a descriptor the conversions between `str` and `[uint8]`.

Compressing the same 100 MB, natively, the best of five runs, in memory (the program's own clock), against GNU gzip 1.12 (the whole program, `gzip -N -c < file > /dev/null`) and Python's `zlib.compress`:

| Level | `gzip(b, level)` | `gzip_writer`, writes of 64 KiB | `gzip -N` | `zlib.compress` | Ratio: `gzip(b, level)` | `gzip -N` |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1507 ms, 66 MB/s | 2146 ms, 47 MB/s | 1400 ms, 71 MB/s | 1110 ms, 90 MB/s | 31.07 % | 31.22 % |
| 6 | 5068 ms, 20 MB/s | 5639 ms, 18 MB/s | 3962 ms, 25 MB/s | 3451 ms, 29 MB/s | 25.30 % | 25.32 % |
| 9 | 12919 ms, 7.7 MB/s | 13513 ms, 7.4 MB/s | 10127 ms, 9.9 MB/s | 8815 ms, 11.3 MB/s | 25.11 % | 25.12 % |

So `gzip` is 1.1 times as slow as `gzip -1` and 1.3 times as slow as `gzip -6` and `-9`, and its output is a little smaller at each level. At the lazy levels most of the time goes to the chains' walks; checking the byte before the best length too took level 6 from about 650 to about 570 ms on 10 MB. A writer costs the copy of its input into the window, a `push` a byte, and the slides.

### LZW and PackBits

Natively on x86-64, the best of five runs, in memory (the program's own clock; `python3 -m tests.burn.test_lzw --bench`), on 4 MB of each: a picture (2048×2048 indices, smooth with shapes and 5 % noise), the repository's text repeated, random bytes and zeros, on a machine shared with other work (2026-11-24):

| Input | Codec | Size | Encode | Decode |
| --- | --- | --- | --- | --- |
| picture | GIF LZW | 54.5 % | 54 ms, 77 MB/s | 32 ms, 133 MB/s |
| picture | TIFF LZW | 54.5 % | 62 ms, 68 MB/s | 34 ms, 123 MB/s |
| picture | PackBits | 100.8 % | 19 ms, 225 MB/s | 6.4 ms, 655 MB/s |
| text | GIF LZW | 54.9 % | 59 ms, 68 MB/s | 34 ms, 116 MB/s |
| random | GIF LZW | 137.0 % | 66 ms, 61 MB/s | 39 ms, 102 MB/s |
| zeros | GIF LZW | 0.1 % | 28 ms, 142 MB/s | 6.6 ms, 605 MB/s |
| zeros | PackBits | 1.6 % | 4.7 ms, 851 MB/s | 4.2 ms, 951 MB/s |

Pillow on the same picture, saving and loading a file in memory (the C codecs, with Python's overhead around them): its own GIF encoder 46 ms and decoder 29 ms; libtiff's LZW 43 and 16 ms, PackBits 15 and 1.1 ms. So the LZW decoders are as fast as Pillow's GIF one and half as fast as libtiff's, which copies an entry's string with `memcpy` where this module pushes its bytes one by one. The first hash of the encoder, compress(1)'s `(byte << 5) ^ prefix`, clustered on text, whose bytes span few values: 472 ms for the text, Knuth's multiplier 59 ms.

## Tests

The module's cases are vectors made by Python's `zlib` and `gzip` and by hand (the error cases and the edge cases of incomplete and empty codes, each checked to be one Python's `zlib` accepts or rejects alike, for the same reason), and test functions for the streams: read in pieces of 1 to 100 bytes from inner streams that give 1 to 100 bytes a read, back references of 32768 bytes across the window, the bit buffer given back at a trailer, and the errors. `max_output` has cases at and one byte below each output's length, in stored and Huffman blocks, across gzip members and on 100 KB of zeros, and one below 0; a test function sums a gzip length past 2^32 ([[MYLA-423]]). With the compressor's, all 155 cases pass interpreted, natively, on aarch64 under qemu and on wasm32 under Node.

`tests/burn/test_compress.py` compresses text, random bytes, long runs and a mix of them with `gzip -1` to `-9`, `zlib.compress` at levels 0 to 9, raw DEFLATE at every level and with each strategy, smaller windows, a low memory level and several members, and decompresses each natively with the functions, as a stream, and as a stream over 1 to 13 bytes a read in reads of 1 to 997 bytes; a few interpreted. It corrupts 400 of them (a bit flipped, a byte changed or added, the data cut short) and checks that each fails where Python fails, with Python's output where it doesn't.

The compressor's cases (MYLA-352) are outputs checked against Python's `zlib` (the same bytes as zlib's where zlib's chains reach, the empty stream, stored blocks, the headers of each container), the Huffman code's lengths with and without the limit, the run-length coding of a header and the cost of a stored block; and test functions: inputs of six kinds at levels of each kind through every container and back, the sizes of the levels and of stored blocks, a writer given its input in pieces of 1 to 70000 bytes making what the functions make, and flushes. All they pass interpreted, natively, on aarch64 under qemu and on wasm32 under Node, among the module's 155 cases.

`tests/burn/test_archive.py` compresses text, random bytes, long runs, a mix of them and matches exactly 32768 bytes back (and one byte further) at every level, in each container, with the functions and with a writer given pieces of 1 to 9973 bytes, and 3 MB of text, and decompresses each with Python's `zlib`, `gzip -d` and this module; the output may be at most 2 % bigger than zlib's at the same level (it is smaller on text). It gunzips 1 GiB of zeros in 1 MB with a `max_output` of 1 MiB, in a process limited to 256 MiB of address space, built plain and `--checked`: `TooLarge`.

LZW and PackBits ([[MYLA-958]]) have cases on each function: vectors from Pillow's GIF and libtiff's TIFF encoders and by hand (a clear and an end code alone, the entry a code is about to add, no clear code first, no end code, bits after it, a code past the table and an entry right after a clear, minimum code sizes outside 1 to 8, the old LZW of TIFF 5.0, PackBits' -128, its longest repeat and runs cut short), `max_output` at and one byte below the output in a literal and in an entry's string and below 0; and test functions: inputs of six kinds and of every minimum code size from 2 to 8 through both LZWs and PackBits and back, a table that fills up without a clear (the encoder made to defer it), and GIF's LZW with 8 bits read as TIFF's old LZW. All pass interpreted, natively and on wasm32 under Node.

`tests/burn/test_lzw.py` decodes a corpus vendored in `tests/burn/data/lzw/` (`--vendor` makes it again with Pillow, ImageMagick and ffmpeg): the LZW data of GIF images by Pillow (minimum code size 8, interlaced and not) and by ImageMagick (2 to 8), and the LZW and PackBits strips of TIFF images, grey, RGB, random RGB and bilevel, by libtiff (through Pillow) and by ffmpeg; each must give the bytes those tools decode, and `TooLarge` a byte below. It encodes empty input, a byte, random bytes, 200,000 zeros, runs of 1 to 300, periodic bytes, 300 KB of the repository's text, a picture and pairs, for GIF at the minimum code sizes 2, 3, 5, 7 and 8; each must come back through this module, through a decoder written in the test from the specifications, and through Pillow inside a GIF or TIFF file it builds. It mutates the corpus 3,000 times (cut short, bits flipped, bytes changed or added, random bytes, another minimum code size, a small `max_output`): each must give what the test's decoder gives, the same bytes or the same error, built plain and `--checked` alike, never a runtime error. The encoders run interpreted too.
