---
id: MYLA-941
title: "std.imgproc, tier A: colour, geometry, filters, morphology, edges, regions"
type: feature
status: review
priority: medium
labels: [stdlib, images, vision]
---
Step 4 of [[Project/Standard-library-roadmap/Images-vision-and-fonts]]: what most image programs reach for. Tier B is [[MYLA-944]].

- **Owns:** `lib/std/imgproc.my`, `docs/Language/Standard-library/Imgproc.md`
- **Needs:** [[MYLA-933]]; std.vector32, std.matrix32, std.unionfind as they are
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] Colour and point operations: `gray`, `to_rgb`, HSV, linear and sRGB, `invert`, `adjust`, `gamma`, `lut`, `threshold`, `otsu`, `adaptive_threshold`, `in_range`, `histogram`, `equalize`, `normalize`, `abs_diff`, `blend`, `apply_mask`
- [x] Geometry: `resize` with five filters, `thumbnail`, `rotate`, `warp_affine`, `warp_perspective`, `affine_from`, `perspective_from`, `pad`, `pyr_down`, `pyr_up`; `Border`
- [x] Filters: `convolve`, `convolve_sep`, `box_blur` (running sums), `gaussian_blur` (separable), `median` (sliding histogram), `sharpen`, `unsharp_mask`, `sobel`, `scharr`, `laplacian`, `gradients`
- [x] Morphology: `erode`, `dilate`, `morph`, `rect`, `cross`, `ellipse`
- [x] Edges, corners, matching: `canny`, `harris`, `good_features`, `match_template`, `min_max`, `integral`
- [x] Regions: `components` with region statistics, `flood_fill`, `distance_transform`
- [x] Quality: `mse`, `psnr`, `ssim`
- [x] A reference for each function, independent of the code: Pillow's where it has one (resize filters, Gaussian blur, rank filters, histograms) through vendored outputs, otherwise the textbook formula in a short Python reference over a few small images, with the tolerance stated per function
- [x] Measured natively at 1 MP: `resize` (each filter), `gaussian_blur` at sigma 2, `median` of radius 2, `canny`, `components`, beside Pillow where it has them
- [x] `#test` cases on every public function that has values to compare (images up to about 16×16), test functions for the generic ones (D162), passing interpreted and `--native`, and on aarch64 (qemu) and wasm32 (Node) — all but aarch64: qemu-aarch64 isn't installed on the lane's machine (aarch64 run by the integrator after the merge, 2026-11-25, under qemu: imgproc 168/168 with tier B (MYLA-944's run))
- [x] Its page below [[Language/Standard-library]] with a doc block that runs, the skill's `reference/stdlib.md`, and an example in `examples/`, registered

Not ticked: the aarch64 run (no qemu here; the integrator's CI `targets` job runs `test_std_modules` there).

## Notes

- Pillow's GaussianBlur is box approximations, so `gaussian_blur` is checked against a numpy Gaussian, not Pillow.
- `resize` of an `Image8` is Pillow's exactly (its coefficients, 22-bit fixed point, rows first, each pass rounded), except RGBA, which Pillow premultiplies.
- float32 arithmetic is several times slower natively than float64 or int32 (a 7-tap pass: 80 ms in float32, 18 ms in float64, 9 ms in int32 per megapixel), and `S.to_f32()`/`S.from_f32()` cost float32 work per sample: the module computes in int32/float64 and converts `uint8` through `to_unorm8`/`from_unorm8`. That float32 cost is a backend matter worth a task of its own.

## Evidence

On branch `stdlib/MYLA-941` (from `claude/stdlib-image-vision-plan-gm6jy5`), 2026-11-25, x86-64.

- Module cases: `build/myla test lib/std/imgproc.my --stdlib lib`: 114/114 interpreted, `--native` 114/114, `--target wasm32-wasi` (`MYLA_EMULATOR="node tools/wasm/run.mjs"`) 114/114. aarch64 not run (no qemu-aarch64). Soft TDD: the cases were written with the functions; their first run failed on four (a wrong expected `sinc(1.5)`, a guessed Pillow bilinear value, an off-by-one past the row end in `box_blur`'s running sum, a histogram expectation), all fixed. A later `empty_images` test function failed on `box_blur` of a 0-wide image (an index past the end), fixed with guards in `box_blur`, `median`, `canny` and `border_at`.
- Burn test `tests/burn/test_imgproc.py`: 108 cases against references vendored in `tests/burn/data/imgproc/` (300 KB gzipped) by `python3 -m tests.burn.test_imgproc --vendor` (Pillow 13, numpy 2.5, colorsys); the test needs neither. `python3 -m unittest tests.burn.test_imgproc`: OK (11 s); with `MYLA_TEST_TARGET=wasm32-wasi`: OK; the driver built `--checked`: every case passes. 104 cases match their reference exactly, among them Pillow's `resize` with Nearest, Bilinear, Bicubic and Lanczos3 shrinking and enlarging gray and RGB, BOX at whole factors, `convert("L")`, `MedianFilter(3)` on RGB and `(5)`, `MinFilter`/`MaxFilter(5)`, `histogram`, `ImageChops.difference`, `ImageOps.invert`, `numpy.pad`'s five modes, Canny (OpenCV's rules re-implemented in plain Python), components, the Euclidean distance (brute force). Within tolerance: `Area` at a fractional factor (53 of 391 samples off by 1: Pillow-style rounding between passes), `gaussian_blur` of an Image8 (15 of 2867 and 3 of 4059 off by 1: fixed point), a float `resize` (6e-8).
- Example `examples/edges.my` registered in `test_examples_run.py` and `test_examples_compile.py`: both pass, and `test_examples_tests` (its cases) passes. The page's doc block checks, runs and prints its output interpreted and natively (checked with test_doc_blocks's own functions on that page only).
- Measured natively at 1024×1024 gray, best of five, beside Pillow 13 on the same machine: `gray` of RGB 3.7 ms (Pillow 0.64); `resize` to 640×480 Nearest 0.8, Bilinear 12.6, Bicubic 15.3, Area 10.1, Lanczos3 22.1 ms (Pillow 0.08, 2.3, 3.7, 1.5 BOX, 5.4); RGB Bilinear 35.8 ms (5.5); `gaussian_blur` σ 2 47 ms (GaussianBlur(2) 9.0, approximate); `box_blur` r 2 27 ms (BoxBlur(2) 4.0); `median` r 2 102 ms (MedianFilter(5) 330); `erode` 5×5 33 ms (MinFilter(5) 228); `sobel` 33 ms; `canny` 37 ms; `components` 20 ms; `distance_transform` 87 ms; `warp_affine` 59 ms. Before the integer paths: Gaussian 85 ms, box 56, sobel 57, bilinear resize 21, warp 96.
- Private helper to be replaced: none needed — std.image's skeleton had what was used (`Image`, `new`, `from_data`, `layout_of`, indexing, `Sample`); `gray` and `to_rgb` live here as the plan has them. When MYLA-933 adds `img.convert(Layout.Gray)` it should give the same luma as `gray` (Pillow's integer formula).
- Outside the owned files: the `std.imgproc` row of [[Language/Standard-library]], the `std.imgproc` section of both copies of the skill's `reference/stdlib.md` (identical), `examples/edges.my` and its two registrations.
