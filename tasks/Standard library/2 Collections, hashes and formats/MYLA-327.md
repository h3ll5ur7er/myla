---
id: MYLA-327
title: "std.hash: the Hasher, fast hashes and checksums"
type: feature
status: done
priority: medium
labels: [stdlib, hashing, wave-2]
---
Wave 2 of [[Project/Standard-library-roadmap]], roadmap #33, #34. The hashing that `Hash` (D163, [[MYLA-313]]) builds on, and the checksums that compression needs.

- **Owns:** `lib/std/hash.my`, `docs/Language/Standard-library/Hash.md`
- **Needs:** nothing; it can start as soon as its wave does
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] `Hasher`: a small value with `add` for each primitive type and `finish() -> uint64`; the algorithm (wyhash or a SipHash-1-3) chosen by measurement, with a fixed seed for now
- [x] FNV-1a 32 and 64 and the hasher's algorithm over a `str` or `[uint8]`
- [x] CRC-32 (table-driven) and Adler-32, checked against published vectors
- [x] Throughput on 100 MB measured natively
- [x] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [x] Its page below [[Language/Standard-library]], with a doc block that runs

## Evidence

- **The API** ([[lib/std/hash.my]], [[Language/Standard-library/Hash]]): `new()`, `with_seed(seed)`, a `Hasher { state: uint64 }` with `add_u64`, `add_u8` … `add_i64`, `add_bool`, `add_char`, `add_str`, `add_bytes` (each `-> Hasher`) and `finish() -> uint64`; `wyhash(s, seed)`, `fnv1a32(s)`, `fnv1a64(s)`, `crc32(s)`, `crc32_update(crc, s)`, `adler32(s)`, `adler32_update(adler, s)`, each with a `_bytes` form over `[uint8]`.
- **Tests first:** with the cases written over stubs, `build/myla test lib/std/hash.my --stdlib lib` gave `2/66 passed` (interpreted and `--native`). Now `82/82 passed` interpreted, with `--native`, with `--target aarch64-linux` (qemu) and `--target wasm32-wasi` (Node). After `scripts/bootstrap.sh`, `python3 -m unittest tests.burn.test_std_modules tests.burn.test_doc_blocks`: `Ran 6 tests … OK`.
- **Vectors:** CRC-32 `"123456789"` → `0xCBF43926`, Adler-32 `"Wikipedia"` → `0x11E60398`, FNV's reference values, the seven wyhash vectors of Zig's tests; the rest from a model in Python checked against those and against the reference SipHash's 64 vectors, and from Python's `zlib`.
- **The choice, by measurement** (natively, best of three; both written alike in Myla): one `uint64` key 6.1 ns with wyhash against 14.0 ns with SipHash-1-3, two 9.2 against 18.2 ns, a 13-byte string 16.4 against 20.5 ns, 100 MB 1533 against 1275 MB/s. wyhash it is; the page gives the reasoning.
- **Throughput on 100 MB**, natively, best of five (`str` / `[uint8]`): FNV-1a 32 953 / 952 MB/s, FNV-1a 64 933 / 948 MB/s, the Hasher (wyhash) 1496 / 1496 MB/s, CRC-32 (slicing by 8) 1167 / 1084 MB/s, Adler-32 1329 / 1335 MB/s. A key of two `int32`s 8.7 ns from `new()` to `finish()`, a 13-byte string 16.1 ns. CRC-32 a byte at a time was 415 MB/s.

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]].
