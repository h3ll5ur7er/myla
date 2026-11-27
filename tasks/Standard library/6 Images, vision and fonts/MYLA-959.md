---
id: MYLA-959
title: "std.image: Image, Color, Rect, ImageError, quantize and the terminal preview"
type: feature
status: review
priority: medium
labels: [stdlib, images]
---
Step 2 of [[Project/Standard-library-roadmap/Images-vision-and-fonts]]: the type every other module of the plan builds on.

- **Owns:** `lib/std/image.my`, `docs/Language/Standard-library/Image.md`
- **Needs:** [[MYLA-956]] (its decisions on the type, the storage and the errors)
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] `Sample` with impls on `uint8`, `uint16`, `float32`; `Layout`; `Image<S>` and the aliases; `Color`, `Rect`, `ImageInfo`, `ImageError` (D168, `message()`, `Format`), `MAX_PIXELS`
- [x] Construction (`new`, `from_data`), `Index`/`IndexSet` on `(x, y, c)`, `get`, `in_bounds`, `color_at`, `set_color`, `row`, `channel`, `merge`
- [x] `convert` between layouts (BT.601 luma, checked against Pillow's `convert("L")` on every 8-bit RGB triple of a sample), `to_f32`, `to_u8`, `to_u16`, `map`
- [x] `crop`, `paste` (clipped), `fill`, the flips, rotations by 90° and `transpose`, premultiplying alpha
- [x] `quantize` (median cut, Floyd–Steinberg optionally) to an `Indexed` image, and back
- [x] `ansi(img, columns)`: truecolor half blocks, scaled with an area filter
- [x] Colours: `rgb`, `rgba`, `parse_color`, `with_alpha`, `lerp`, `Format`
- [x] Sizes in `int64` wherever a product of dimensions is formed; `new` past 2^31 − 1 samples a named failure (as `grid.new`, D184)
- [x] Measured: `convert` RGBA to gray and `flip_h` of a 4096×4096 image natively, against the loops by hand
- [x] `#test` cases on every public function that has values to compare (images up to about 16×16), test functions for the generic ones (D162), passing interpreted and `--native`, and on aarch64 (qemu) and wasm32 (Node) — all but aarch64: this machine has no `qemu-aarch64` (aarch64 run by the integrator after the merge, 2026-11-25, under qemu: image 121/121)
- [x] Its page below [[Language/Standard-library]] with a doc block that runs, the skill's `reference/stdlib.md`, and an example in `examples/`, registered

## Evidence

Branch `stdlib/MYLA-959` over `0ad529e`, measured on 2026-11-24.

- **Tests:** `build/myla test lib/std/image.my` 121/121 passed interpreted, `--native` 121/121, `--target wasm32-wasi` under Node 121/121 (aarch64 not run: no `qemu-aarch64` here). Before the implementation the new test functions failed to check (`unknown function 'ansi'`, eight errors). `examples/images.my`: 8/8 cases; `tests.burn.test_examples_run`, `test_examples_tests` (45 tests) and `test_examples_compile` (40) OK, interpreted and native output the same; `tests.burn.test_doc_blocks` OK (5 tests, 40 s, the new page's block included).
- **Pillow 13 as the oracle** (run once, not in CI): `(R * 19595 + G * 38470 + B * 7471 + 0x8000) >> 16` equals `convert("L")` on all 16,777,216 RGB triples (0 mismatches); `uint8.mul_alpha` equals `convert("RGBa")` and `div_alpha` (truncated, unchanged at alpha 0) `"RGBa"` to `"RGBA"` on all 65,536 (value, alpha) pairs. The cases marked "Pillow" in the module are its values. Rounding through float32 would get uint16 premultiplication wrong (39196 × 5505 / 65535 = 3292.4997 rounds to 3293), hence the integer `mul_alpha`/`div_alpha` and a case for it.
- **Measured natively** (`myla build`, bounds checks on, 4096×4096 RGBA, fastest of 5 to 10 runs over several runs, at `6f95a1a`; the shared machine varies 10 to 15 %): `convert(Layout.Gray)` 76 to 90 ms against 74 to 86 ms for the loop by hand; `flip_h()` 200 to 228 ms against 197 to 226 ms; `premultiplied()` 222 to 232 ms against 226 to 228 ms (it was 1.32 s through float32 before `mul_alpha`); `to_f32()` 1.44 to 1.50 s against 1.36 s by hand (making a float32 list that size alone takes 0.48 s); `rotate90()` 343 ms, `crop` to 2048² 50 ms, `fill` 134 ms, `ansi(img, 80)` 221 ms. `quantize` of a 1024² image of about a million colours to 256: 0.53 to 0.59 s dithered, 0.69 s not (splitting boxes by a counting sort took it from 0.97 s); of 251 colours 0.09 s.
- **Changed outside the owned files:** `examples/images.my` and its rows in `tests/burn/test_examples_run.py` and `test_examples_compile.py`, the index row on [[Language/Standard-library]], the std.image section of both copies of the skill's `reference/stdlib.md`.
- **Additions to the skeleton** (no declaration renamed or changed): `Sample` gained `luma(r, g, b)`, `mul_alpha(a)` and `div_alpha(a)` (every impl is in this module); `Image` gained `bounds()`. The plan's `to_u8(f: ImageF)` is a method on every sample type, `img.to_u8()`, as `to_f32` and `to_u16` are. `ansi` is generic over `Sample` rather than taking only an `Image8`.
- **Not done:** `quantize` spends most of its time in the nearest-colour search (a palette sorted by red, searched outwards); an inverse colour map would be faster for big images.
