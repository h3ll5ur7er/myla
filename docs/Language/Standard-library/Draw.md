# std.draw

2D vector drawing ([[MYLA-968]], D313): paths of lines and Bézier curves, a rasteriser that gives each pixel the exact share of it a path covers, strokes with joins, caps and dashes, and an RGBA canvas that fills, strokes and composites onto an `Image8` ([[Language/Standard-library/Image]]). It has a built-in bitmap font, so a program can write text with no font file; TrueType text goes through std.font, which hands this module its glyph outlines. The plan is [[Project/Standard-library-roadmap/Images-vision-and-fonts#std.draw: 2D vector drawing (MYLA-968)]].

```myla
import std.draw as draw
import std.image as image
from std.draw import Paint, FillRule, Join
from std.vector32 import vec2

fun main() {
    // the share of each pixel a triangle covers, exactly
    let tri = draw.polygon([vec2(0.0, 0.0), vec2(4.0, 0.0), vec2(0.0, 2.0)])
    let cov = draw.coverage(tri, 4, 2)
    for y in 0..2 {
        var row = StringBuilder()
        for x in 0..4 {
            row.append(f"{cov.data[y * 4 + x]:4}")
        }
        print(row.build())
    }

    // two squares overlapping: the even-odd rule leaves the overlap out
    var two = draw.rect(0.0, 0.0, 2.0, 2.0)
    two.append(draw.rect(1.0, 1.0, 2.0, 2.0))
    let eo = draw.coverage(two, 3, 3, FillRule.EvenOdd)
    print(f"{eo.data[4]} {eo.data[0]}")

    // a canvas: a rounded rectangle, a translucent curve, bitmap text
    var c = draw.blank(40, 20, image.rgb(255u8, 255u8, 255u8))
    c.fill(draw.rounded_rect(2.0, 2.0, 20.0, 12.0, 4.0), Paint.Solid(image.rgb(30u8, 120u8, 220u8)))
    var p = draw.path()
    p.move_to(4.0, 18.0)
    p.cubic_to(12.0, 6.0, 26.0, 26.0, 36.0, 10.0)
    c.stroke(p, draw.stroke_style(2.0).with_join(Join.Round), Paint.Solid(image.rgba(200u8, 30u8, 30u8, 128u8)))
    c.text_bitmap("ok", 26, 1, image.rgb(0u8, 0u8, 0u8))
    for (x, y) in [(10, 8), (11, 13), (30, 14), (28, 4)] {
        let k = c.image.data[(y * c.width() + x) * 4:(y * c.width() + x) * 4 + 4]
        print(f"({x}, {y}): {k[0]} {k[1]} {k[2]} {k[3]}")
    }
}
// output:
//  255 255 191  64
//  191  64   0   0
// 0 255
// (10, 8): 30 120 220 255
// (11, 13): 115 75 125 255
// (30, 14): 232 162 162 255
// (28, 4): 0 0 0 255
```

Coordinates are `float32` pixels, x to the right and y down. The pixel `(x, y)` is the square from `(x, y)` to `(x + 1, y + 1)`, so a rectangle at whole numbers covers whole pixels, and a line at `x = 3.5` crosses the middle of a column. Angles are radians, and a positive angle turns from the x axis towards the y axis, which is clockwise on the screen. Points are std.vector32's `Vec2` and transforms std.matrix32's `Mat3` ([[Language/Standard-library/Vector]], [[Language/Standard-library/Matrix]]).

[TOC]

## Paths

A `Path` is a list of subpaths, each begun by a move and made of lines and quadratic and cubic Bézier curves: its field `segs` holds them as `Seg.Move(p)`, `Line(p)`, `Quad(c, p)`, `Cubic(c1, c2, p)` and `Close`. Its commands are `var self` methods; the shapes are functions that return a closed path.

| Method or function | What it does |
| --- | --- |
| `path() -> Path` | An empty path |
| `p.move_to(x, y)` | Begins a subpath at `(x, y)` |
| `p.line_to(x, y)` | A line from the current point; without one it begins a subpath there, as a canvas's `lineTo` does |
| `p.quad_to(cx, cy, x, y)` | A quadratic curve with the control point `(cx, cy)` |
| `p.cubic_to(c1x, c1y, c2x, c2y, x, y)` | A cubic curve with two control points |
| `p.arc(cx, cy, r, start, end)` | An arc of the circle around `(cx, cy)` from the angle `start` to `end` (`end < start` turns the other way), as cubic curves of at most a quarter turn; a line joins the current point to its start |
| `p.close()` | Closes the subpath with a line back to its first point, which becomes the current point: a line after it starts a new subpath there |
| `p.append(other)` | Adds the subpaths of `other` |
| `p.is_empty() -> bool` | Whether the path has no commands |
| `p.transformed(m: Mat3) -> Path` | Every point through the affine `m` (`translation2d`, `rotation2d`, `scaling2d` and their products) |
| `p.bounds() -> Option<(Vec2, Vec2)>` | The box around every point, control points included, as `(min, max)`; `None` for a path without points |
| `p.flatten(tolerance = 0.25) -> [[Vec2]]` | Each subpath as a polyline within `tolerance` of the curves; a closed one ends at its first point again |
| `p.stroked(style, tolerance = 0.25) -> Path` | The outline of the path's stroke, a path to fill by the non-zero rule ([[#Strokes]]) |
| `rect(x, y, w, h)`, `rounded_rect(x, y, w, h, r)` | Rectangles, clockwise on the screen; the corners' radius at most half the shorter side |
| `circle(cx, cy, r)`, `ellipse(cx, cy, rx, ry)` | Four cubic curves, within 0.03 % of the radius of the true curve |
| `polygon(points: [Vec2])`, `polyline(points)`, `line(x0, y0, x1, y1)` | A closed polygon, an open polyline, a line (the last two for stroking) |

Flattening cuts each curve into lines of equal parameter steps, as many as keep every chord within the tolerance of the curve: the second derivative bounds the error (|B''| h² / 8, Wang's formula), so a curve that bends little gets few lines. The tolerance is in the path's units; `Canvas` flattens after its transform, to a quarter of a pixel (`TOLERANCE`).

## Rasterising

```myla fragment
pub struct Mask { image: Image8, x: int, y: int }   // a Gray coverage image placed at (x, y)
pub enum FillRule { NonZero, EvenOdd }

pub fun rasterize(path: Path, rule: FillRule = FillRule.NonZero, tolerance: float32 = TOLERANCE) -> Mask
pub fun rasterize_clipped(path: Path, clip: Rect, rule: FillRule = FillRule.NonZero, tolerance: float32 = TOLERANCE) -> Mask
pub fun coverage(path: Path, width: int, height: int, rule: FillRule = FillRule.NonZero, tolerance: float32 = TOLERANCE) -> Image8
```

The rasteriser computes, for every pixel, the area of it inside the outline: for each edge, the trapezoid it cuts off each cell it crosses, accumulated with the sign of its direction, and summed along each row. That is the "cover" and "area" of FreeType's smooth renderer folded into one list, as font-rs keeps them. The sum is the integral of the winding number over the pixel: non-zero takes its magnitude, clamped to 1, and even-odd folds it so 1 is inside and 2 outside again. The result is scaled to 0..255 and rounded once. A pixel that one simple outline crosses gets exactly its covered area (the burn test checks every pixel of random polygons against areas clipped with Sutherland-Hodgman, to one level). Where an outline crosses itself inside a pixel, the pixel gets the magnitude of the integral, as FreeType's does, which can be more than the area actually covered.

- `rasterize` gives a tight mask over the pixels the path reaches, anywhere, including negative coordinates. std.font caches glyph masks this way and draws them with `c.fill_mask`. A path whose box is more than 2^28 pixels is a failure: use `rasterize_clipped`.
- `rasterize_clipped` gives a mask over the part within `clip`, and `coverage` gives a whole `width` by `height` Gray image at the origin.
- Edges above or below the clip are dropped. Edges left of it are moved onto its left border, where they still cover the pixels to their right, and so are edges right of it, so a clipped shape is exact up to the border. Points that are not finite are skipped.
- An empty result is a 0 by 0 mask at `(0, 0)`.

## Canvas

```myla fragment
pub struct Canvas { image: Image8, transform: Mat3, clip: Rect, stack: [CanvasState], scratch: [float64] }
pub fun canvas(img: Image8) -> Canvas            // any layout, converted to RGBA
pub fun blank(width: int, height: int, background: Color) -> Canvas
```

`image` is always RGBA with straight (not premultiplied) alpha, as `Color` is. `transform` takes user space to pixels: paths, strokes and paints go through it. Pixel art, images and masks are placed in pixels without it. `clip` is the rectangle of pixels drawing may change. `scratch` is the rasteriser's, kept between fills so a fill doesn't build a list.

| Method | What it does |
| --- | --- |
| `c.width()`, `c.height()` | The image's size |
| `c.clip_bounds() -> Rect` | The clip within the image |
| `c.save()`, `c.restore()` | Push and pop the transform and the clip; `restore` without a `save` does nothing |
| `c.translate(dx, dy)`, `c.scale(sx, sy)`, `c.rotate(angle)`, `c.concat(m)`, `c.set_transform(m)` | Change user space: each applies before the current transform, as a canvas's do |
| `c.clip_to(r: Rect)` | Narrows the clip to its overlap with `r` (pixels) |
| `c.clear(color)` | Sets every pixel of the clip to `color`, alpha included |
| `c.fill(path, paint, rule = FillRule.NonZero)` | Fills a path |
| `c.fill_rect(x, y, w, h, paint)` | Fills a rectangle of user space |
| `c.stroke(path, style, paint)` | Strokes a path ([[#Strokes]]) |
| `c.fill_mask(m: Mask, paint)` | Composites `paint` through a coverage mask at `(m.x, m.y)`: how text arrives |
| `c.draw_image(src, x, y, opacity = 1.0)` | Draws an image of any layout with its top left pixel at `(x, y)` |
| `c.draw_image_scaled(src, dst: Rect, filter = Filter.Bilinear)` | Draws an image scaled into `dst`, each pixel sampling `src` at its centre: `Filter.Nearest`, or `Filter.Bilinear` between the four nearest pixels (premultiplied, the edges repeated) |

Compositing is source-over. The coverage scales the paint's alpha first, `a = (alpha × coverage + 127) / 255` (256 levels), and then the result is rounded once from the exact value. Over an opaque pixel each channel becomes `(s × a + d × (255 − a) + 127) / 255`. Over a translucent pixel the alpha is `a + d_a (1 − a)`, and each channel is the premultiplied sum divided by it, so a colour drawn on a transparent canvas keeps its channels. A module test checks this against the exact result, within half a level, for every kind of destination.

## Paints

```myla fragment
pub enum Paint { Solid(Color), Linear(Gradient), Radial(Gradient), Pattern(Image8) }
pub struct Gradient { start: Vec2, end: Vec2, radius: float32, stops: [Stop] }
pub struct Stop { offset: float32, color: Color }
pub fun linear_gradient(x0: float32, y0: float32, x1: float32, y1: float32, stops: [Stop]) -> Paint
pub fun radial_gradient(cx: float32, cy: float32, r: float32, stops: [Stop]) -> Paint
pub fun stop(offset: float32, color: Color) -> Stop
```

Gradients and patterns live in user space: each pixel's centre goes back through the inverse transform. A linear gradient runs from `start` (offset 0) to `end` (offset 1), and a radial one from its centre out to `radius`. Before the first stop and after the last, the end colours continue (the "pad" spread). Colours are interpolated premultiplied, so a fade to transparent doesn't darken, into a table of 256 entries. A pattern repeats its image in both directions from user space's origin, sampled at the nearest pixel.

## Strokes

```myla fragment
pub enum Join { Miter, Round, Bevel }
pub enum Cap { Butt, Round, Square }
pub struct Stroke { width: float32, join: Join, cap: Cap, miter_limit: float32, dash: [float32], dash_offset: float32 }
pub fun stroke_style(width: float32) -> Stroke   // miter joins (limit 4), butt caps, no dashes: SVG's defaults
// s.with_join(j), s.with_cap(c), s.with_dash(dash, offset = 0.0) give a changed copy
```

A stroke is turned into an outline and filled by the non-zero rule. Each subpath is flattened and, with a dash pattern, cut into dashes. Then it is widened by half the width on each side. On the outer side of a turn go the join's points: the miter's tip, which becomes a bevel past `miter_limit` times the width as SVG says, an arc for a round join, or nothing for a bevel. On the inner side the two offset edges meet at their crossing, so the outline doesn't overlap itself there. Where the segments are too short for that, the outline goes through the vertex itself, as Skia's stroker does, and the non-zero rule fills the small loop this makes. An open subpath gets caps. A closed one gets an outer and an inner outline in opposite directions. A zero-length subpath with round or square caps is a dot.

A dash pattern alternates the lengths drawn and left out. A list of odd length counts twice, and `dash_offset` starts that far into the pattern. A pattern that is empty, negative or adds up to nothing draws the path whole, and so does one that would make more than a million dashes.

The canvas strokes in user space and flattens to a quarter pixel after the transform, so a scale scales the width too.

## Pixel art and the bitmap font

| Method or function | What it does |
| --- | --- |
| `c.set_pixel(x, y, color)` | Sets one pixel, alpha included, if it is in the clip |
| `c.put_pixel(x, y, color)` | Blends `color` onto one pixel, if it is in the clip |
| `c.line_aliased(x0, y0, x1, y1, color)` | A line of whole pixels, both ends included (Bresenham's), `color` blended onto each |
| `c.text_bitmap(s, x, y, color, scale = 1)` | `s` in the built-in font, its first cell's top left corner at `(x, y)`, each font pixel `scale` by `scale`; `\n` starts a line below |
| `text_size(s, scale = 1) -> (int, int)` | The size `text_bitmap` gives `s`: the longest line by `GLYPH_WIDTH` (6), the lines by `GLYPH_HEIGHT` (10) |

The font was drawn for std.draw. It covers ASCII 32 to 126, and any other character is drawn as a box. Each glyph is 5 by 10 pixels in a 6 by 10 cell: capitals and digits on rows 1 to 7, lower case from row 3, descenders on rows 8 and 9. Its source is `tests/burn/data/draw/font.txt`, as pixel art, and `draw.my` keeps it as a string of 960 base-32 digits, a digit per row of a glyph. The burn test checks the two against each other and draws every glyph.

## Accuracy and speed

- **References** (`tests/burn/test_draw.py`). Random polygons, including convex, star-shaped, self-intersecting and clipped ones, by both rules, are compared with exact per-pixel areas computed in Python, within one level. Circles, ellipses, rounded rectangles, an even-odd ring and strokes of every join, cap and a dash pattern, at 0.01 px, are compared with numpy references sampled 32 × 32 a pixel, within 4 levels, 0.4 on average. Lines are compared with Pillow's `ImageDraw.line`, rectangles with `ImageDraw.rectangle`, and scaling with `Image.resize` (nearest: equal; bilinear upscaling: within one level).
- **Speed**, natively on 1024 × 1024 (measured on 2026-11-25 on a shared 4-core x86-64 machine, the working tree of [[MYLA-968]] over `0ad529e`): 10,000 random triangles within 64-pixel boxes, translucent, fill in about 0.11 s; 10,000 triangles with vertices anywhere on the canvas (about 90,000 pixels each) in about 8.5 s, about 100 million composited pixels a second; a polyline of 1000 random points, 3 pixels wide, strokes in 0.05 to 0.07 s depending on the join.
- At the default tolerance the chords of a curve lie inside it, by at most a quarter of a pixel. A thin, small circle loses a little area this way, as in other renderers that flatten. Pass a smaller tolerance to `rasterize` or `coverage` for more exact curves.

## Not yet

- Hairlines thinner than a pixel get their exact area, which makes them faint, with no minimum width.
- No conical (two-circle) gradients, no repeat or reflect spread, no transformed images (draw an image through `Paint.Pattern` for that), no clip paths (the clip is a rectangle of pixels), and no blend modes other than source-over.
- `line_aliased` visits every pixel of its line, even outside the clip.
