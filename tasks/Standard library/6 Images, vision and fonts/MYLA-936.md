---
id: MYLA-936
title: "std.jpeg: baseline and progressive decoding"
type: feature
status: in-progress
priority: medium
labels: [stdlib, images, jpeg]
---
Step 3 of [[Project/Standard-library-roadmap/Images-vision-and-fonts]]. The encoder is [[MYLA-937]].

- **Owns:** `lib/std/jpeg.my` (the decoder), `docs/Language/Standard-library/Jpeg.md`
- **Needs:** [[MYLA-933]], [[MYLA-931]], [[MYLA-945]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] Markers and segments: SOI, APPn, DQT (8 and 16 bit), SOF0/1/2, DHT, SOS, DRI, RSTn, EOI; a segment's length checked against the input before it is read
- [ ] Baseline: Huffman decoding, every sampling factor, restart intervals, libjpeg's islow IDCT and its fancy upsampling, YCbCr → RGB by libjpeg's fixed-point tables
- [ ] The baseline corpus decodes bit-identical to Pillow's (vendored PAMs), on every runner
- [ ] Progressive: spectral selection and successive approximation (DC and AC, first and refining scans), the same exactness
- [ ] Adobe APP14 CMYK and YCCK to RGB; `JpegMeta` (JFIF density, EXIF, ICC); `orientation`, `apply_orientation`
- [ ] Arithmetic coding, lossless, 12-bit and hierarchical are `Unsupported(…)` by name
- [ ] Measured natively: a 12-megapixel baseline and a progressive photo, beside Pillow (libjpeg-turbo); a profile of where the time goes
- [ ] Its corpus and fuzz cases in [[MYLA-945]]'s harness: truncations and seeded mutations are `Ok` or `Err`, never a runtime error, natively plain and `--checked`
- [ ] `#test` cases on every public function that has values to compare (images up to about 16×16), test functions for the generic ones (D162), passing interpreted and `--native`, and on aarch64 (qemu) and wasm32 (Node)
- [ ] Its page below [[Language/Standard-library]] with a doc block that runs, the skill's `reference/stdlib.md`, and an example in `examples/`, registered
