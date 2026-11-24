---
id: MYLA-934
title: "std.pnm, std.bmp and std.qoi"
type: feature
status: backlog
priority: medium
labels: [stdlib, images]
---
Step 2 of [[Project/Standard-library-roadmap/Images-vision-and-fonts]]. Three small formats: PNM is what the tests write expected pixels in, BMP is Windows' own format, and QOI is fast lossless output.

- **Owns:** `lib/std/pnm.my`, `lib/std/bmp.my`, `lib/std/qoi.my` and their pages
- **Needs:** [[MYLA-933]], [[MYLA-931]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] std.pnm: PBM, PGM, PPM in ASCII and binary, PAM (every tuple type of 1 to 4 channels), 8 and 16 bits; `info`, `decode`, `decode16`, `encode`, `encode16`
- [ ] std.bmp: read 1, 4, 8, 16, 24 and 32 bits, bottom-up and top-down, BI_RGB, RLE4, RLE8, BI_BITFIELDS (with alpha masks), the V4 and V5 headers; write 24 and 32 bits
- [ ] std.qoi: read and write the whole specification, checked against the reference test images
- [ ] Each of them: `max_pixels` checked before allocating
- [ ] Its corpus and fuzz cases in [[MYLA-945]]'s harness: truncations and seeded mutations are `Ok` or `Err`, never a runtime error, natively plain and `--checked`
- [ ] `#test` cases on every public function that has values to compare (images up to about 16×16), test functions for the generic ones (D162), passing interpreted and `--native`, and on aarch64 (qemu) and wasm32 (Node)
- [ ] Its page below [[Language/Standard-library]] with a doc block that runs, the skill's `reference/stdlib.md`, and an example in `examples/`, registered
