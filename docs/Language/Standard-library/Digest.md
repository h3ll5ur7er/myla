# std.digest

Message digests ([[MYLA-328]]): MD5 (RFC 1321), SHA-1, SHA-224, SHA-256, SHA-384 and SHA-512 (FIPS 180-4), and HMAC (RFC 2104) over any of them. A digest takes bytes and gives bytes; the `_hex` functions take a string's bytes and give lower-case hex. MD5 and SHA-1 are broken as signatures: use them for checksums, Git's object ids and puzzles, SHA-256 or SHA-512 for anything an attacker chooses.

```myla
import std.digest as digest

fun main() {
    print(digest.md5_hex("abc"))
    print(digest.sha256_hex("abc"))

    // in pieces: the same digest
    var h = digest.new_sha1()
    h.update_str("ab")
    h.update([99u8])
    print(h.finish_hex())

    print(digest.hmac_sha256_hex("key", "The quick brown fox jumps over the lazy dog"))
    let raw = digest.md5([97u8, 98u8, 99u8])
    print(f"{raw.len()} bytes, the first {raw[0]}")
}
// output:
// 900150983cd24fb0d6963f7d28e17f72
// ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
// a9993e364706816aba3e25717850c26c9cd0d89d
// f7bc83f430538424b13298e6aa6fb143ef4d59a14946175997479dbc2d1a3cd8
// 16 bytes, the first 144
```

## Hashers

Each digest is a type, started by a function (Myla has no static methods): `new_md5() -> Md5`, `new_sha1() -> Sha1`, `new_sha256() -> Sha256`, `new_sha224() -> Sha256`, `new_sha512() -> Sha512`, `new_sha384() -> Sha512`. A hasher is a value: copying one copies what it has taken in, so two messages with a common prefix can share its work.

| Method | Meaning |
| --- | --- |
| `h.update(data: [uint8])` | Adds the bytes; needs a `var` place |
| `h.update_str(s: str)` | Adds the bytes of `s`; needs a `var` place |
| `h.finish() -> [uint8]` | The digest of everything added so far; `h` itself doesn't change, so it can take more |
| `h.finish_hex() -> str` | The same in lower-case hex |
| `h.block_size() -> int` | The block HMAC pads its key to: 64 bytes, 128 for SHA-384 and SHA-512 |

The trait `Digest` has `update`, `finish` and `block_size`, and all four types implement it: a generic function over digests takes a `D: Digest`.

`compress` and `close`, methods of each hasher, are its own steps (a block taken in; the padding `finish` gives a copy), public only because a method can't be private yet ([[MYLA-433]]); a program has no need of them.

## One-shot functions

| Function | Result |
| --- | --- |
| `md5(data: [uint8]) -> [uint8]`, `md5_hex(s: str) -> str` | 16 bytes, 32 hex digits |
| `sha1(data)`, `sha1_hex(s)` | 20 bytes |
| `sha224(data)`, `sha224_hex(s)` | 28 bytes |
| `sha256(data)`, `sha256_hex(s)` | 32 bytes |
| `sha384(data)`, `sha384_hex(s)` | 48 bytes |
| `sha512(data)`, `sha512_hex(s)` | 64 bytes |

## HMAC

| Function | Result |
| --- | --- |
| `hmac(d: D, key: [uint8], msg: [uint8]) -> [uint8]` | The HMAC of `msg` under `key` with the digest of `d`, a new hasher (`D: Digest`): `hmac(new_sha384(), key, msg)`. A key longer than the block is hashed first |
| `hmac_md5(key, msg)`, `hmac_sha1`, `hmac_sha256`, `hmac_sha512` | `hmac` with that digest |
| `hmac_md5_hex(key: str, msg: str) -> str`, `hmac_sha1_hex`, `hmac_sha256_hex`, `hmac_sha512_hex` | The same of two strings' bytes, in hex |

## Speed

Advent of Code's own MD5 dominated three of its six slowest days ([[Project/AoC-2015-2021]]), so the module is tuned for the native code generator as it is: a hasher keeps one block of 16 words and allocates nothing per block, MD5's, SHA-1's and SHA-256's rounds are unrolled onto locals, and no operator in them has two compound operands, which the code generator would keep one of on the stack. Measured natively on x86-64 (a shared 2.1 GHz Xeon, best of five), 100 MB through `update` and the 2016 Day 5 workload of 2 million `md5_hex(f"abc{i}")`:

| | std.digest | coreutils | AoC's `md5.my` |
| --- | --- | --- | --- |
| MD5 | 287 MB/s | 690 MB/s | 178 MB/s |
| SHA-1 | 305 MB/s | 1470 MB/s (SHA-NI) | |
| SHA-256 | 171 MB/s | 1340 MB/s (SHA-NI) | |
| SHA-512 | 214 MB/s | 670 MB/s | |
| 2 million short MD5s, in hex | 730 ms | | 1200 ms |

Python's `hashlib` takes 1100 ms for the 2 million short MD5s; the f-strings alone take 50 ms. Of the instructions left, about a third are the compression and a third the hex digits.
