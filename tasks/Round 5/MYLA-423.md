---
id: MYLA-423
title: "P9 Archives and compression: pax numbers, ids, output limits"
type: bug
status: done
priority: medium
labels: [std, archive, compress, round-5]
---
Work package P9 of [[Project/Review-2026-11-09]] (wave A2). Files: `lib/std/archive.my`, `lib/std/compress.my`, `tests/burn/test_archive.py`. Reopens [[MYLA-352]].

- [x] `pax_int` bounded (a 20-digit pax number overflowed), D184
- [x] M19: uid and gid of 2^31 or more as `int64`, or refused
- [x] A `max_output` form of `inflate`, `gunzip` and `zip_data`
- [x] Tar headers and pax records in the fuzz test, run under `--checked`
- [x] The D184 sweep of both modules: base-256 fields, gzip's length, zip's directory numbers, the additions that compare lengths

## Proposals

Decisions the items left open, built as recommended; the owner decides.

1. **Owners as `int64`, not refused (M19).** `Entry.uid` and `gid` are `int64`. Python's `tarfile` reads them as unbounded integers (`biguid_gnu.tar`, `biguid_pax.tar`: uid 4294967294, gid 3000000000), GNU tar reads them as `uid_t` (32 bits unsigned), and 4294967294 is a real id (`(uid_t)-2`, `nobody` on NFS); refusing would make archives other tools read unreadable. `int64` holds every id POSIX allows and every number a base-256 field of 8 bytes holds (2^56). The cost: a caller that set `e.uid` from an `int32` variable now writes `as int64` (a literal adapts); none in the repository did but the burn test's driver. *Alternative:* `int32` and `BadHeader` past 2^31 − 1 (no API change, refuses real archives); `uint32` (Linux's type, but pax and GNU allow negative ids, which Python reads).
2. **A pax number that isn't one is `BadHeader`.** A pax `mtime`, `uid`, `gid` or `size` that doesn't fit an `int64` is `BadHeader` (D184, rule 1), as GNU tar 1.35 refuses it (`Extended header mtime=99999999999999999999999999 is out of range -9223372036854775808..9223372036854775807`, exit 2). So is one that isn't a number in its strict form (`+5`, ` 5`, `1_000`, `1e5`, a fraction of an id, empty), where before an unreadable `mtime`, `uid` or `gid` silently kept the header's value. *Alternatives:* Python's tarfile reads a time as a float (`1e+26`) and a number that isn't one as 0, and never fails; keeping the header's value hides a broken archive.
3. **`max_output` as a default parameter.** `inflate(b, max_output: int = 0x7FFFFFFF)`, the same for `gunzip`, `zlib_decompress` and `zip_data(b, f, max_output)`, rather than a second function each (`inflate_limited`): existing calls are unchanged and a caller adds one argument. Past the limit the result is the new variant `CompressError.TooLarge` (and `ArchiveError.TooLarge` for `zip_data`). A `#test` case must give every argument, so the existing cases of the three functions gained `, ALL`. *Alternatives:* separate functions; a limit on the `Decoder` streams too (a caller of a stream already bounds what it reads).
4. **`zip_data` inflates no further than the entry's size**, and more is `LengthMismatch`, as it was after the whole entry was inflated: so an entry takes no more memory than its directory says, whatever `max_output`. An entry whose size is over `max_output` is `TooLarge` before anything is read.
5. **The tar reader is stricter, as Python's tarfile is**, which the fuzz test asked for: every header's number fields (a pax header's and a long name's too) must be numbers, and a pax header or a long name with no entry after it is `Truncated` (tarfile: `ReadError`). It stays more lenient in one place, on purpose: the last entry's padding may be missing (tarfile: `unexpected end of data`).

## Evidence

**Tests first.** Each item began with a test that failed:
- `myla test lib/std/archive.my --stdlib lib`, before the fix: 90/100, failing `pax_int` #9, #11–#13 (`runtime error: integer overflow`), #7 (`12.5x` read as 12), `tar_number` #12–#15 (2^63 read as −2^63, 2^80 and −2^80 − 1 as 0 and int64's largest: wrapped with no trap, as `<<` drops bits), and `tar_big_numbers` (overflow); the case of M19 didn't compile (`integer literal 4294967294 does not fit in 'int32'`). After: 112/112.
- The review's reproducer `bug_pax_overflow.my`: before, `runtime error: integer overflow` at `archive.my:598` (interpreted; a wrapped mtime natively); after, `Err: invalid header`. The three archives of the bundle: `biguid_gnu.tar` and `biguid_pax.tar` read uid 4294967294, gid 3000000000 (before: −2 and −1294967296), interpreted and natively; `pax_mtime_huge.tar` is `invalid header`.
- `zip_data` with an `offset` or `csize` of int64's largest: before, `runtime error: integer overflow` at `archive.my:909`; after, `Truncated`.
- `gzip_length_wraps` (compress): before, `runtime error: integer overflow`; after, passes (the length sums to 4 past 2^32).
- `tar_broken_headers`, from what the fuzz test found: with the old `next_entry`, `runtime error: the end after a pax header`; `tar_big_numbers` with it: `mtime=99999999999999999999999999` taken. The fuzz tests with the old `next_entry` (and everything else new): 80 failures in `test_tar_corrupted_natively` and `test_tar_pax_records_natively` (`std.archive reads what tarfile refuses`, listings that differ); after: none.
- Not tested by a failing case, as it takes inputs of 1 to 2 GiB: the additions that compare lengths in `pax_records` (`p + len`), `zip_list` (`q + 46 + nlen + elen + clen`), `extra_mtime` and gzip's FEXTRA, now comparisons without the addition.

**Module cases**, each interpreted, `--native` (built checked), `--target aarch64-linux` under qemu and `--target wasm32-wasi` under Node: archive 112/112, compress 155/155.

**Burn test** `tests/burn/test_archive.py`: 11 tests in 42 s (was 7 in 51 s). New: the driver also built `--checked`, and both must give the same output on every fuzzed input, a failure being the driver's own `error: …`, not a runtime error; `test_tar_corrupted_natively` (400 tar files with a header field changed or cut short), `test_tar_pax_records_natively` (250 PAX archives of odd records), `test_zip_directory_corrupted_natively` (150), the 60 zip entries of `test_zip_corrupted_natively` under both builds, tarfile's GNU and PAX archives with ids of 2^31 to 2^53 and times of 2^40 and −5 listed as Python lists them, an entry with uid 4294967294 written that `tarfile` reads and `tar -x` extracts, and `test_decompression_bomb_natively`. Of the changed tar headers, std.archive read 288 of 400 as Python did, refused 65 that Python read (a stricter number, a header Python takes for the end) and refused all 47 that Python refused; of 4000 changed headers in a longer run, none disagreed. `tests.burn.test_compress`: 4 tests, OK.

**The bomb**: 1 GiB of zeros gzipped to 1,043,656 bytes. `gunzip(gz, 1 << 20)` natively: `TooLarge` in 0.01 s, 8.8 MB resident, under a 256 MiB address-space limit; `gunzip(gz)`: `runtime error: out of memory` under the same limit.

**Suites**: `scripts/test.sh fast`: 829 tests, one failure, `test_embedded_std` (expected until the integrator's seed commit). `tests.burn.test_std_modules`, `test_doc_blocks`, `test_lsp`, `test_compiler_parity` and `test_http` (std.http calls std.compress): 427 tests, OK. `scripts/test.sh` (full): 1482 tests in 21 min, the same one failure, 336 skipped. The bootstrap from the base seed is unchanged (no compiler change); `selfhost/embedded_std.my` restored, not committed.

## The owner's decision (2026-11-11)

The proposals stand as built (D189).

## Review 2026-11-12

Signed off in [[Project/Review-2026-11-12]], with a follow-up in [[MYLA-550]]: `archive.zip_read` has no output limit, and a tar entry of 2^31 bytes or more is `BadHeader`.
