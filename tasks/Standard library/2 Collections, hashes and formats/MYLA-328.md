---
id: MYLA-328
title: "std.digest: MD5, SHA-1, SHA-2 and HMAC"
type: feature
status: done
priority: medium
labels: [stdlib, hashing, wave-2]
---
Wave 2 of [[Project/Standard-library-roadmap]], roadmap #35, #36. Message digests, one-shot and incremental (`new`, `update`, `finish`), as bytes and as hex. AoC's MD5 dominated three of its six slowest days, so speed counts.

- **Owns:** `lib/std/digest.my`, `docs/Language/Standard-library/Digest.md`
- **Needs:** nothing; it can start as soon as its wave does
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] MD5 and SHA-1
- [x] SHA-256 and SHA-512
- [x] HMAC over any of them
- [x] Checked against the NIST and RFC vectors
- [x] MD5 throughput measured against AoC's `md5.my` and `md5sum`; the 2016 Day 5 workload (a few million short hashes) timed
- [x] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [x] Its page below [[Language/Standard-library]], with a doc block that runs

## Evidence

- **API** ([[Language/Standard-library/Digest]]): the types `Md5`, `Sha1`, `Sha256` (also SHA-224), `Sha512` (also SHA-384), started by `new_md5()`, `new_sha1()`, `new_sha224()`, `new_sha256()`, `new_sha384()`, `new_sha512()` (no static methods, so `new()` is a function per type), with `update(data: [uint8])`, `update_str(s: str)`, `finish() -> [uint8]`, `finish_hex() -> str`, `block_size() -> int`; the one-shots `md5`, `sha1`, `sha224`, `sha256`, `sha384`, `sha512` (bytes) and their `_hex` forms (a string in, hex out); the trait `Digest` and `hmac<D: Digest>(d, key, msg)`, with `hmac_md5`, `hmac_sha1`, `hmac_sha256`, `hmac_sha512` and their `_hex` forms. Hex is a private `hex_of` here until std.encoding ([[MYLA-329]]) exists.
- **Tests first:** with the compression functions stubbed, 41 of the 48 cases failed; the module now has 62 cases (RFC 1321's seven, FIPS 180's `""`, `"abc"`, 448 and 896 bits for SHA-1, -224, -256, -384, -512, RFC 2202's cases 1, 3, 4, 6, 7 and RFC 4231's 1, 2, 3, 4, 6, 7, pieces of every size through both `update`s). `myla test lib/std/digest.my`: 62/62 passed interpreted, with `--native`, `--target aarch64-linux` (qemu) and `--target wasm32-wasi` (node). `tests.burn.test_std_modules` and `tests.burn.test_doc_blocks` pass after a bootstrap.
- **Against hashlib:** all six digests and the six HMACs of every length 0 to 200 (two input paths for the digests), and one million `a`s fed in pieces of 1000 for MD5, SHA-1, SHA-256 and SHA-512: 2416 lines, identical to Python's interpreted (1 min 40 s), natively (30 ms), on aarch64 and on wasm32.
- **Speed** (native x86-64, a shared 2.1 GHz Xeon, best of five; 100 MB through `update` of a 1 MB buffer):

  | | std.digest | coreutils | AoC's `md5.my` |
  | --- | --- | --- | --- |
  | MD5 | 287 MB/s | 690 MB/s | 178 MB/s (1 MB strings) |
  | SHA-1 | 305 MB/s | 1470 MB/s (SHA-NI) | |
  | SHA-256 | 171 MB/s | 1340 MB/s (SHA-NI) | |
  | SHA-512 | 214 MB/s | 670 MB/s | |
  | 2016 Day 5: 2 million `md5_hex(f"abc{i}")` | 730 ms | | 1275 ms (`md5_hex`), 1200 ms (a reused hasher) |

  Python's `hashlib` takes 1100 ms for the 2 million; the f-strings alone 50 ms. What the tuning was worth (callgrind instructions and timings): rotations written so no operator has two compound operands, MD5 +5 to 10 %, SHA-1 +10 %, SHA-256 +25 % (with the rotations as shifts of the word doubled to 64 bits), SHA-512 +10 to 20 %; hex from the state words instead of a list of bytes, −10 % of the instructions of a short hash. SHA-512's rounds call small functions instead of being unrolled, which keeps the module at 2700 lines (121 KB) instead of 6700 (183 KB).
- **Found:** under register pressure the x86-64 allocator keeps the left operand of `(x << 7u32) | (x >> 25u32)` in a stack cell while it computes the right one, rather than spilling a long-lived local; small functions the compiler inlines keep their parameters in stack slots (SHA-256's `compress` had a 5.7 KB frame that way). Both cost speed only.

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]].
