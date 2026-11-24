---
id: MYLA-932
title: "std.compress: LZW (GIF and TIFF) and PackBits"
type: feature
status: in-progress
priority: medium
labels: [stdlib, compression, images]
---
Step 1 of [[Project/Standard-library-roadmap/Images-vision-and-fonts]]. The codecs GIF and TIFF need, beside DEFLATE.

- **Owns:** the new parts of `lib/std/compress.my`, [[Language/Standard-library/Compress]]
- **Needs:** [[MYLA-931]] (the bit readers), [[MYLA-930]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] `lzw_decode_gif(b, min_code_size, max_output)` and `lzw_encode_gif`: LSB-first, codes growing to 12 bits, clear and end codes, a full table kept (deferred clear) as decoders must accept
- [ ] `lzw_decode_tiff(b, max_output)` and `lzw_encode_tiff`: MSB-first, the "early change" by one code, and the old-style (LSB) variant detected as libtiff does
- [ ] `packbits_decode(b, max_output)` and `packbits_encode`
- [ ] Each decoder bounded by `max_output` (`TooLarge`), as inflate is ([[MYLA-423]]); a code past the table is `Corrupt`
- [ ] Against Pillow's GIF and TIFF LZW (vendored streams), and round trips of random and repetitive data
- [ ] `#test` cases on every public function that has values to compare (images up to about 16×16), test functions for the generic ones (D162), passing interpreted and `--native`, and on aarch64 (qemu) and wasm32 (Node)
- [ ] Its page below [[Language/Standard-library]] with a doc block that runs, the skill's `reference/stdlib.md`, and an example in `examples/`, registered
