---
id: MYLA-329
title: "std.encoding and std.bytes: hex, Base64, URLs, bytes and strings"
type: feature
status: backlog
priority: medium
labels: [stdlib, encoding, wave-2]
---
Wave 2 of [[Project/Standard-library-roadmap]], roadmap #7, #37, #38. Conversions between bytes and text.

- **Owns:** `lib/std/encoding.my`, `lib/std/bytes.my`, `lib/std/url.my`, `docs/Language/Standard-library/Encoding.md`, `docs/Language/Standard-library/Bytes.md`, `docs/Language/Standard-library/Url.md`
- **Needs:** nothing; it can start as soon as its wave does
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] `std.bytes`: a `str` from `[uint8]` and back, `is_utf8`, a `char`'s UTF-8 bytes and back
- [ ] `std.encoding`: hex and Base64 (standard and URL-safe, with and without padding) encode and decode, with an error for bad input
- [ ] `std.url`: percent-encoding, query strings, parsing and building a URL
- [ ] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [ ] Its page below [[Language/Standard-library]], with a doc block that runs
