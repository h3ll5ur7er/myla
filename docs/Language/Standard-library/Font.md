# std.font

TrueType fonts ([[MYLA-943]], D311): `.ttf` files and `.ttc` collections parsed, glyph outlines as std.draw paths ([[Language/Standard-library/Draw]]), glyphs rasterised unhinted into coverage masks at a quarter of a pixel, and a simple text layout: characters to glyphs through `cmap`, advances, `kern` pairs, lines broken at spaces within a width and at `\n`, left, centred or right aligned. That is enough for Latin, Greek and Cyrillic UI text. The plan is [[Project/Standard-library-roadmap/Images-vision-and-fonts#std.font: TrueType and text (MYLA-943)]].

A font is untrusted input, read with every offset checked: a broken file is an `Err`, a broken glyph no outline, never a failure.

```myla
import std.font as font
from std.font import FontError, Align

fun main() {
    // the first bytes of a TrueType font, an OpenType CFF font and a collection
    for b in [[0u8, 1u8, 0u8, 0u8, 0u8, 0u8], [79u8, 84u8, 84u8, 79u8], [116u8, 116u8, 99u8, 102u8, 0u8, 1u8, 0u8, 0u8, 0u8, 0u8, 0u8, 3u8]] {
        print(f"{b.len()} bytes, {font.face_count(b)} face(s)")
    }
    // parsing bytes that are not a whole font is an error, never a failure
    let header = [0u8, 1u8, 0u8, 0u8, 0u8, 0u8, 0u8, 0u8, 0u8, 0u8, 0u8, 0u8]
    for (bytes, face) in [(header, 0), (header[:6], 0), (header, 2), ([1u8, 2u8, 3u8, 4u8, 5u8, 6u8, 7u8, 8u8, 9u8, 10u8, 11u8, 12u8], 0)] {
        match font.parse(bytes, face) {
            Ok(f) => print(f.family)
            Err(e) => print(f"{e}")
        }
    }
    // the layout's options, changed by copies
    let opts = font.layout_options().with_max_width(200.0).with_align(Align.Center).with_line_height(1.2)
    print(f"wrap at {opts.max_width} px, line height x{opts.line_height}, tabs of {opts.tab} spaces, kerned: {opts.kerning}")
}
// output:
// 6 bytes, 1 face(s)
// 4 bytes, 1 face(s)
// 12 bytes, 3 face(s)
// missing table 'head'
// truncated font
// no face 2 in the file
// not a TrueType font
// wrap at 200 px, line height x1.2, tabs of 4 spaces, kerned: true
```

With a font file, as `examples/font_text.my` does with the test font of the image corpus (`tests/burn/data/images/fonts/MylaTestSans.ttf`, a subset of Liberation Sans):

```myla fragment
let f = font.parse(fs.read_bytes(path)?, 0)?          // a Result<Font, FontError>
print(f"{f.family} {f.style}: {f.glyph_count} glyphs")  // Myla Test Sans Regular: 176 glyphs
let (w, h) = font.measure(f, "Hello, Myla!", 16.0)      // 83.58 by 17.88 px
let opts = font.layout_options().with_max_width(150.0).with_align(Align.Center)
let l = font.layout(f, "The quick brown fox jumps over the lazy dog.", 12.0, opts)   // 2 lines
var c = draw.blank(200, 40, image.rgb(255u8, 255u8, 255u8))
var cache = font.glyph_cache(f)
c.fill_masks(cache.masks(l, 4.0, 2.0), Paint.Solid(image.rgb(0u8, 0u8, 0u8)))
```

[TOC]

## Fonts

```myla fragment
pub fun parse(b: [uint8], index: int = 0) -> Result<Font, FontError>   // index: a face of a .ttc collection
pub fun face_count(b: [uint8]) -> int                                 // a collection's faces, 1 for a font, 0 for neither
pub struct Font { family: str, style: str, units_per_em: int, ascender: int, descender: int, line_gap: int,
    glyph_count: int, … }
pub enum FontError { Truncated, BadSignature, MissingTable(str), Unsupported(str), Corrupt(str), NoFace(int) }
```

`parse` reads the tables `head`, `hhea`, `hmtx`, `maxp`, `cmap`, `loca` and `glyf`, which a font must have, and `kern`, `name` and `OS/2` when it has them. It checks where each table is and that the arrays it uses fit, and keeps the file's bytes: the glyphs are read when they are asked for, so parsing takes a few microseconds whatever the font's size. `family` and `style` are the names 1 and 2 of the `name` table: a Windows Unicode record (UTF-16, English first), else a Unicode one, else a Mac Roman one; `""` without a `name` table. `ascender`, `descender` (negative) and `line_gap` are `hhea`'s, or `OS/2`'s typographic metrics when its `USE_TYPO_METRICS` bit says so. Every value is in font units, `units_per_em` to the em, y up from the baseline.

`FontError` is a bare enum with `message()` and `Format` (D168), separate from std.image's `ImageError`: a font is no image, and its errors name tables and faces. `Truncated` is a file that ends inside its header, its table directory or a table; `BadSignature` one that is no TrueType font; `MissingTable("glyf")` a table the font needs; `Unsupported` CFF outlines (an OpenType `OTTO` font) or a font without a Unicode `cmap` of format 4 or 12; `Corrupt` numbers out of their range (units per em outside 16 to 16384, a `loca` format other than 0 or 1, more horizontal metrics than glyphs); `NoFace(i)` a face index past the file's faces.

| Method | What it gives |
| --- | --- |
| `f.glyph(c: char) -> int` | The glyph of `c` through `cmap`, 0 (`.notdef`) for a character the font lacks |
| `f.advance(g) -> int`, `f.lsb(g) -> int` | Glyph `g`'s advance width and left side bearing (`hmtx`); 0 past the glyphs |
| `f.kerning(a, b) -> int` | The `kern` table's value for the pair, to add to `a`'s advance; 0 without one |
| `f.outline(g) -> Option<draw.Path>` | The glyph's contours in font units, y up: lines and quadratic curves, a closed subpath a contour; `None` for a glyph without contours (a space), past the glyphs, or broken |
| `f.scale(px: float32) -> float32` | Pixels a font unit at `px` pixels to the em |

The `cmap` subtable used is the best of the Unicode ones: (3, 10) of format 12, a Unicode platform one of format 12, (3, 1) of format 4, a Unicode platform one of format 4, then (3, 1) of format 12 and a symbol font's (3, 0). Format 12 covers the whole of Unicode, format 4 the Basic Multilingual Plane. Each is checked to fit in its table, and a glyph number past the font's glyphs is 0.

Glyphs are simple or composite. A simple glyph's points come with flags for on- and off-curve points, repeated flags and short coordinates; two off-curve points in a row have an implied on-curve point half way, and a contour that starts off the curve starts at its last point or half way between its last and first. A composite glyph places other glyphs, by offsets (scaled when `SCALED_COMPONENT_OFFSET` says so) or by matching a point of the component with a point of the glyph so far, with a scale, two scales or a 2 by 2 matrix. Components nest at most `MAX_DEPTH` (8) deep, and one glyph expands to at most 4096 components and 262,144 points, so a font that repeats its parts at every level stays small. The `kern` table is read in Microsoft's format: the first horizontal format 0 subtable, its pairs found by binary search.

## Glyph masks

```myla fragment
pub fun render_glyph(f: Font, g: int, px: float32, dx: float32 = 0.0) -> Mask   // std.draw's Mask
```

`render_glyph` gives glyph `g` at `px` pixels to the em, its outline moved right by `dx` pixels (the fraction of a pen position), as a coverage mask placed from the pen on the baseline: the mask's top left pixel is `(m.x, m.y)` pixels from it, y down, so a capital's mask has a negative `m.y`. The outline is unhinted and each pixel gets the exact area of it the outline covers, through std.draw's rasteriser. As FreeType does it, the points are first put on a grid of 1/64 pixel, and each quadratic curve is cut into 2^k lines of equal parameter steps, the fewest for which each piece's second difference is within a quarter pixel (its chord within 1/16 pixel of the curve), the points in 1/256 pixel: FreeType's `gray_render_conic`. That makes the masks match FreeType's unhinted renderer to a few levels. A glyph without an outline gives an empty mask (0 by 0), and so does a size that isn't positive.

## Layout

```myla fragment
pub fun layout(f: Font, text: str, px: float32, opts: LayoutOptions = layout_options()) -> TextLayout
pub fun measure(f: Font, text: str, px: float32) -> (float32, float32)
pub struct LayoutOptions { max_width: float32, align: Align, line_height: float32, tab: int, kerning: bool }
pub fun layout_options() -> LayoutOptions   // no wrapping, Align.Left, 1.0, 4, kerned
pub enum Align { Left, Center, Right }
pub struct TextLayout { glyphs: [Placed], width: float32, height: float32, lines: int, px: float32 }
pub struct Placed { glyph: int, x: float32, y: float32 }
```

`layout` places each character's glyph at its pen position: the pen moves by the glyphs' advances and the `kern` table's pairs (with `kerning`), in pixels, unrounded. A line ends at `\n` and, with a `max_width` other than 0, before a word that would pass it; a word wider than `max_width` stays whole on its line. Spaces at a break are dropped; spaces that start a paragraph indent it. A tab moves the pen to the next multiple of `tab` spaces' width. Lines are `line_height` times the font's line height apart (ascender minus descender plus line gap), the first baseline the ascender below the top. They are aligned within `max_width`, or within the widest line without one. Characters below U+0020 other than `\t` and `\n` are left out, and a character the font lacks is its `.notdef` glyph.

The result holds the placed glyphs (not the spaces, tabs and breaks), each at its pen position on its line's baseline from the layout's top left corner; `width`, the widest line's advance (trailing spaces not counted); `height`, from the first line's ascender to the last line's descender; the number of lines (0 for an empty text, 2 for a text that ends in `\n`); and the size. `measure` is `layout` with the default options, as `(width, height)`.

The `with_max_width`, `with_align`, `with_line_height`, `with_tab` and `with_kerning` methods give a changed copy of the options.

## The glyph cache and drawing

```myla fragment
pub fun glyph_cache(f: Font) -> GlyphCache
// cache.masks(var self, l: TextLayout, x: float32, y: float32) -> [Mask]
// cache.mask(var self, g: int, px: float32, x: float32, y: float32) -> Mask
// cache.count(self) -> int
// c.fill_masks(var self, ms: [Mask], paint: Paint)                               (a Canvas method)
// c.fill_text(var self, f: Font, text: str, x: float32, y: float32, px: float32, paint: Paint)
```

A `GlyphCache` keeps the masks it has rasterised, one per glyph, size and quarter-pixel offset. `masks` gives a layout's glyphs placed with its top left corner at `(x, y)` (pixels): each pen position's x is rounded to a quarter of a pixel and its y to a pixel, and the cache's mask for that glyph and quarter is moved there. Glyphs without an outline are left out. `mask` is the same for one glyph with its pen at `(x, y)` on the baseline.

The masks go onto a canvas with std.draw's `c.fill_mask(m, paint)`, or all at once with `c.fill_masks(ms, paint)`, which std.font adds to `Canvas`. `c.fill_text(f, text, x, y, px, paint)` lays out and draws in one call, with a cache of its own for that call. A cache is changed by `masks` (it is a `var self` method), and a canvas by its methods, so they stay two values: the cache gives the masks, the canvas draws them, and neither is copied.

```myla fragment
var cache = font.glyph_cache(f)
for line in ["first", "second"] {
    c.fill_masks(cache.masks(font.layout(f, line, 16.0), 10.0, y), paint)   // each glyph rasterised once
    y += 20.0
}
```

## Accuracy and speed

- **References** (`tests/burn/test_font.py`, against MYLA-945's corpus). Parsing is compared with a TrueType reader in Python: both faces' names and metrics, every glyph's advance, left side bearing and outline box (the box of its `glyf` header, composites included), every character of the `cmap` and every kerning pair. The 48 unhinted FreeType renderings of `A`, `g`, `@` and the composite `é` at 12, 24 and 48 px, at offsets of 0, ¼, ½ and ¾ pixel, have the same bitmap box and differ by at most 5 levels a pixel, 0.37 on average for the worst glyph (2026-11-25); the advances are FreeType's to 1/65536 pixel. Two strings with each glyph at its exact pen fraction differ by at most 5 levels; drawn through the cache, at quarter pixels, by at most 33 and 2.2 on average. Every glyph's mask at 48 px covers its curves' exact area within its perimeter times 1/16 px. Layouts of fixed and 200 random texts match a layout in Python by the rules above to 0.001 px.
- **Fuzzing**: every truncation of the `.ttf` and the `.ttc` up to 512 bytes and every 17th after, and 10,000 seeded mutations, each parsed in every face with every glyph outlined and rendered and a text laid out, natively plain and `--checked`: each an `Ok` or an `Err`, never a failure.
- **Speed**, natively (2026-11-25, a shared 4-core x86-64 machine): `parse` of the test font about 3 µs; the 804 characters of `benchmarks/images_pillow.py`'s paragraph at 16 px wrapped at 780 px, laid out in about 0.1 ms; laid out, rasterised with a new cache (153 masks) and drawn on an 800 by 400 canvas in about 5.5 ms, of which 2.9 ms make the canvas (`draw.blank`); with the cache kept, 3.8 ms. Pillow does the same work in 25 ms (`benchmarks/images_std.my`).

## Not yet

- `GPOS` pair kerning (the test font's `kern` table has the same pairs), `CFF` outlines (`.otf` fonts are `Unsupported`), WOFF 1, `GSUB` ligatures.
- Complex shaping (Arabic, Indic), bidirectional text, hinting, colour and bitmap glyphs, subpixel (LCD) antialiasing, vertical metrics and WOFF 2 are out of scope.
- Line breaking is at spaces and tabs only: a word longer than the width overflows its line, and there is no hyphenation or Unicode line breaking.
