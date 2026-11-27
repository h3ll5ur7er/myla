---
id: MYLA-961
title: "std.png: decode and encode"
type: feature
status: review
priority: medium
labels: [stdlib, images, png]
---
Step 3 of [[Project/Standard-library-roadmap/Images-vision-and-fonts]].

- **Owns:** `lib/std/png.my`, `docs/Language/Standard-library/Png.md`
- **Needs:** [[MYLA-959]], [[MYLA-957]], [[MYLA-971]] (the corpus); std.compress and std.checksum as they are
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] `info`, `decode`, `decode16`, `decode_with_meta`: every colour type and bit depth, `tRNS`, Adam7, the five filters, CRC-32 on every chunk, inflate bounded by the size the header claims, `PngMeta` (`gAMA`, `sRGB`, `iCCP`, `pHYs`, the text chunks)
- [x] PngSuite: every valid file decodes exactly as Pillow decodes it (the vendored PAMs); every `x*` file is `Err`
- [x] `encode`, `encode16`, `encode_indexed`: adaptive filtering by the minimum sum of absolute differences, levels through `zlib_compress`, the smallest lossless colour type
- [x] Round trips through our decoder and Pillow's; the size at level 6 compared with Pillow's `optimize=False` output on the corpus
- [x] Measured natively: decode and encode of a 12-megapixel photo saved as PNG, beside Pillow's numbers
- [x] Its corpus and fuzz cases in [[MYLA-971]]'s harness: truncations and seeded mutations are `Ok` or `Err`, never a runtime error, natively plain and `--checked`
- [x] `#test` cases on every public function that has values to compare (images up to about 16×16), test functions for the generic ones (D162), passing interpreted and `--native`, and on aarch64 (qemu) and wasm32 (Node). *aarch64 not run: there is no `qemu-aarch64` on this machine; the driver builds for `aarch64-linux`.* (aarch64 run by the integrator after the merge, 2026-11-25, under qemu: png 91/91)
- [x] Its page below [[Language/Standard-library]] with a doc block that runs, the skill's `reference/stdlib.md`, and an example in `examples/`, registered

## Evidence

Branch `stdlib/MYLA-961` over `088e285`, measured on 2026-11-25 on the shared 4-core machine (other lanes running).

- **Module cases:** `build/myla test lib/std/png.my` 91/91 interpreted (about 4 s), `--native` 91/91, `--target wasm32-wasi` under Node 91/91. aarch64: built only (no qemu). Hand-made vectors (Python's zlib, no Pillow) for a 4-bit palette with `tRNS`, 16-bit RGB with a colour key, 1-bit gray, a 2-bit Adam7 image, every metadata chunk, a huge IHDR, no IDAT, a filter byte 5; round trips of every filter, layout, 16 bits and palette depths 1, 2, 4, 8; the encoders' bytes pinned after Python's zlib and CRC read them back. The cases first failed where the test was wrong (a rounding expectation) or the vectors were placeholders; review then found two bugs the tests now pin: a file with IHDR and IEND but no IDAT was `Truncated` (now `Corrupt("no IDAT")`), and a filter byte 5 after an Average first row was accepted as the internal "average with nothing above" (now `Corrupt("filter type 5 at row 1")`).
- **Corpus** (`python3 -m unittest tests.burn.test_images.PngDecoder tests.burn.test_images.Png16Decoder`, 10 tests, OK): `decode` over all 195 PNG entries (171 ok, every PngSuite file and the generated ones, exact against the PAMs, 16-bit files compared rounded to 8; all 22 `err` refused, `xcsn0g01` included: its IDAT CRC is checked, the manifest already said `err`; the 2 `any` decode), natively and `--checked`; `decode16` over the 59 entries of 16 bits or broken; the smallest files interpreted; the fuzz runs (truncations up to 512 bytes and 10,000 seeded mutations, plain and `--checked`), and once more with `MYLA_FUZZ_CASES=50000 MYLA_FUZZ_SEED=935`: never a runtime error or `bad`. No manifest entry needed changing.
- **Encoders** (`python3 -m unittest tests.burn.test_png`, new, 4 tests, OK): every decodable corpus file re-encoded (`encode`, `encode16` for the 16-bit ones, `encode_indexed` of `image.quantize(img, 256, false)` for the palette ones), decoded again by std.png to the same pixels, by `_images.png_decode` (Python's zlib alone) to the expected pixels, and by Pillow 13 (when installed); each fixed filter and levels 0 and 9 on 13 files. At level 6 the 70 8-bit non-palette files take 25,998 bytes against Pillow's 25,779 (`optimize=False, compress_level=6`, ratio 1.008).
- **Measured natively** (`benchmarks/images_std.my`, its 4000×3000 photo-like RGB picture, fastest of 3): `png.decode` 402 to 418 ms (Pillow 196 ms), of which std.compress's `zlib_decompress` 255 ms, the chunk walk with the IDAT slice and its CRC-32 60 ms, unfiltering about 85 ms; `png.encode` at level 6 5.19 s (Pillow 3.08 s), of which `zlib_compress` 4.69 s and choosing and applying the filters 0.48 s; the file is 13,657,043 bytes (Pillow's 14.7 MB). Unfiltering works in place in the inflated list (each row moved over the filter bytes before it), so an 8-bit image's samples are that list, with no copy. The branch-free Paeth: adaptive filtering 607 → 476 ms with the same output; Paeth unfiltering of 36 MB 234 to 286 ms branchy → about 200 ms (written out by hand: as a call it was 232 ms). The generated code for that loop is about 80 instructions a byte (spills, a bounds check per index), which is the limit from the source side.
- **Example:** `examples/png_badge.my` (a badge drawn with std.draw, encoded, decoded back, as a palette PNG, a broken byte refused), 3/3 cases, the same output interpreted and natively; registered in `test_examples_run.py` and `test_examples_compile.py`; `test_examples_tests` OK. `tests.burn.test_doc_blocks` OK (the new page's block included).
- **Changed outside the owned files:** `tests/burn/test_png.py` and `tests/burn/drivers/png_roundtrip.my` (new: the encoders' burn test and its driver), `benchmarks/images_std.my` (the png slots and their numbers), the example and its two registrations, the index row on [[Language/Standard-library]], the std.png section of both copies of the skill's `reference/stdlib.md`, a row for `test_png.py` in [[Development/Testing]]'s table. `_images.py`, `test_images.py` and `image_driver.my` are unchanged.
- **Found on the way (toolchain, not filed):** a list slice copies element by element (`a[1:]` of 36 MB takes 95 ms, a copy loop by hand 121 ms), so the IDAT slice costs about 35 ms of the 60; `list.filled` is MYLA-949. A small function in the same module isn't inlined into a hot loop (the Paeth call cost 15 %).
- **Not done:** APNG, writing metadata chunks, lower bit depths for gray on encode (the plan doesn't ask for them). The encoder's speed is std.compress's deflate (4.7 of 5.2 s).

