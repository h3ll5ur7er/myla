---
id: MYLA-428
title: "P14 Standard library helpers, round two"
type: improvement
status: review
priority: low
labels: [std, cleanup, round-5]
---
Work package P14 of [[Project/Review-2026-11-09]] (wave B, after wave A: it touches twenty modules wave A edits). Follow-up of [[MYLA-376]].

- [x] `holds` ×5 (a workaround for a bug [[MYLA-355]] fixed)
- [x] `is_some_of`, `is_none` and `same` in deque, heap, random and set
- [x] `hex_digit` ×6, `unhex` ×3, `hex_of` ×3; `is_digit`, `digit_value`, `utf8_len`, `find_byte`
- [x] std.toml's private `utf8_error`; std.compress's own CRC-32 and Adler-32

MYLA-376's rule, applied to each copy: it goes where the library's version behaves the same and isn't slower on a hot path; it stays, with a comment saying why, where it differs, where it works around a language limit, or where the import costs a lot for little. Each swap that touched a loop was measured, and four that looked harmless were slower and went back.

## What changed

| Helper | Where | Removed or kept | Why |
| --- | --- | --- | --- |
| `holds` | char, int (and `scripts/gen_std_int.py`), io, process, regex | removed: `assert` | MYLA-355 is fixed: `assert(c, f"…")` and `assert(c, "x" + t)` build and run interpreted, natively, on aarch64 and on wasm32 |
| `same` | deque, heap, random, set | removed: `==` | lists of `Eq` elements compare (D163) |
| `is_some_of`, `is_none` | deque, heap, random | removed: `o == Some(v)`, `o == None` | an `Option` of `Eq` compares ([[MYLA-379]]); simpler than importing std.option for `is_none()` |
| `hex_digit` | net | removed: `to_digit(16)` | an IPv6 address's groups, nothing hot; importing std.char costs no measurable check time |
| `hex_digit` | archive, compress | removed: `to_digit(16)` | the tests' `unhex` |
| `hex_digit` | url | kept | `to_digit` took `percent_decode` 29 % longer and `parse` 35 % |
| `hex_digit` | digest | kept | the other direction (a value to its digit), branch-free, eight per word of every hex digest; `from_digit` is a call and an `Option` |
| `hex_digit` | encoding | kept | the library's own: `hex_decode`'s |
| `hex_value` (regex's `hex_digit`) | regex | kept | with std.char's, compiling a pattern took 10 % longer |
| `unhex` | archive, compress, net | kept | test helpers; std.encoding's `hex_decode` would be checked by every importer for the tests' sake (+3 ms for std.compress) |
| `hex_of` | digest, fs, net | kept | std.encoding's `hex_encode` costs every importer: +4 ms for std.digest, +2.5 ms for every program using std.io (fs's); net's is a test helper |
| `is_digit` | fmt | kept | `parse_spec` runs at every formatted hole: 300,000 formats took 2 to 3 % longer with std.char's |
| `is_digit` | regex | kept | `replace_all`'s `$1` took 6 % longer with std.char's |
| `is_digit`, `digit_value` | toml | kept | a document of numbers took 5 % longer to parse with std.char's |
| `is_digit` | yaml | kept | a call per byte of every plain scalar resolved, as toml's |
| `digit_value` | num, bigint | kept | `to_digit` took `parse_uint64` 70 % longer |
| `utf8_len` | term, xml | kept | nothing in std gives a sequence's length from its lead byte; term's gives 0 for a byte that leads none, xml's assumes a checked one |
| `find_byte` | args | removed: `find`, `contains` | argv is parsed once; the old comment's MYLA-360 is fixed |
| `find_byte` | http | kept | with std.str's `find_from` (and a `match` for the token bytes), a request's parse took 7.8 % more instructions |
| `utf8_error` | toml | removed: std.bytes' | the same rules (no overlong forms, surrogates or code points past U+10FFFF); +1 ms on a 4.9 MB document (8.1 → 9.2 ms of 1,150) |
| `crc32_part`, `adler32_part` | compress | kept | std.checksum's take a whole list and make the tables each call: `gunzip` of 36 MB from 253 to 372 ms |

Only a function of the caller's module is inlined ([[Architecture/IR]]), so a per-byte test from std.char is a call each time; [[Development/Conventions]] now says so, with the numbers.

## Evidence

