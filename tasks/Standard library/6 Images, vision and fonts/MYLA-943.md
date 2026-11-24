---
id: MYLA-943
title: "std.font: TrueType parsing, glyph rendering and simple text layout"
type: feature
status: todo
priority: medium
labels: [stdlib, fonts, graphics]
---
Step 5 of [[Project/Standard-library-roadmap/Images-vision-and-fonts]].

- **Owns:** `lib/std/font.my`, `docs/Language/Standard-library/Font.md`, the vendored test font and its licence
- **Needs:** [[MYLA-942]], [[MYLA-931]], [[MYLA-945]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] `parse`: `head`, `hhea`, `hmtx`, `maxp`, `cmap` 4 and 12, `loca` (both formats), `glyf` (simple and composite, nesting at most 8 deep), `kern` 0, `name`, `OS/2`, collections; every offset checked
- [ ] Glyph outlines as `draw.Path`s; rasterised masks at a quarter-pixel offset; equal to the outline's exact area within a tolerance, and visually checked against Pillow's FreeType rendering of the vendored font (unhinted)
- [ ] `layout`, `measure`: cmap, advances, kerning, wrapping at spaces within `max_width`, `\n`, alignment, line height
- [ ] `GlyphCache` and `masks`; `Canvas.fill_mask` draws them
- [ ] An example: a paragraph rendered to a PNG
- [ ] Later steps, each its own box when it starts: `GPOS` pair kerning, `CFF` outlines, WOFF 1
- [ ] Its corpus and fuzz cases in [[MYLA-945]]'s harness: truncations and seeded mutations are `Ok` or `Err`, never a runtime error, natively plain and `--checked`
- [ ] `#test` cases on every public function that has values to compare (images up to about 16×16), test functions for the generic ones (D162), passing interpreted and `--native`, and on aarch64 (qemu) and wasm32 (Node)
- [ ] Its page below [[Language/Standard-library]] with a doc block that runs, the skill's `reference/stdlib.md`, and an example in `examples/`, registered
