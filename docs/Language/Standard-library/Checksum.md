# std.checksum

FNV-1a, CRC-32 and Adler-32 ([[MYLA-327]]). They were std.hash's until [[MYLA-359]] moved them here (D166): std.hash is in every program, as the `Hash` trait builds on it, and a program that wants a checksum imports this module. It imports nothing.

```myla
import std.checksum as checksum

fun main() {
    print(f"{checksum.fnv1a64("foobar"):#x}")
    let crc = checksum.crc32_update(checksum.crc32("1234"), "56789")
    print(f"{crc:#x} {checksum.adler32("Wikipedia"):#x}")
}
// output:
// 0x85944171f73967e8
// 0xcbf43926 0x11e60398
```

Every function takes a `str`, and its `_bytes` form a `[uint8]`; the two give the same result for the same bytes.

| Function | Result |
| --- | --- |
| `fnv1a32(s) -> uint32`, `fnv1a32_bytes(b)` | FNV-1a, 32 bits |
| `fnv1a64(s) -> uint64`, `fnv1a64_bytes(b)` | FNV-1a, 64 bits |
| `crc32(s) -> uint32`, `crc32_bytes(b)` | CRC-32 as zlib, gzip, PNG and zip compute it |
| `crc32_update(crc: uint32, s) -> uint32`, `crc32_update_bytes(crc, b)` | The CRC of more bytes: start from 0, and `crc32_update(crc32(a), b)` is `crc32(a + b)` |
| `adler32(s) -> uint32`, `adler32_bytes(b)` | Adler-32 as zlib computes it (RFC 1950) |
| `adler32_update(adler: uint32, s) -> uint32`, `adler32_update_bytes(adler, b)` | Start from 1, not 0; `adler32_update(adler32(a), b)` is `adler32(a + b)` |

None of these is cryptographic; [[MYLA-328]]'s `std.digest` has the cryptographic hashes, and std.hash the `Hasher` and wyhash.

## How they work

FNV-1a xors each byte into the state and multiplies by the prime (Fowler, Noll and Vo's), 32 or 64 bits: simple and short, but a byte at a time, so slower than wyhash on long input.

CRC-32 is CRC-32/ISO-HDLC, the one of zlib, gzip, PNG, zip and Ethernet: the reflected polynomial `0xEDB88320`, the register started at and xored with `0xFFFFFFFF`, so `crc32("123456789")` is `0xCBF43926`. It's table-driven. From 2048 bytes on it reads eight bytes at a time ("slicing by 8"), with seven more tables derived from the first when the call starts; below that, one table, a byte at a time.

Adler-32 is zlib's, so `adler32("Wikipedia")` is `0x11E60398`. It reduces its two sums modulo 65521 once every 5552 bytes, the most after which they still fit 32 bits. Note the different starting values of the incremental forms, as in zlib: 0 for `crc32_update`, 1 for `adler32_update`.

## Speed

Natively on x86-64, the best of five runs over 100 MB (100,000,000 bytes), on a machine shared with other work (measured in std.hash, [[MYLA-327]]):

| Function | `str` | `[uint8]` |
| --- | --- | --- |
| `fnv1a32` | 953 MB/s | 952 MB/s |
| `fnv1a64` | 933 MB/s | 948 MB/s |
| `crc32` | 1167 MB/s | 1084 MB/s |
| `adler32` | 1329 MB/s | 1335 MB/s |

A CRC-32 of a short string takes about 60 ns, most of it building the table, which Myla can't keep in a constant. Every byte is read with a bounds check, which bounds all of these: FNV-1a's chain of multiplications is the slowest. std.compress keeps its own CRC-32 and Adler-32 over a range of a list, as these take a whole one ([[MYLA-376]]).

## Tests

The vectors are published ones: FNV's reference values, the CRC-32 check value and zlib's results; a model of FNV-1a in Python gives the rest. Test functions check that the `str` and `[uint8]` forms agree at every length up to 130 and over 10,000 bytes, that an incremental checksum doesn't depend on how the input is split, that the fast paths agree with the byte-at-a-time ones, and that the CRC table is the register after each byte computed bit by bit.
