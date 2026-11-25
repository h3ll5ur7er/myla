---
id: MYLA-935
title: "std.png: decode and encode"
type: feature
status: in-progress
priority: medium
labels: [stdlib, images, png]
---
Step 3 of [[Project/Standard-library-roadmap/Images-vision-and-fonts]].

- **Owns:** `lib/std/png.my`, `docs/Language/Standard-library/Png.md`
- **Needs:** [[MYLA-933]], [[MYLA-931]], [[MYLA-945]] (the corpus); std.compress and std.checksum as they are
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] `info`, `decode`, `decode16`, `decode_with_meta`: every colour type and bit depth, `tRNS`, Adam7, the five filters, CRC-32 on every chunk, inflate bounded by the size the header claims, `PngMeta` (`gAMA`, `sRGB`, `iCCP`, `pHYs`, the text chunks)
- [ ] PngSuite: every valid file decodes exactly as Pillow decodes it (the vendored PAMs); every `x*` file is `Err`
- [ ] `encode`, `encode16`, `encode_indexed`: adaptive filtering by the minimum sum of absolute differences, levels through `zlib_compress`, the smallest lossless colour type
- [ ] Round trips through our decoder and Pillow's; the size at level 6 compared with Pillow's `optimize=False` output on the corpus
- [ ] Measured natively: decode and encode of a 12-megapixel photo saved as PNG, beside Pillow's numbers
- [ ] Its corpus and fuzz cases in [[MYLA-945]]'s harness: truncations and seeded mutations are `Ok` or `Err`, never a runtime error, natively plain and `--checked`
- [ ] `#test` cases on every public function that has values to compare (images up to about 16×16), test functions for the generic ones (D162), passing interpreted and `--native`, and on aarch64 (qemu) and wasm32 (Node)
- [ ] Its page below [[Language/Standard-library]] with a doc block that runs, the skill's `reference/stdlib.md`, and an example in `examples/`, registered
