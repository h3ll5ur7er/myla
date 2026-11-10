---
id: MYLA-331
title: "std.num: integers in any radix and width, parse errors"
type: feature
status: done
priority: medium
labels: [stdlib, numbers, wave-2]
---
Wave 2 of [[Project/Standard-library-roadmap]], roadmap #6. `std.num` is used by the compiler (float literals), so its existing functions stay as they are: only new ones are added.

- **Owns:** `lib/std/num.my` (its new functions), `docs/Language/Standard-library/Num.md`
- **Needs:** nothing; it can start as soon as its wave does
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] `parse_int_radix(s, radix) -> Result<int64, ParseIntError>`, the error saying why (empty, a bad digit at an index, out of range); forms for `int32` and `uint64`
- [x] `to_radix(n, radix)` and `to_hex`, `to_binary`, with an optional width and padding
- [x] The `int` form of `parse_int` that AoC unwrapped 12 times ([[MYLA-318]]) reads as one call
- [x] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [x] Its page below [[Language/Standard-library]], with a doc block that runs

## Evidence

- **API** ([[lib/std/num.my]]): `#derive(Eq) pub enum ParseIntError { Empty, InvalidDigit(int), Overflow }`; `parse_int_radix(s, radix) -> Result<int64, ParseIntError>`, `parse_int32(s) -> Result<int32, …>`, `parse_uint64(s) -> Result<uint64, …>`, `parse_uint64_radix(s, radix) -> Result<uint64, …>`; `to_radix(n: int64, radix) -> str`, `to_radix_u64(n: uint64, radix) -> str`, `to_hex(n: uint64, width: int = 0) -> str`, `to_binary(n: uint64, width: int = 0) -> str`. The existing functions are unchanged. `parse_int32(s).unwrap_or(0)` and `parse_int32(s)?` are the one-call forms.
- **Rules:** an optional `+` or `-`, then digits; letters in either case; leading zeros and `-0` allowed; no spaces, prefixes or `_`. A sign alone is `Empty`. A bad digit anywhere is reported before an overflow. The unsigned forms take a sign too: `-0` is 0, `-1` an `Overflow`. A radix outside 2 to 36 panics, naming the function.
- **Tests first:** 115 cases on the public functions were written against stubs; 57 of 166 passed then (the 51 old ones and 6 that expected `Empty`). 8 cases on the private helpers and 2 test functions came with the code. Now `build/myla test lib/std/num.my --stdlib lib`: 176/176 interpreted, 176/176 `--native`, 176/176 `--target aarch64-linux` (qemu). `radix_extremes` checks int64's MIN and MAX and uint64's MAX in every radix from 2 to 36, read back, with a `+`, with leading zeros, and the strings just past each limit (past the multiply and past the add). A mutant that lets the add go one past the limit fails 18 cases and both test functions. `python3 -m unittest tests.burn.test_std_modules tests.burn.test_doc_blocks`: OK (6 tests).
- **Bootstrap:** `scripts/bootstrap.sh` reaches its byte-identical fixed point (11,045,117 bytes; 10,982,434 before, the growth being the embedded library).
- **Speed:** 10 million decimal strings (1000 distinct ones of 1 to 19 digits, half negative), native, best of 7: `parse_int_radix(s, 10)` 314 ms, `parse_int` 509 ms.
- **Compiler bug found:** `Checker.synthesize_derives` (`selfhost/checker.my`) skips a `#derive` type whose declaration has the same line and column as one already collected, in another module. So a program loses `Eq` on its own derived type when a module it loads has a derived type at the same position. `myla test lib/std/num.my --native` without `--stdlib` hits it, as the harness holds a copy of `std.num` and loads the embedded one too. Comparing `d.id == decl.id` instead fixes it, with the fixed point still reached. Not fixed here (`selfhost/` isn't this lane's).

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]], with a follow-up in [[MYLA-425]]: `to_hex`/`to_binary` with a width near `int`'s minimum.
