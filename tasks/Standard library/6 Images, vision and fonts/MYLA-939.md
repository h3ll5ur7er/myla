---
id: MYLA-939
title: "std.tiff: baseline TIFF, several pages, float samples"
type: feature
status: review
priority: low
labels: [stdlib, images, tiff]
---
Step 3 of [[Project/Standard-library-roadmap/Images-vision-and-fonts]].

- **Owns:** `lib/std/tiff.my`, `docs/Language/Standard-library/Tiff.md`
- **Needs:** [[MYLA-933]], [[MYLA-932]] (LZW, PackBits), [[MYLA-945]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] The IFD chain in both byte orders, every field type, offsets checked; `pages`, `tags`
- [x] Strips and tiles, planar configurations 1 and 2, none, PackBits, LZW and Deflate, predictors 2 and 3
- [x] Bilevel, gray, RGB, palette, extra samples as alpha (associated or not); 1, 4, 8, 16 bits and `float32`; `decode`, `decode16`, `decode_f32`
- [x] JPEG in TIFF, CCITT, BigTIFF, YCbCr and CMYK are `Unsupported(…)` by name
- [x] `encode`, `encode16`: strips of about 8 KB, none, LZW or Deflate with the predictor; Pillow and `tiffinfo` (when installed) read the output. `tiffinfo` isn't installed here: libtiff through ImageMagick 6 read the output instead (by hand, not in a committed test, see Evidence)
- [ ] The corpus (libtiff's pictures where their licence allows, and Pillow's output in every supported combination) decodes as Pillow decodes it. All 41 files of [[MYLA-945]]'s TIFF corpus decode as Pillow does (the big-endian float file as libtiff does); no libtiff pictures were vendored, and the corpus is the vendor script's writer, not Pillow's output in every combination
- [x] Its corpus and fuzz cases in [[MYLA-945]]'s harness: truncations and seeded mutations are `Ok` or `Err`, never a runtime error, natively plain and `--checked`
- [x] `#test` cases on every public function that has values to compare (images up to about 16×16), test functions for the generic ones (D162), passing interpreted and `--native`, and on aarch64 (qemu) and wasm32 (Node)
- [x] Its page below [[Language/Standard-library]] with a doc block that runs, the skill's `reference/stdlib.md`, and an example in `examples/`, registered

## Evidence

- **API shipped** ([[Language/Standard-library/Tiff]]): `decode(b, page = 0, max_pixels = image.MAX_PIXELS) -> Result<Image8, ImageError>`, `decode16`, `decode_f32`, `pages(b) -> Result<[ImageInfo], ImageError>`, `info(b) -> Result<ImageInfo, ImageError>` (added for std.imageio: page 0, `frames` the page count), `tags(b, page = 0) -> Result<[int: TagValue], ImageError>`, `encode(img: Image8, compression: Compression = Compression.Lzw) -> [uint8]`, `encode16`; `enum TagValue { Ints([int64]), Rationals([(int64, int64)]), Floats([float64]), Ascii(str), Bytes([uint8]) }` (`Eq`, `Format`), `enum Compression { Uncompressed, PackBits, Lzw, Deflate }`.
- **Order of work:** the harness's three TIFF classes existed before the module (skipped until it did); the first corpus run passed, the first fuzz run crashed (`same` on an empty `BitsPerSample` list: `list index 0 out of bounds`, fixed). The helpers' vectors went in with the code; one of them (the float predictor's) was wrong and failed first. Review then found a possible int32 overflow in the `max_output` given to the decompressors and an int64 one in the block count of a tiled planar page past 2^62 tiles (both fixed, the second with a case).
- **Cases:** 71/71 pass interpreted (`build/myla test lib/std/tiff.my`, about 2 s), `--native`, `--target aarch64-linux` (qemu) and `--target wasm32-wasi` (Node). They cover 17 small files made by the vendor script's TIFF writer (each read alike by Pillow 13 except the big-endian predictor-3 floats, which Pillow misreads), errors by name, and `encode`/`encode16` round trips of every layout and compression.
- **Corpus:** `python3 -m unittest tests.burn.test_images.TiffDecoder tests.burn.test_images.Tiff16LastPageDecoder tests.burn.test_images.TiffF32Decoder`: 15/15 pass in 27 s (corpus natively, `--checked`, interpreted on the smallest files, fuzz plain and `--checked`, 10,000 mutations and the truncations). Also 30,000 mutations `--checked` with each of the seeds 1, 2 and 3 for the three drivers: pass. The corpus classes pass with `MYLA_TEST_TARGET=aarch64-linux` and `wasm32-wasi` too. The 16-bit and float drivers are new rows of `CODECS` in `tests/burn/test_images.py` (with `_tiff_last_pages`, the entries of the last page of a multi-page file); no manifest entry needed a change.
- **Encoder against other readers** (by hand: 300×61 images of each layout at 8 and 16 bits with each compression, 32 files): Pillow 13 reads 28 of them to the same pixels and can't open the 4 of 16-bit gray and alpha (a mode it lacks); ImageMagick 6 (libtiff) reads all 32 without a warning, the same pixels where compared (gray, RGB, RGBA).
- **Speed** natively, 4096×4096 RGB, best of 3 (shared machine, load about 2): uncompressed encode 114 ms, decode 111 ms; LZW with the predictor 781 and 511 ms (16.2 MB); Deflate 3678 and 578 ms (14.3 MB, std.compress's level 6 dominates); PackBits 463 and 207 ms. Pillow's save and load of the same: 61/42, 828/268 (45 MB, no predictor), 1367/327, 173/38 ms.
- **Docs and example:** [[Language/Standard-library/Tiff]] (its doc block checks, runs and prints the same natively), the row on [[Language/Standard-library]], `## std.tiff` in both copies of the skill's `reference/stdlib.md`, `examples/tiff_files.my` (7/7 cases; registered in `test_examples_run.py` and `test_examples_compile.py`, which pass for it).
- **Found:** natively a list slice (`b[a:b]`) costs as much as a loop of `push`es, about 2 ns a byte (50 MB in 108 ms either way), so decoding an uncompressed 50 MB file can't go much below 110 ms. Not a bug, but a `memcpy` for slices would make every codec's copies about ten times cheaper. No private helpers of other lanes were needed.
