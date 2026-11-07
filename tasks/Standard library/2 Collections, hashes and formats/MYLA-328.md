---
id: MYLA-328
title: "std.digest: MD5, SHA-1, SHA-2 and HMAC"
type: feature
status: backlog
priority: medium
labels: [stdlib, hashing, wave-2]
---
Wave 2 of [[Project/Standard-library-roadmap]], roadmap #35, #36. Message digests, one-shot and incremental (`new`, `update`, `finish`), as bytes and as hex. AoC's MD5 dominated three of its six slowest days, so speed counts.

- **Owns:** `lib/std/digest.my`, `docs/Language/Standard-library/Digest.md`
- **Needs:** nothing; it can start as soon as its wave does
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] MD5 and SHA-1
- [ ] SHA-256 and SHA-512
- [ ] HMAC over any of them
- [ ] Checked against the NIST and RFC vectors
- [ ] MD5 throughput measured against AoC's `md5.my` and `md5sum`; the 2016 Day 5 workload (a few million short hashes) timed
- [ ] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [ ] Its page below [[Language/Standard-library]], with a doc block that runs
