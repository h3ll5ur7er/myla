---
id: MYLA-352
title: DEFLATE compression and archives
type: feature
status: done
priority: low
labels: [stdlib, compression, wave-4]
---
Wave 4 of [[Project/Standard-library-roadmap]], roadmap #50, #51. The compressor after the decompressor, then tar and zip.

- **Owns:** `lib/std/compress.my` (the compressor), `lib/std/archive.my`, `docs/Language/Standard-library/Archive.md`
- **Needs:** [[MYLA-344]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] Deflate with LZ77 matching and dynamic Huffman codes, levels from fast to small, round-tripped through `gzip`
- [x] tar read and write; zip read
- [x] Ratio and speed against `gzip -1`, `-6` and `-9`
- [x] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [x] Its page below [[Language/Standard-library]], with a doc block that runs

## Evidence

- **API** ([[Language/Standard-library/Compress#compressing]]): `deflate`, `gzip`, `zlib_compress` (`(b: [uint8], level: int = 6) -> [uint8]`, levels 0 to 9, below 0 the default); `deflate_writer`, `gzip_writer`, `zlib_writer` (`<W: Write>(w: W, level: int = 6) -> Encoder<W>`), a `Write` whose `flush` is a sync flush, with `finish() -> Result<W, IoError>`. The decompressor is unchanged.
- **API** ([[Language/Standard-library/Archive]]): `Entry`, `EntryKind`, `file`, `dir`, `symlink`; `tar_read`, `tar_reader` (an `Iterator<Result<Entry, ArchiveError>>`), `tar_write`, `tar_writer` (`add`, `finish`); `zip_read`, `zip_list`, `zip_data`, `ZipFile`; `is_safe_name`, `safe_path`; `ArchiveError`, a bare enum (D168) with `message()`, `Format`, `Eq`. Long tar names go in pax `path` records (POSIX.1-2001, as Python's `tarfile` writes them); reading also takes GNU's `L`/`K`.
- **How:** zlib's algorithm: hash chains over a 32 KiB window, greedy at levels 1 to 3, lazy at 4 to 9, zlib's level table; blocks of 16383 symbols written dynamic, fixed or stored, whichever is smallest; Huffman lengths by two queues, limited to 15 (7) bits as JPEG's Annex K.3 does. Unlike zlib, a chain may reach position 0.
- **Tests first:** the cases were written with the code; their first run failed 6 of 134 (compress) and 6 of 86 (archive), each a hand-made expectation that was wrong (among them the run of 300 bytes, where this compressor is a byte smaller than zlib, which can't match position 0). The burn test's first run failed on two real differences: Python's `zipfile` takes a deflate entry whose stream doesn't end, if its CRC is right (the reference now asks for a whole stream, as std.archive does), and GNU tar warns about a time before 1970.
- **Module cases:** compress 139/139 (the decompressor's 92 and 47 new), archive 86/86 (136 and 83 on `95785ab`, after [[MYLA-376]] replaced the modules' private helpers and their cases), each interpreted, natively, on aarch64 under qemu and on wasm32 under Node (`MYLA_EMULATOR="node tools/wasm/run.mjs"`).
- **Burn test** `tests/burn/test_archive.py`, 7 tests in 51 s: 7 inputs (one with matches exactly 32768 bytes back) at levels 0 to 9 in three containers, whole and through a writer in pieces, decompressed by Python's `zlib`, `gzip -d` and std.compress, at most 2 % bigger than zlib; 3 MB through the writer (the window slides); tar files from GNU tar 1.35 (gnu, posix, ustar, v7) and `tarfile` (GNU, PAX, USTAR), plain and gzipped, and zip files from `zipfile` (stored, deflated 0 to 9) and `zip -0/-6/-9`, each listed as Python lists it; a tar written (and gzipped at four levels) that `tarfile` reads and `tar -x` extracts; 60 corrupted zip entries failing where Python fails.
- `python3 -m unittest tests.burn.test_std_modules tests.burn.test_doc_blocks` after a bootstrap: OK (and `tests.burn.test_compress`, `tests.burn.test_embedded_std`).
- **Speed and ratio**, natively, best of five, 100 MB of mixed text (the repository's sources and pages repeated), in memory against the whole `gzip -N -c` program: level 1 1507 ms (66 MB/s, 31.07 %) against `gzip -1` 1400 ms (31.22 %); level 6 5068 ms (20 MB/s, 25.30 %) against 3962 ms (25.32 %); level 9 12919 ms (7.7 MB/s, 25.11 %) against 10127 ms (25.12 %). `gzip_writer` in writes of 64 KiB: 2146, 5639 and 13513 ms, the same bytes.


## Review 2026-11-09

Not ready ([[Project/Review-2026-11-09]]): `tar_read` overflows on a pax number of 20 digits; uid/gid of 2^31 or more read negative. The fix is in [[MYLA-423]].

- [x] The review's blocker, fixed with [[MYLA-423]]

## Review 2026-11-12

Signed off in [[Project/Review-2026-11-12]].
