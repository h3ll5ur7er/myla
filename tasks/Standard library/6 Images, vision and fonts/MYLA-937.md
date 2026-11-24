---
id: MYLA-937
title: "std.jpeg: baseline encoding"
type: feature
status: backlog
priority: low
labels: [stdlib, images, jpeg]
---
Step 4 of [[Project/Standard-library-roadmap/Images-vision-and-fonts]], after the decoder ([[MYLA-936]]).

- **Owns:** the encoder in `lib/std/jpeg.my` and its section of the page
- **Needs:** [[MYLA-936]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] `encode(img, quality, subsampling)`: JFIF, baseline, the Annex K tables scaled for quality 1 to 100 as IJG scales them, 4:4:4, 4:2:2 and 4:2:0 (box-filtered chroma), the islow forward DCT, the standard Huffman tables; gray images as one component
- [ ] Pillow decodes every output; at qualities 50, 75, 90 and 95 our PSNR is within 0.5 dB of Pillow's own encoder at the same quality and subsampling, and the size within 10 %
- [ ] Our decoder reads it back exactly as Pillow does
- [ ] Measured natively: encoding a 12-megapixel image, beside Pillow
- [ ] `#test` cases on every public function that has values to compare (images up to about 16×16), test functions for the generic ones (D162), passing interpreted and `--native`, and on aarch64 (qemu) and wasm32 (Node)
- [ ] Its page below [[Language/Standard-library]] with a doc block that runs, the skill's `reference/stdlib.md`, and an example in `examples/`, registered
