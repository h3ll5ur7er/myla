---
id: MYLA-344
title: "std.compress: DEFLATE decompression, gzip and zlib"
type: feature
status: backlog
priority: low
labels: [stdlib, compression, streams, wave-3]
---
Wave 3 of [[Project/Standard-library-roadmap]], roadmap #49. Decompression first: it is smaller than the compressor, and reading archives and HTTP bodies needs it.

- **Owns:** `lib/std/compress.my`, `docs/Language/Standard-library/Compress.md`
- **Needs:** [[MYLA-327]], [[MYLA-338]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] Inflate (stored, fixed and dynamic Huffman blocks) as a `Read` adapter
- [ ] gzip and zlib containers with their checksums
- [ ] Checked against files made by `gzip` and Python's `zlib` at every level
- [ ] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [ ] Its page below [[Language/Standard-library]], with a doc block that runs
