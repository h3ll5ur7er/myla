---
id: MYLA-934
title: "std.pnm, std.bmp and std.qoi"
type: feature
status: review
priority: medium
labels: [stdlib, images]
---
Step 2 of [[Project/Standard-library-roadmap/Images-vision-and-fonts]]. Three small formats: PNM is what the tests write expected pixels in, BMP is Windows' own format, and QOI is fast lossless output.

- **Owns:** `lib/std/pnm.my`, `lib/std/bmp.my`, `lib/std/qoi.my` and their pages
- **Needs:** [[MYLA-933]], [[MYLA-931]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] std.pnm: PBM, PGM, PPM in ASCII and binary, PAM (every tuple type of 1 to 4 channels), 8 and 16 bits; `info`, `decode`, `decode16`, `encode`, `encode16`
- [x] std.bmp: read 1, 4, 8, 16, 24 and 32 bits, bottom-up and top-down, BI_RGB, RLE4, RLE8, BI_BITFIELDS (with alpha masks), the V4 and V5 headers; write 24 and 32 bits
- [x] std.qoi: read and write the whole specification, checked against the reference test images
- [x] Each of them: `max_pixels` checked before allocating
- [x] Its corpus and fuzz cases in [[MYLA-945]]'s harness: truncations and seeded mutations are `Ok` or `Err`, never a runtime error, natively plain and `--checked`
- [ ] `#test` cases on every public function that has values to compare (images up to about 16×16), test functions for the generic ones (D162), passing interpreted and `--native`, and on aarch64 (qemu) and wasm32 (Node) — all but aarch64: qemu-aarch64 isn't installed on the lane's machine
- [x] Its page below [[Language/Standard-library]] with a doc block that runs, the skill's `reference/stdlib.md`, and an example in `examples/`, registered

## What was built

- `std.pnm` ([[Language/Standard-library/Pnm]]): `info`, `decode`, `decode16`, `encode` (P5, P6, or P7 with alpha), `encode_as(img, kind, ascii = false)`, `encode16`, `encode16_as`, `enum Kind { Pbm, Pgm, Ppm, Pam }`. Any MAXVAL 1 to 65535, scaled rounded half up; a MAXVAL past 255 read through 16 bits then `to_unorm8`, which gives the corpus's Pillow pixels exactly (MAXVAL 15 and 1000 included).
- `std.bmp` ([[Language/Standard-library/Bmp]]): `info`, `decode`, `encode` (24-bit `BI_RGB`, or 32-bit `BI_BITFIELDS` with a V4 header for alpha). Also reads the OS/2 core header and `BI_ALPHABITFIELDS`.
- `std.qoi` ([[Language/Standard-library/Qoi]]): `info`, `decode`, `encode`, the reference encoder's bytes.
- `tests/burn/drivers/pnm.my`, `pnm16.my` (a `Pnm16Decoder` row in `test_images.py`'s `CODECS`: `decode16`), `bmp.my`, `qoi.my`; `tests/burn/drivers/simple_roundtrip.my` and `tests/burn/test_simple_images.py` (every encoder, every kind and form, round-tripped over the corpus; QOI byte for byte against Pillow's files; Pillow reads what we write).
- `examples/image_files.my`, registered in `test_examples_run.py` and `test_examples_compile.py`.

## Evidence

- Cases (2026-11-25): std.pnm 43/43, std.bmp 21/21, std.qoi 12/12, each interpreted (`build/myla test lib/std/<m>.my --stdlib lib`), `--native`, and `--target wasm32-wasi` under Node. The corpus classes existed first (skipped until the modules did); the `#test` cases were written with the code, and their first runs failed on three wrong expectations of mine (a QOI DIFF byte, a PBM threshold, an error's offset), not on the modules. aarch64 not run: no qemu-aarch64 here.
- `python3 -m unittest tests.burn.test_images.PnmDecoder tests.burn.test_images.Pnm16Decoder tests.burn.test_images.BmpDecoder tests.burn.test_images.QoiDecoder tests.burn.test_images.Corpus tests.burn.test_simple_images`: 31 tests OK in 35 s (each codec's corpus natively and `--checked`, the smallest files interpreted, the fuzz runs plain and `--checked` with 10,000 mutations and the truncations). Before the modules the four codec classes were skipped. Once more with `MYLA_FUZZ_CASES=30000 MYLA_FUZZ_SEED=934`, `--checked`: OK. No manifest verdict needed changing.
- Round trips (`test_simple_images`): the 29 `ok` files of the three formats, each written by 10 encoders (BMP, QOI, PNM in its kind and all seven forms) and PNM's also by the 8 at 16 bits, read back as written; the 4 QOI files Pillow wrote come back byte for byte but for the colour space byte (Pillow writes 1, qoi.h 0); Pillow 13 reads every output but the PAM files to the pixels std's decoders read.
- The QOI reference images (qoiformat.org's `qoi_test_images.zip`, fetched once, not vendored: 5.6 MB, past the corpus limit): all 8 decode to their PNG's pixels; 7 encode again byte for byte; `edgecase.qoi` uses the table for an opening run's colour, which qoi.h's encoder never writes.
- `tests.burn.test_doc_blocks`: OK (the three pages' blocks run, interpreted and natively). `test_examples_run`/`test_examples_compile` for `image_files.my`, `test_compile_list_matches_examples`, `test_every_value_returning_function_is_tested`: OK.
- Measured natively (`myla build`, the best of three runs, a shared 4-core machine with other lanes running), a 4096×4096 RGB picture (50,331,648 samples; gradients, noise and flat bands):

  | Format | File | Encode | Decode |
  | --- | --- | --- | --- |
  | PPM (P6) | 50.3 MB | 108 to 110 ms | 114 to 116 ms |
  | BMP (24 bits) | 50.3 MB | 120 to 124 ms | 113 to 114 ms |
  | QOI | 23.6 MB | 259 to 298 ms | 337 to 363 ms |

  Making the 50 MB output list (`list.filled`, a push at a time or a slice alike) is about 100 ms of each. QOI's encoder went from 425 ms to 259–298 ms with the hash and the deltas inline and the table as 64 packed `uint32`s; the decoder's loop is about 15 ns an operation.
- Not done: `tests/burn/drivers/image_driver.my` still writes PAM itself; switching it to `pnm.encode_as` would make every codec's harness depend on std.pnm, the module under test here, for no gain.
