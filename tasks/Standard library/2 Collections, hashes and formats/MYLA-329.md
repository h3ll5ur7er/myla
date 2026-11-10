---
id: MYLA-329
title: "std.encoding and std.bytes: hex, Base64, URLs, bytes and strings"
type: feature
status: done
priority: medium
labels: [stdlib, encoding, wave-2]
---
Wave 2 of [[Project/Standard-library-roadmap]], roadmap #7, #37, #38. Conversions between bytes and text.

- **Owns:** `lib/std/encoding.my`, `lib/std/bytes.my`, `lib/std/url.my`, `docs/Language/Standard-library/Encoding.md`, `docs/Language/Standard-library/Bytes.md`, `docs/Language/Standard-library/Url.md`
- **Needs:** nothing; it can start as soon as its wave does
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] `std.bytes`: a `str` from `[uint8]` and back, `is_utf8`, a `char`'s UTF-8 bytes and back
- [x] `std.encoding`: hex and Base64 (standard and URL-safe, with and without padding) encode and decode, with an error for bad input
- [x] `std.url`: percent-encoding, query strings, parsing and building a URL
- [x] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [x] Its page below [[Language/Standard-library]], with a doc block that runs

## Evidence

- Pages: [[Language/Standard-library/Bytes]], [[Language/Standard-library/Encoding]], [[Language/Standard-library/Url]], each with a doc block that runs.
- Tests first: with the cases written and the bodies `panic("todo")`, `myla test` gave 0/39 for `bytes.my`, 0/61 for `encoding.my` and 0/86 for `url.my`.
- `build/myla test lib/std/<m>.my --stdlib lib`, interpreted, `--native`, `--target aarch64-linux` (qemu) and `--target wasm32-wasi` (node): `bytes.my` 47/47, `encoding.my` 93/93, `url.my` 139/139 on each. The cases hold RFC 4648's test vectors (base 16 and Base64) and RFC 3986's examples (sections 1.1.2, 3 and 5.4, an IPv6 and an IPvFuture host among them); test functions check round trips of every encoding for 0 to 300 random bytes and of 18 URLs through `parse` and `to_str`.
- After `scripts/bootstrap.sh`: `python3 -m unittest tests.burn.test_std_modules tests.burn.test_doc_blocks` OK (6 tests).
- Speed, x86-64, best of three on 100 MB of random bytes: `base64_encode` 0.55 s, `base64_decode` 0.45 s, `hex_encode` 0.61 s, `hex_decode` 0.73 s, `bytes.to_str` 0.30 s, `bytes.from_str` 0.21 s. A table lookup for the digits instead of range comparisons took `base64_decode` from 1.24 s to 0.45 s and `hex_decode` from 1.30 s to 0.73 s.

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]], with a follow-up in [[MYLA-425]]: `EncodingError` and `UrlError` have no `Format`; `to_str` and reference resolution are [[MYLA-422]]'s.
