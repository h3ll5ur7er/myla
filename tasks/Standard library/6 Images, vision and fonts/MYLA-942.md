---
id: MYLA-942
title: "std.draw: paths, a coverage rasteriser and an RGBA canvas"
type: feature
status: backlog
priority: medium
labels: [stdlib, images, graphics]
---
Step 4 of [[Project/Standard-library-roadmap/Images-vision-and-fonts]]. std.font renders through it, and the GUI ([[MYLA-63]]) would draw with it.

- **Owns:** `lib/std/draw.my`, `docs/Language/Standard-library/Draw.md`
- **Needs:** [[MYLA-933]]; std.vector32 and std.matrix32 as they are
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] `Path` with lines, quadratic and cubic curves, arcs, the shapes; flattening to a tolerance; transforms by `Mat3`; bounds
- [ ] The rasteriser: exact area coverage per pixel (as FreeType's smooth renderer computes it), non-zero and even-odd, clipped to the canvas; equal-area tests on shapes whose area is known
- [ ] `Canvas`: transform and clip stack, `fill`, `fill_rect`, `clear`, `fill_mask`, `draw_image`, `draw_image_scaled`, source-over in premultiplied 8 bits
- [ ] Strokes: width, joins (miter, round, bevel), caps (butt, round, square), dashes, as a stroked outline filled non-zero
- [ ] Paints: solid first; then linear and radial gradients and image patterns
- [ ] Pixel art and the built-in bitmap font: `set_pixel`, `line_aliased`, `text_bitmap` (ASCII, about 6×10, our own design)
- [ ] Rendered references for a set of scenes, compared with a tolerance of one level per channel at edges (the reference renderer and how its output was made recorded in the test)
- [ ] Measured natively: filling 10,000 random triangles and a 1000-point stroked polyline on 1024×1024
- [ ] `#test` cases on every public function that has values to compare (images up to about 16×16), test functions for the generic ones (D162), passing interpreted and `--native`, and on aarch64 (qemu) and wasm32 (Node)
- [ ] Its page below [[Language/Standard-library]] with a doc block that runs, the skill's `reference/stdlib.md`, and an example in `examples/`, registered
