# std.compress

DEFLATE decompression, and the gzip and zlib formats around it ([[MYLA-344]]). The compressor is [[MYLA-352]].

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
        match r.read_str(5) {
            Ok(s) => {
                if s.len() == 0 { break }
                print(f"[{s}]")
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
| `inflate(b: [uint8]) -> Result<[uint8], CompressError>` | The raw DEFLATE stream `b` (RFC 1951) decompressed |
| `gunzip(b: [uint8]) -> Result<[uint8], CompressError>` | The gzip data `b` (RFC 1952) decompressed: every member, one after the other. Zero bytes after a member are padding, as for `gzip` |
| `zlib_decompress(b: [uint8]) -> Result<[uint8], CompressError>` | The zlib stream `b` (RFC 1950) decompressed |

The names are the operations' usual ones; the compressor will add `deflate`, `gzip` and `zlib_compress`. A `str` read from a file is turned into bytes with `bytes.from_str` ([[Language/Standard-library/Bytes]]).

## Streams

A `Decoder<R>` is a `Read` stream ([[Language/Standard-library/Io#streams]]) of what the compressed stream `R` gives decompressed, so a file or a pipe is decompressed as it is read, in a window of 32 KiB, whatever its length. It owns its inner stream, as `buffered` does, and reads it in chunks of 32 KiB, so the inner stream is read past the end of the compressed data.

| Item | What it is |
| --- | --- |
| `inflate_reader<R: Read>(r: R) -> Decoder<R>` | Raw DEFLATE; the stream ends where DEFLATE's ends, and the bytes after it are left unread (in the decoder's chunk) |
| `gzip_reader<R: Read>(r: R) -> Decoder<R>` | gzip, member after member, to the end of `r`; anything there but another member or zero padding is `TrailingData` |
| `zlib_reader<R: Read>(r: R) -> Decoder<R>` | zlib; the stream ends where zlib's ends |
| `d.read(n)`, `d.read_str(n)` | `Read`: up to `n` bytes of the output, `[]` or `""` at its end |
| `d.read_to_end() -> Result<[uint8], CompressError>` | The rest of the output, or why it couldn't be had |
| `d.error() -> Option<CompressError>` | Why a read failed |
| `d.into_inner() -> R` | The inner stream |

`Read` gives an `IoError`, so a read of corrupt data fails with `IoError.InvalidInput`, and `error()` says what was wrong; a failure of the inner stream is its own `IoError` (and `error()` is `Io` of it). A failure stays: every later read gives it again, and output decoded before it isn't given. `read_to_end` gives the `CompressError` itself.

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

`io.copy` takes the decoder by value, so the caller's `d` can't say why it failed; a loop over `d.read_str(n)` can.

## Errors

`CompressError` is a bare enum (D168), with `message()` and `Format`; it is `Eq` (two `Io` errors are equal when their causes are). Corrupt input of every kind is one of them, never a panic or a hang.

| Variant | Meaning |
| --- | --- |
| `Truncated` | The input ended inside the stream |
| `BadHeader` | Not a gzip or zlib header: the magic bytes, a method other than DEFLATE, reserved gzip flags, zlib's header check, a window over 32 KiB |
| `PresetDictionary` | A zlib stream that needs a preset dictionary (FDICT), which this module doesn't take |
| `BadBlockType` | A block of the reserved type 3 |
| `BadStoredLength` | A stored block whose length and its complement don't match |
| `BadCodeLengths` | A dynamic block's code lengths: more than 286 or 30 codes, a repeat with nothing to repeat or past the end, lengths that over-subscribe a code, or leave it incomplete but for a single code of length 1, no code for the end of the block. A distance code with no lengths at all is allowed: its block has only literals |
| `BadCode` | Bits that aren't a code of the block, or a symbol DEFLATE doesn't define (lengths 286 and 287, distances 30 and 31) |
| `DistanceTooFar` | A distance back past the start of the output (of the member, for gzip) |
| `ChecksumMismatch` | The CRC-32 (gzip) or Adler-32 (zlib) of the output, or gzip's header CRC, isn't the stream's |
| `LengthMismatch` | The output's length isn't the one the gzip trailer gives (modulo 2^32) |
| `TrailingData` | Bytes after the end of the stream |
| `Io(IoError)` | The inner stream failed |

The rules are zlib's, so `gzip`, Python's `zlib` and this module accept and reject the same streams: the burn test checks 400 corrupted ones, each read three ways. Python's `gzip` module alone is more lenient: it ignores the header's CRC and its reserved flags. A gzip header's fields (name, comment, time, extra field) are checked as far as they have checks and skipped.

## How it works

One decoder does the work. It is given compressed bytes and decodes as far as they go: until the output it was asked for is there, the input runs out, or the stream ends. It stops only at a symbol's boundary, so a stream can be cut anywhere: before a symbol it waits for 48 bits, the most a length and a distance take, unless the input has ended, and before a block's header for 1024 bytes, more than a dynamic header takes. The functions give it all their input at once; a `Decoder` gives it each chunk its inner stream reads.

The output is a list the decoder appends to. A back reference copies from it, byte by byte, as a match may overlap itself. A stream hands the list out whole when it is read whole (no copy), and keeps it as the window if it holds 32 KiB, else copies its bytes into a ring of 32 KiB; a back reference that reaches before the list reads the window. The functions never hand the list out, so they keep everything and need no window.

Huffman codes are decoded with a table indexed by the next 10 bits: an entry gives the symbol and its length. A longer code (up to 15 bits) is decoded bit by bit from the code's counts, as `puff` does. The table pays: natively, `gunzip` of the benchmark below takes 1157 ms with no table (every code bit by bit), and with a table of 8, 9, 10 or 11 bits 744, 757, 735 and 746 ms. The widths differ by less than the noise; 10 bits is the fastest, and leaves few codes to the slow path.

CRC-32 and Adler-32 are std.hash's algorithms ([[Language/Standard-library/Hash#the-checksums]]), written here for now over a part of the output, with the CRC's tables kept in the decoder. A module of `std` that imports std.hash can't run its cases natively ([[MYLA-360]]), and the checksums move to a module of their own ([[MYLA-359]], D166), which this module will call.

## Speed

Natively on x86-64, the best of five runs, decompressing 100 MB (100,000,000 bytes) of mixed text (the repository's sources, pages and tests, repeated), compressed at level 6 to 25 MB, on a machine shared with other work:

| What | Time | Speed |
| --- | --- | --- |
| `gunzip` | 757 ms | 131 MB/s |
| `zlib_decompress` | 704 ms | 142 MB/s |
| `inflate` (no checksum) | 623 ms | 160 MB/s |
| `gzip_reader` over a memory stream, reads of 64 KiB | 859 ms | 116 MB/s |
| `gzip_reader`, reads of 4 KiB | 987 ms | 101 MB/s |
| `gzip_reader(fd_stream(0))`, each `read_str(65536)` written to the standard output, `< file.gz > /dev/null` (the whole program) | 1108 ms | 90 MB/s |
| `gzip -dc < file.gz > /dev/null` (GNU gzip 1.12, the whole program) | 635 ms | 157 MB/s |
| Python's `zlib.decompress(data, 31)` (the whole program, reading the file too) | 464 ms | 215 MB/s |

So `gunzip` is about 1.2 times as slow as `gzip -d`. Most of its time goes to the bytes of back references, a list `push` each, with its check of the capacity; the checksum takes about a tenth. A stream costs the copies a `Read` implies: the inner stream's chunks, the output of each read that isn't all the decoder had, and from a descriptor the conversions between `str` and `[uint8]`.

## Tests

The module's cases are vectors made by Python's `zlib` and `gzip` and by hand (the error cases and the edge cases of incomplete and empty codes, each checked to be one Python's `zlib` accepts or rejects alike, for the same reason), and test functions for the streams: read in pieces of 1 to 100 bytes from inner streams that give 1 to 100 bytes a read, back references of 32768 bytes across the window, the bit buffer given back at a trailer, and the errors. All 92 cases pass interpreted, natively, on aarch64 under qemu and on wasm32 under Node.

`tests/burn/test_compress.py` compresses text, random bytes, long runs and a mix of them with `gzip -1` to `-9`, `zlib.compress` at levels 0 to 9, raw DEFLATE at every level and with each strategy, smaller windows, a low memory level and several members, and decompresses each natively with the functions, as a stream, and as a stream over 1 to 13 bytes a read in reads of 1 to 997 bytes; a few interpreted. It corrupts 400 of them (a bit flipped, a byte changed or added, the data cut short) and checks that each fails where Python fails, with Python's output where it doesn't.
