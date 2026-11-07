---
id: MYLA-327
title: "std.hash: the Hasher, fast hashes and checksums"
type: feature
status: backlog
priority: medium
labels: [stdlib, hashing, wave-2]
---
Wave 2 of [[Project/Standard-library-roadmap]], roadmap #33, #34. The hashing that `Hash` (D163, [[MYLA-313]]) builds on, and the checksums that compression needs.

- **Owns:** `lib/std/hash.my`, `docs/Language/Standard-library/Hash.md`
- **Needs:** nothing; it can start as soon as its wave does
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] `Hasher`: a small value with `add` for each primitive type and `finish() -> uint64`; the algorithm (wyhash or a SipHash-1-3) chosen by measurement, with a fixed seed for now
- [ ] FNV-1a 32 and 64 and the hasher's algorithm over a `str` or `[uint8]`
- [ ] CRC-32 (table-driven) and Adler-32, checked against published vectors
- [ ] Throughput on 100 MB measured natively
- [ ] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [ ] Its page below [[Language/Standard-library]], with a doc block that runs
