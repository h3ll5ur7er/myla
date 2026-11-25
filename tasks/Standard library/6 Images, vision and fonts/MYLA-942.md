---
id: MYLA-942
title: "std.draw: paths, a coverage rasteriser and an RGBA canvas"
type: feature
status: review
priority: medium
labels: [stdlib, images, graphics]
---
Step 4 of [[Project/Standard-library-roadmap/Images-vision-and-fonts]]. std.font renders through it, and the GUI ([[MYLA-63]]) would draw with it.

- **Owns:** `lib/std/draw.my`, `docs/Language/Standard-library/Draw.md`, `tests/burn/test_draw.py`, `tests/burn/data/draw/`, `examples/draw_chart.my`
- **Needs:** [[MYLA-933]]; std.vector32 and std.matrix32 as they are
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] `Path` with lines, quadratic and cubic curves, arcs, the shapes; flattening to a tolerance; transforms by `Mat3`; bounds (`arc(cx, cy, r, start, end)` as a canvas's `arc`; no SVG-style `arc_to` yet)
- [x] The rasteriser: exact area coverage per pixel (as FreeType's smooth renderer computes it), non-zero and even-odd, clipped to the canvas; equal-area tests on shapes whose area is known
- [x] `Canvas`: transform and clip stack, `fill`, `fill_rect`, `clear`, `fill_mask`, `draw_image`, `draw_image_scaled`, source-over in premultiplied 8 bits (straight alpha kept in the image, as `Color` is; each result rounded once from the exact premultiplied value)
- [x] Strokes: width, joins (miter, round, bevel), caps (butt, round, square), dashes, as a stroked outline filled non-zero
- [x] Paints: solid first; then linear and radial gradients and image patterns
- [x] Pixel art and the built-in bitmap font: `set_pixel`, `line_aliased`, `text_bitmap` (ASCII, about 6×10, our own design)
- [x] Rendered references for a set of scenes, compared with a tolerance of one level per channel at edges (the reference renderer and how its output was made recorded in the test): one level against exact areas; curves and strokes against numpy's 32×32 supersampling within 4 levels (the sampling's own error), see Evidence
- [x] Measured natively: filling 10,000 random triangles and a 1000-point stroked polyline on 1024×1024
- [ ] `#test` cases on every public function that has values to compare (images up to about 16×16), test functions for the generic ones (D162), passing interpreted and `--native`, and on aarch64 (qemu) and wasm32 (Node): all but aarch64, as qemu-aarch64 isn't installed on the lane's machine
- [x] Its page below [[Language/Standard-library]] with a doc block that runs, the skill's `reference/stdlib.md`, and an example in `examples/`, registered

## Evidence

Measured on 2026-11-25 in the lane's worktree (branch `stdlib/MYLA-942` over `0ad529e`), on a shared 4-core x86-64 machine.

- **Module cases** (`lib/std/draw.my`, 84 cases: `#test` cases on the public functions and methods with values, test functions for the rest): `build/myla test lib/std/draw.my --stdlib lib` 84/84 passed; `--native` 84/84; `--target wasm32-wasi` with `MYLA_EMULATOR="node tools/wasm/run.mjs"` 84/84. aarch64 not run: no `qemu-aarch64` here. The test functions check exact per-pixel coverage of rectangles at fractional positions, convex polygons' coverage against the shoelace area (also reversed and even-odd), a circle against its flattened polygon and πr², the fill rules, masks moved by whole pixels, source-over against the exact float64 result (3000 random cases over opaque, transparent and translucent pixels, within half a level), fills, transforms, save/restore, clips, gradients, patterns, images (scaled nearest and bilinear), Bresenham, the font, the areas of strokes with each join, cap and dashes, the miter limit, the canvas's rasterising against masks over 40 fills with its scratch list reused, and points that are NaN, infinite or 10^30 (nothing fails).
- **Burn test** `python3 -m unittest tests.burn.test_draw`: 6 tests OK in 15 s. 120 random polygon sets (convex, star polygons, self-intersecting, partly outside, two at once, both rules) natively, plain and `--checked`, and 6 interpreted: every pixel within one level of the exact area computed in Python (Sutherland-Hodgman per pixel), the largest difference seen 1. Thirteen supersampled scenes (circles, a clipped circle, an ellipse, a rounded rectangle, a pie slice by `arc`, an even-odd ring, round-, miter- and bevel-joined strokes with round, square and butt caps, a dashed stroke) against numpy at 32×32 samples a pixel: at most 3 levels, at most 0.31 on average, areas within 0.005 px a pixel of edge. `line_aliased` lights exactly Pillow 13's `ImageDraw.line` pixels (40 lines, 752 pixels, 0 different), `fill_rect` at whole pixels equals `ImageDraw.rectangle`, `draw_image_scaled` nearest equals `Image.resize(NEAREST)`, bilinear upscaling is within one level of `Image.resize(BILINEAR)`. The 96 glyphs drawn by `text_bitmap` are exactly `data/draw/font.txt`, and `FONT` is its encoding. References come from `python3 -m tests.burn.test_draw --vendor` (numpy, Pillow 13), committed; the test needs neither.
- **Failing first**: the supersampled scenes failed by 55 levels (`sharp round stroke`) while the stroker's inner joins went through the vertex, whose loop the signed-area sum counts twice near the outline's edge; `inner_join` (the offset edges' crossing) brought it to 2. A first version of the row bounds (`lo`/`hi`) failed 4 module cases (a shape clipped on the right) before edges right of the raster were moved onto its border.
- **Speed** natively on 1024×1024 (`build/myla build`, bounds checks on): 10,000 translucent triangles with vertices in random 64-pixel boxes 0.11 s; 10,000 with vertices anywhere (about 90,000 pixels each) 8.5 s, about 100 million composited pixels a second; a 1000-point random polyline 3 px wide stroked 0.05 s (bevel) to 0.07 s (miter), a 1000-point random walk 3 ms. Before the canvas kept its scratch list, summed in float64 (float32 arithmetic is done in float64 and rounded after every operation) and skipped unchanged cells and the empty ends of rows, the same work took 0.47 s, 88 s and 0.10 s.
- **Example** `examples/draw_chart.my` (a bar chart with a stroked trend, axes and a title, printed as text): its cases pass, registered in `test_examples_run.EXPECTED` and `test_examples_compile.EXAMPLES`; interpreted and native output identical; `tests.burn.test_examples_run`, `_compile` and `_tests` OK.
- **Docs**: [[Language/Standard-library/Draw]]'s doc block checks, runs and prints the same interpreted and natively; the row on [[Language/Standard-library]]; the section `std.draw` in both copies of the skill's `reference/stdlib.md` (identical).
- **Private helpers to be replaced** (std.image of [[MYLA-933]] wasn't there yet): `pixel_color(img, x, y)` by `img.color_at(x, y)`, and `to_rgba(img)` by `img.convert(Layout.Rgba)`. Replaced by the integrator after the merge (84/84 cases interpreted and native).
