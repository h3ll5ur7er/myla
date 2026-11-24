---
id: MYLA-939
title: "std.tiff: baseline TIFF, several pages, float samples"
type: feature
status: todo
priority: low
labels: [stdlib, images, tiff]
---
Step 3 of [[Project/Standard-library-roadmap/Images-vision-and-fonts]].

- **Owns:** `lib/std/tiff.my`, `docs/Language/Standard-library/Tiff.md`
- **Needs:** [[MYLA-933]], [[MYLA-932]] (LZW, PackBits), [[MYLA-945]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] The IFD chain in both byte orders, every field type, offsets checked; `pages`, `tags`
- [ ] Strips and tiles, planar configurations 1 and 2, none, PackBits, LZW and Deflate, predictors 2 and 3
- [ ] Bilevel, gray, RGB, palette, extra samples as alpha (associated or not); 1, 4, 8, 16 bits and `float32`; `decode`, `decode16`, `decode_f32`
- [ ] JPEG in TIFF, CCITT, BigTIFF, YCbCr and CMYK are `Unsupported(…)` by name
- [ ] `encode`, `encode16`: strips of about 8 KB, none, LZW or Deflate with the predictor; Pillow and `tiffinfo` (when installed) read the output
- [ ] The corpus (libtiff's pictures where their licence allows, and Pillow's output in every supported combination) decodes as Pillow decodes it
- [ ] Its corpus and fuzz cases in [[MYLA-945]]'s harness: truncations and seeded mutations are `Ok` or `Err`, never a runtime error, natively plain and `--checked`
- [ ] `#test` cases on every public function that has values to compare (images up to about 16×16), test functions for the generic ones (D162), passing interpreted and `--native`, and on aarch64 (qemu) and wasm32 (Node)
- [ ] Its page below [[Language/Standard-library]] with a doc block that runs, the skill's `reference/stdlib.md`, and an example in `examples/`, registered
