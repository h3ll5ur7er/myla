---
id: MYLA-344
title: "std.compress: DEFLATE decompression, gzip and zlib"
type: feature
status: done
priority: low
labels: [stdlib, compression, streams, wave-3]
---
Wave 3 of [[Project/Standard-library-roadmap]], roadmap #49. Decompression first: it is smaller than the compressor, and reading archives and HTTP bodies needs it.

- **Owns:** `lib/std/compress.my`, `docs/Language/Standard-library/Compress.md`
- **Needs:** [[MYLA-327]], [[MYLA-338]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] Inflate (stored, fixed and dynamic Huffman blocks) as a `Read` adapter
- [x] gzip and zlib containers with their checksums
- [x] Checked against files made by `gzip` and Python's `zlib` at every level
- [x] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [x] Its page below [[Language/Standard-library]], with a doc block that runs

## Evidence

- **API** ([[Language/Standard-library/Compress]]): `inflate`, `gunzip`, `zlib_decompress` (`[uint8] -> Result<[uint8], CompressError>`); `inflate_reader`, `gzip_reader`, `zlib_reader` (`R: Read -> Decoder<R>`), a `Read` with `read_to_end`, `error` and `into_inner`; `CompressError`, a bare enum (D168) with `message()`, `Format` and a written `Eq`.
- **Private helper:** CRC-32 and Adler-32 are std.hash's algorithms, written in [[lib/std/compress.my]] for now (`crc32_part`, `adler32_part`). A module of `std` that imports std.hash can't run its cases with `--native`: the harness copies std.hash's cases on the built-in types by byte spans (the native form of [[MYLA-360]]). The integrator switches to std.hash, or [[MYLA-359]]'s module.
- **Tests first:** the cases were written before the fixes they found: the fixed distance codes 30 and 31 read as `Truncated` (one case failed); a header error through a stream left `error()` empty, and output decoded before a failure was handed out after it (the burn test and a test function); dynamic blocks without distance codes, and incomplete codes zlib rejects (3 of 92 failed).
- **Module cases:** 92/92 interpreted, natively, on aarch64 under qemu and on wasm32 under Node (`MYLA_EMULATOR="node tools/wasm/run.mjs"`).
- **Burn test** `tests/burn/test_compress.py`: 6 inputs at every level and variant (234 compressed files) and 4 MB of text, each decompressed three ways natively; 400 corrupted files, three ways each, against Python's zlib; a few interpreted. OK in 28 s. Three sweeps of 3000 more corrupted files each (27,000 runs) gave no disagreement.
- `python3 -m unittest tests.burn.test_std_modules tests.burn.test_doc_blocks` after a bootstrap: OK.
- **Speed**, natively, best of five, 100 MB of mixed text at level 6: `gunzip` 131 MB/s, `zlib_decompress` 142 MB/s, `inflate` 160 MB/s, `gzip_reader` over a memory stream 116 MB/s; `gzip -dc` 157 MB/s on the same machine. A first table of 10 bits against none: 735 against 1157 ms.


## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]].
