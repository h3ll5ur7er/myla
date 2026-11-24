---
id: MYLA-933
title: "std.image: Image, Color, Rect, ImageError, quantize and the terminal preview"
type: feature
status: backlog
priority: medium
labels: [stdlib, images]
---
Step 2 of [[Project/Standard-library-roadmap/Images-vision-and-fonts]]: the type every other module of the plan builds on.

- **Owns:** `lib/std/image.my`, `docs/Language/Standard-library/Image.md`
- **Needs:** [[MYLA-930]] (its decisions on the type, the storage and the errors)
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] `Sample` with impls on `uint8`, `uint16`, `float32`; `Layout`; `Image<S>` and the aliases; `Color`, `Rect`, `ImageInfo`, `ImageError` (D168, `message()`, `Format`), `MAX_PIXELS`
- [ ] Construction (`new`, `from_data`), `Index`/`IndexSet` on `(x, y, c)`, `get`, `in_bounds`, `color_at`, `set_color`, `row`, `channel`, `merge`
- [ ] `convert` between layouts (BT.601 luma, checked against Pillow's `convert("L")` on every 8-bit RGB triple of a sample), `to_f32`, `to_u8`, `to_u16`, `map`
- [ ] `crop`, `paste` (clipped), `fill`, the flips, rotations by 90° and `transpose`, premultiplying alpha
- [ ] `quantize` (median cut, Floyd–Steinberg optionally) to an `Indexed` image, and back
- [ ] `ansi(img, columns)`: truecolor half blocks, scaled with an area filter
- [ ] Colours: `rgb`, `rgba`, `parse_color`, `with_alpha`, `lerp`, `Format`
- [ ] Sizes in `int64` wherever a product of dimensions is formed; `new` past 2^31 − 1 samples a named failure (as `grid.new`, D184)
- [ ] Measured: `convert` RGBA to gray and `flip_h` of a 4096×4096 image natively, against the loops by hand
- [ ] `#test` cases on every public function that has values to compare (images up to about 16×16), test functions for the generic ones (D162), passing interpreted and `--native`, and on aarch64 (qemu) and wasm32 (Node)
- [ ] Its page below [[Language/Standard-library]] with a doc block that runs, the skill's `reference/stdlib.md`, and an example in `examples/`, registered
