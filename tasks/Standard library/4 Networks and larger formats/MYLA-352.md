---
id: MYLA-352
title: DEFLATE compression and archives
type: feature
status: backlog
priority: low
labels: [stdlib, compression, wave-4]
---
Wave 4 of [[Project/Standard-library-roadmap]], roadmap #50, #51. The compressor after the decompressor, then tar and zip.

- **Owns:** `lib/std/compress.my` (the compressor), `lib/std/archive.my`, `docs/Language/Standard-library/Archive.md`
- **Needs:** [[MYLA-344]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] Deflate with LZ77 matching and dynamic Huffman codes, levels from fast to small, round-tripped through `gzip`
- [ ] tar read and write; zip read
- [ ] Ratio and speed against `gzip -1`, `-6` and `-9`
- [ ] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [ ] Its page below [[Language/Standard-library]], with a doc block that runs