- **MYLA-355 is fixed.** A program with `assert(t != "b", f"'{t}' {n}")`, `assert(n == 3, "x" + t)` and a failing `assert(n == 4, f"n is {n}, not 4")` prints `ok`, then `runtime error: n is 3, not 4`, exit 1, interpreted, natively, on aarch64 (qemu) and on wasm32 (Node). A `#test` function whose `assert` fails is a `FAIL` under `myla test` and `--native`.
- **toml's UTF-8 test.** `finds_bad_utf8` called the private `utf8_error`; it now parses `x = "…"` around each bad sequence and expects `invalid UTF-8` from `parse`, so it tests the module's behaviour.
- **Cases**, interpreted and `--native` (which checks overflow as `run` does; `myla test` has no `--checked`), before → after: char 82, int 1826, io 30, process 48, regex 1967, deque 18, heap 8, random 41, set 7, archive 112, compress 155, digest 62, url 169, fs 74, fmt 34, yaml 197, bigint 138, num 189, term 102, xml 90, http 221, all passing as before; net 101 → 98, args 46 → 43, toml 170 → 168 (the removed helpers' own cases). `--target aarch64-linux` (qemu) and `--target wasm32-wasi` (Node): char, int, io, process, regex, deque, heap, random, set, archive, compress, net, args and toml pass on both.
- **Check time** (CPU time of `myla check`, min of 21 runs, the two libraries alternating, the machine shared with three lanes), before → after: a hello world with std.io 27.6 → 27.7 ms; a program importing std.http 119.5 → 118.9; std.toml 35.7 → 36.6 (std.bytes); std.args 49.2 → 49.7; std.net 49.1 → 47.9; std.compress 52.0 → 51.8; std.archive 74.7 → 74.5; std.deque 12.9 → 12.8; std.regex 26.8 → 26.7; std.process 39.6 → 39.6. Importing std.char cost nothing measurable (std.net 50.3 → 49.7, std.url 15.7 → 15.5, std.regex 28.7 → 28.7, min of 11); importing std.encoding did (std.compress 53.0 → 56.0, std.digest 63.2 → 67.2, hello world through std.fs 28.6 → 31.1).
- **Hot paths**, natively, best of 3 to 9 repetitions, the builds run alternately:
  - std.compress with std.checksum's CRC-32 and Adler-32 (rejected): `gunzip` of 36 MB (the seed and the sources twice; 5.7 MB of gzip) 250–262 → 367–381 ms, `zlib_decompress` 236–244 → 361–366, `gzip_reader` in 16 KiB reads 285–294 → 365; `gzip_writer` and `zlib_writer` in 16 KiB writes (8 MB, level 1) 102–111 → 106–111 and 100–103 → 101–103.
  - std.toml with std.bytes' `utf8_error` (kept): `parse` of a 4.9 MB document 1115–1168 → 1147–1190 ms; the check alone 8.1 → 9.1–9.4 ms.
  - std.toml with std.char's `is_digit` and `to_digit` (rejected): a 5.1 MB document of integer arrays and dates 295–303 → 311–317 ms.
  - std.url with `to_digit` (rejected): `percent_decode` of 4.8 MB 22.4 → 28.8 ms, `parse` of 9.6 MB 60 → 82 ms.
  - std.num with `to_digit` (rejected): a million `parse_uint64` 73–78 → 131–133 ms, `parse_int_radix(s, 16)` 109 → 142–144.
  - std.http with `find_from` (rejected): 100,000 `parse_request` of a chunked request with ten headers 596–600 → 600–608 ms; callgrind 968.9 M → 1,044.3 M instructions on 20,000 (`find_from` 177.7 M where `find_byte` was 154.4 M, plus `matched` and `unwrap_or`).
  - std.fmt with `is_digit` (rejected): 300,000 `f"{i:08x} {x:>12.3}"` 777–784 → 791–808 ms; with the copy back 774–779.
  - std.regex with std.char's (rejected): `replace_all` of 200,000 matches with `$2-$1` 305–311 → 325–330 ms, 20,000 compiles 181–191 → 201–204; with the copies back 306–311 and 182–184.
- `python3 scripts/gen_std_int.py --check`: current (its template's `holds` went too).
- `scripts/bootstrap.sh` (std.toml, std.fs, std.io, std.process and std.num are the compiler's): byte-identical fixed point, 21,013,000 bytes; `selfhost/embedded_std.my` restored after it.
- `scripts/test.sh fast`: 837 tests, two failures, `test_embedded_std` and `test_installed`'s `test_the_language_server_knows_the_standard_library`, both because `selfhost/embedded_std.my` is behind `lib` until the pull request's seed commit (D156). `python3 -m unittest tests.burn.test_compiler_parity tests.burn.test_lsp tests.burn.test_toml tests.burn.test_compress tests.burn.test_archive tests.burn.test_http tests.burn.test_regex tests.burn.test_yaml tests.burn.test_xml tests.burn.test_fs`: 478 tests, OK. `scripts/test.sh`: 1503 tests, the same two failures, nothing else.
