---
id: MYLA-937
title: "std.jpeg: baseline encoding"
type: feature
status: review
priority: low
labels: [stdlib, images, jpeg]
---
Step 4 of [[Project/Standard-library-roadmap/Images-vision-and-fonts]], after the decoder ([[MYLA-936]]).

- **Owns:** the encoder in `lib/std/jpeg.my` and its section of the page
- **Needs:** [[MYLA-936]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] `encode(img, quality, subsampling)`: JFIF, baseline, the Annex K tables scaled for quality 1 to 100 as IJG scales them, 4:4:4, 4:2:2 and 4:2:0 (box-filtered chroma), the islow forward DCT, the standard Huffman tables; gray images as one component
- [x] Pillow decodes every output; at qualities 50, 75, 90 and 95 our PSNR is within 0.5 dB of Pillow's own encoder at the same quality and subsampling, and the size within 10 %
- [x] Our decoder reads it back exactly as Pillow does
- [x] Measured natively: encoding a 12-megapixel image, beside Pillow
- [x] `#test` cases on every public function that has values to compare (images up to about 16×16), test functions for the generic ones (D162), passing interpreted and `--native`, and on aarch64 (qemu) and wasm32 (Node)
- [x] Its page below [[Language/Standard-library]] with a doc block that runs, the skill's `reference/stdlib.md`, and an example in `examples/`, registered

Box-filtered chroma: libjpeg's h2v1/h2v2 downsampling is a box filter (the mean of 2 or 4 pixels) with its alternating rounding bias, smoothing off (Pillow's default), which is what makes the bytes equal Pillow's.

## Evidence

Branch `stdlib/MYLA-937` (rebased onto `claude/stdlib-image-vision-plan-gm6jy5` at `a72676e`, after std.imageio). The API: `#derive(Eq) pub enum Subsampling { S444, S422, S420 }` and `pub fun encode(img: Image8, quality: int = 85, subsampling: Subsampling = Subsampling.S420) -> [uint8]` in `lib/std/jpeg.my` ([[Language/Standard-library/Jpeg#Encoding]]).

- **Exact, beyond the task's tolerance:** every file is the one Pillow 13.0 (libjpeg-turbo 3.2, `optimize=False`, not progressive) writes for the same pixels, quality and subsampling, byte for byte, including the 12-MP picture of `benchmarks/images_std.my` (q85 4:2:0: 3,278,764 bytes, SHA-256 0e0a0d98...). The first comparison, of 192 cases (8 sizes from 1x1 to 100x75, RGB in each subsampling and gray, qualities 1 to 100), was identical on the first build. So the PSNR is Pillow's and the size too (12 MP 4:2:0: q50 1,085,565 bytes 29.72 dB, q75 2,127,856 31.03 dB, q85 3,278,764 33.21 dB, q90 4,222,178 35.88 dB, q95 5,831,278 40.57 dB, the same numbers as Pillow's).
- **`lib/std/jpeg.my`:** 88/88 cases pass interpreted (7.7 s), `--native`, `--target aarch64-linux` (qemu) and `--target wasm32-wasi` (Node); the decoder's 65 as before, 23 new. New: `#test` cases on `rgb_to_ycc`, `reciprocal`, `quantize`, `huffman_codes`, `fdct_block`; test functions `quantising_is_rounding` (every q 1..255), `encodes_as_libjpeg_does` (10 small images to Pillow's length and CRC-32: 4:4:4, 4:2:2 13x9, 4:2:0, gray, 1x1, RGBA, gray + alpha, q1, q100, 24x18 with dummy blocks), `encodes_what_it_can_and_nothing_else` (headers, every quality -5..101 decodes, clamping, `[]` for a 0 side, a 70000-wide image and data that doesn't fit).
- **`tests/burn/test_jpeg_encode.py`** (driver `tests/burn/drivers/jpeg_encode.my`, vendored `tests/burn/data/jpeg_encode.json` of 1,053 cases: size and 16 hex digits of the SHA-256 of Pillow's file, PSNR for the photo-like ones, made by `--vendor`): 7 tests OK in 20 to 32 s: all 1,046 small cases Pillow's bytes; the photo-like ones (14 JPEG-corpus images x q50/75/90/95 x 3 subsamplings) at Pillow's PSNR and size (asserted within 0.5 dB and 10 %); the 12-MP picture in 7 settings; odd sizes, the quality sweeps and every 7th corpus case built `--checked`; 4 cases interpreted; with Pillow: Pillow decodes every file to the samples our decoder gives, Pillow's encoder asked again, 300 random images (sides of 1 to 48, every layout, random quality and subsampling) as Pillow writes them. `scripts/test-target.py aarch64-linux test_jpeg_encode`: OK (248 s); `wasm32-wasi`: OK (30 s).
- **Not broken:** `tests.burn.test_images.JpegDecoder` OK (5 tests); the doc blocks of Jpeg.md and the skill's stdlib.md pass test_doc_blocks' check (run for those pages alone); `test_examples_run` for `jpeg_encode.my` and the registration checks OK; `benchmarks/images_std.my`'s 15 cases pass.
- **Speed** (natively, fastest of 5, idle 4-core machine, 2026-11-25), 12-MP picture at q85: 4:2:0 300 to 305 ms (Pillow 45 ms, 6.7x), 4:4:4 390 to 430 ms (Pillow 59 ms, 7x). The first version took 507 ms; quantising inside the Huffman coder's loop with a zero threshold of 4q made it 329 ms, converting and downsampling in one loop 300 ms. Callgrind: the DCT about 40 %, conversion and downsampling a third, quantisation and Huffman coding a quarter. `benchmarks/images_std.my` now times encode (4:2:0, 4:4:4) and the decode of its own output.
- **Example:** `examples/jpeg_encode.my` (a 64x48 picture at q50/75/90 4:2:0, q90 4:2:2 and 4:4:4, and gray: size and PSNR through `imgproc.psnr`; a file name argument writes it), registered in test_examples_run and test_examples_compile; its 5 cases pass, also on aarch64.
- **Docs:** [[Language/Standard-library/Jpeg]] (intro, the function's row, `## Encoding` with a doc block that runs, what it writes, each step as libjpeg does it, speed, tests), the row on [[Language/Standard-library]], the std.jpeg section of both copies of the skill's `reference/stdlib.md`.
- **For the integrator:** std.imageio's private `encode_jpeg` (MYLA-940) can now be `return Some(jpeg.encode(img, quality, jpeg.Subsampling.S420))`; with that change in a scratch copy, `lib/std/imageio.my`'s 86 cases pass natively. Not done here (not this task's file). `selfhost/embedded_std.my` not regenerated (the lane rules).
- Shared private helpers: none needed; the decoder's tables (`natural_order`, `luma_quant`, `chroma_quant`, `std_huffman`, `scaled_quant`) are used as they were, and the decoder's code is unchanged.
