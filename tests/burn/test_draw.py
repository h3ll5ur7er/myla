"""Burn tests: `std.draw` (MYLA-968) against exact areas, supersampled
references and Pillow.

A Myla driver (`DRIVER`) reads one command a line from stdin and answers
each with a line: the coverage `std.draw` gives a path (`fill`), a path's
stroke (`stroke`), aliased lines (`lines`), an image scaled onto a canvas
(`scaled`), or the bitmap font's glyphs (`glyphs`).

- **Exact areas** (no reference files): seeded random polygons, convex,
  star-shaped, self-intersecting and partly outside the raster, by the
  non-zero and the even-odd rule. The reference is computed here in plain
  Python: each polygon clipped to each pixel (Sutherland-Hodgman, which
  keeps the winding number's integral over the pixel), the signed areas
  summed, and folded as the rasteriser folds them (non-zero: the magnitude
  clamped to 1; even-odd: modulo 2, mirrored past 1). Tolerance: one level
  (the rasteriser sums in float64 and rounds once).
- **Curves and round strokes** against supersampled references
  (`data/draw/supersampled.json`): circles (one clipped), an ellipse, a
  rounded rectangle, a pie slice made with `arc`, an even-odd ring,
  round-joined round-capped polylines (the set of points within half the
  width of the polyline, which is exactly what that stroke covers),
  miter- and bevel-joined ones with square and butt caps (the union of the
  segments' rectangles and the joins' wedges) and a dashed line. Each pixel is sampled on a regular 32 by 32
  grid with numpy (`--vendor`). The driver flattens to 0.01 px, so the
  difference is the reference's sampling (at most 1/32 of a pixel where an
  edge runs along a row of samples) and the chords inside the curves:
  tolerance 4 levels a pixel, 0.4 on average, and the covered area within
  0.006 px a pixel of edge (2026-11-25, `0ad529e` and this test's
  module: at most 3, 0.31 and 0.0046).
- **Aliased drawing** against Pillow's `ImageDraw` (`data/draw/pillow.json`,
  `--vendor`): `line_aliased` must light exactly the pixels of
  `ImageDraw.line` (width 1) for lines in every octant, and `fill_rect` at
  whole pixels exactly those of `ImageDraw.rectangle`. `Image.resize` with
  NEAREST must equal `draw_image_scaled(…, Filter.Nearest)`, and BILINEAR,
  upscaling, `Filter.Bilinear` within one level.
- **The bitmap font**: `data/draw/font.txt` is its source; the constant
  `FONT` in `lib/std/draw.my` must be its encoding (`--font` prints it), and
  each glyph drawn by `text_bitmap` must light exactly the font's pixels.

The corpus runs on the self-hosted native build, plain and `--checked`, a
small part of it in the self-hosted interpreter. `--vendor` needs numpy and
Pillow; the tests need neither.
"""
from __future__ import annotations

import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest

from ._native import CAN_BUILD_NATIVE, SKIP_REASON
from ._tools import STDLIB_ROOT, selfhost_tool
from ._native import AS_CMD  # the machine's assembler (MYLA-926)

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
DATA = os.path.join(os.path.dirname(__file__), "data", "draw")
FONT_TXT = os.path.join(DATA, "font.txt")
SUPERSAMPLED = os.path.join(DATA, "supersampled.json")
PILLOW = os.path.join(DATA, "pillow.json")

DRIVER = """import std.draw as draw
import std.image as image
import std.io as io
import std.num as num
import std.process as process
import std.encoding as encoding
from std.draw import Path, FillRule, Join, Cap, Filter, Paint
from std.image import Image8, Layout, Rect
from std.vector32 import vec2

struct Tokens {
    t: [str],
    at: int,
}

impl Tokens {
    fun next(var self) -> str {
        if self.at >= self.t.len() {
            fail("out of tokens")
        }
        self.at += 1
        return self.t[self.at - 1]
    }

    fun f(var self) -> float32 {
        let s = self.next()
        return (num.parse_float(s).unwrap_or(0.0)) as float32
    }

    fun i(var self) -> int {
        return (num.parse_int(self.next()).unwrap_or(0i64)) as int
    }

    fun more(self) -> bool {
        return self.at < self.t.len()
    }

    // A path in a small language: M x y, L x y, Q cx cy x y,
    // C c1x c1y c2x c2y x y, Z, E cx cy rx ry (ellipse),
    // R x y w h r (rounded rectangle), A cx cy r a0 a1 (arc).
    fun path(var self) -> Path {
        var p = draw.path()
        while self.more() {
            let op = self.next()
            if op == "M" {
                let x = self.f()
                p.move_to(x, self.f())
            } else if op == "L" {
                let x = self.f()
                p.line_to(x, self.f())
            } else if op == "Q" {
                let cx = self.f()
                let cy = self.f()
                let x = self.f()
                p.quad_to(cx, cy, x, self.f())
            } else if op == "C" {
                let a = self.f()
                let b = self.f()
                let c = self.f()
                let d = self.f()
                let x = self.f()
                p.cubic_to(a, b, c, d, x, self.f())
            } else if op == "Z" {
                p.close()
            } else if op == "E" {
                let cx = self.f()
                let cy = self.f()
                let rx = self.f()
                p.append(draw.ellipse(cx, cy, rx, self.f()))
            } else if op == "R" {
                let x = self.f()
                let y = self.f()
                let w = self.f()
                let h = self.f()
                p.append(draw.rounded_rect(x, y, w, h, self.f()))
            } else if op == "A" {
                let cx = self.f()
                let cy = self.f()
                let r = self.f()
                let a0 = self.f()
                p.arc(cx, cy, r, a0, self.f())
            } else {
                fail(f"unknown path command {op}")
            }
        }
        return p
    }
}

fun fail(why: str) {
    io.eprintln(f"error: {why}")
    process.exit(1)
}

fun words(line: str) -> [str] {
    var out: [str] = []
    for w in line.split(" ") {
        if w.len() > 0 {
            out.push(w)
        }
    }
    return out
}

// The red samples of an RGBA canvas.
fun reds(c: draw.Canvas) -> [uint8] {
    var out: [uint8] = []
    for i in 0..c.image.width * c.image.height {
        out.push(c.image.data[i * 4])
    }
    return out
}

fun rgb_of(c: draw.Canvas) -> [uint8] {
    var out: [uint8] = []
    for i in 0..c.image.width * c.image.height {
        out.push(c.image.data[i * 4])
        out.push(c.image.data[i * 4 + 1])
        out.push(c.image.data[i * 4 + 2])
    }
    return out
}

fun answer(line: str) -> str {
    var t = Tokens { t: words(line), at: 0 }
    let cmd = t.next()
    if cmd == "fill" {
        // fill <nonzero|evenodd> <w> <h> <tolerance> <path>
        let rule = if t.next() == "evenodd" { FillRule.EvenOdd } else { FillRule.NonZero }
        let w = t.i()
        let h = t.i()
        let tol = t.f()
        let img = draw.coverage(t.path(), w, h, rule, tol)
        return encoding.hex_encode(img.data)
    }
    if cmd == "stroke" {
        // stroke <width> <miter|round|bevel> <butt|round|square> <w> <h> <tolerance> <dashes> <d...> <path>
        let width = t.f()
        let j = t.next()
        let k = t.next()
        let w = t.i()
        let h = t.i()
        let tol = t.f()
        var dash: [float32] = []
        let nd = t.i()
        for i in 0..nd {
            dash.push(t.f())
        }
        let join = if j == "round" { Join.Round } else if j == "bevel" { Join.Bevel } else { Join.Miter }
        let cap = if k == "round" { Cap.Round } else if k == "square" { Cap.Square } else { Cap.Butt }
        let st = draw.stroke_style(width).with_join(join).with_cap(cap).with_dash(dash)
        let img = draw.coverage(t.path().stroked(st, tol), w, h, FillRule.NonZero, tol)
        return encoding.hex_encode(img.data)
    }
    if cmd == "lines" {
        // lines <w> <h> then x0 y0 x1 y1 ..., white on black
        let w = t.i()
        let h = t.i()
        var c = draw.blank(w, h, image.rgb(0u8, 0u8, 0u8))
        while t.more() {
            let x0 = t.i()
            let y0 = t.i()
            let x1 = t.i()
            let y1 = t.i()
            c.line_aliased(x0, y0, x1, y1, image.rgb(255u8, 255u8, 255u8))
        }
        return encoding.hex_encode(reds(c))
    }
    if cmd == "rects" {
        // rects <w> <h> then x y w h ..., white on black, by fill_rect
        let w = t.i()
        let h = t.i()
        var c = draw.blank(w, h, image.rgb(0u8, 0u8, 0u8))
        while t.more() {
            let x = t.f()
            let y = t.f()
            let rw = t.f()
            let rh = t.f()
            c.fill_rect(x, y, rw, rh, Paint.Solid(image.rgb(255u8, 255u8, 255u8)))
        }
        return encoding.hex_encode(reds(c))
    }
    if cmd == "scaled" {
        // scaled <sw> <sh> <dw> <dh> <nearest|bilinear> <rgb hex>
        let sw = t.i()
        let sh = t.i()
        let dw = t.i()
        let dh = t.i()
        let filter = if t.next() == "nearest" { Filter.Nearest } else { Filter.Bilinear }
        let data = encoding.hex_decode(t.next()).unwrap_or([])
        let src = image.from_data<uint8>(sw, sh, Layout.Rgb, data).unwrap_or(image.new(1, 1, Layout.Rgb, 0u8))
        var c = draw.blank(dw, dh, image.rgb(0u8, 0u8, 0u8))
        c.draw_image_scaled(src, image.rect(0, 0, dw, dh), filter)
        return encoding.hex_encode(rgb_of(c))
    }
    if cmd == "glyphs" {
        // every glyph in a row, 32 to 126 and then a character outside
        var s = StringBuilder()
        for k in 32..127 {
            s.append_char((k as char))
        }
        s.append_char('é')
        let text = s.build()
        let (w, h) = draw.text_size(text)
        var c = draw.blank(w, h, image.rgb(0u8, 0u8, 0u8))
        c.text_bitmap(text, 0, 0, image.rgb(255u8, 255u8, 255u8))
        return encoding.hex_encode(reds(c))
    }
    fail(f"unknown command {cmd}")
    return ""
}

fun main() {
    var input = io.stdin()
    let text = input.read_to_end().unwrap_or("")
    var out = StringBuilder()
    for line in text.split("\\n") {
        if line.len() > 0 {
            out.append(answer(line))
            out.append("\\n")
        }
    }
    match io.write(1, out.build()) {
        Ok(()) => {}
        Err(_) => { process.exit(3) }
    }
}
"""

# --- the exact reference ----------------------------------------------------


def _clip(poly, x0, y0, x1, y1):
    """`poly` clipped to the box (Sutherland-Hodgman)."""
    def cut(pts, inside, inter):
        out = []
        n = len(pts)
        for i in range(n):
            a, b = pts[i], pts[(i + 1) % n]
            ia, ib = inside(a), inside(b)
            if ia:
                out.append(a)
                if not ib:
                    out.append(inter(a, b))
            elif ib:
                out.append(inter(a, b))
        return out

    def at_x(xc):
        return lambda a, b: (xc, a[1] + (b[1] - a[1]) * (xc - a[0]) / (b[0] - a[0]))

    def at_y(yc):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (yc - a[1]) / (b[1] - a[1]), yc)

    p = poly
    for inside, inter in ((lambda q: q[0] >= x0, at_x(x0)), (lambda q: q[0] <= x1, at_x(x1)),
                          (lambda q: q[1] >= y0, at_y(y0)), (lambda q: q[1] <= y1, at_y(y1))):
        if not p:
            return p
        p = cut(p, inside, inter)
    return p


def _signed_area(p) -> float:
    return sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1] for i in range(len(p))) / 2


def exact_coverage(polys, w: int, h: int, even_odd: bool) -> list[int]:
    """Each pixel's integral of the winding number, folded by the rule and
    scaled to 0..255 as std.draw does."""
    out = [0] * (w * h)
    boxes = [(min(q[0] for q in p), min(q[1] for q in p), max(q[0] for q in p), max(q[1] for q in p)) for p in polys]
    for y in range(h):
        for x in range(w):
            s = 0.0
            for poly, (bx0, by0, bx1, by1) in zip(polys, boxes):
                if bx1 <= x or bx0 >= x + 1 or by1 <= y or by0 >= y + 1:
                    continue
                c = _clip(poly, x, y, x + 1, y + 1)
                if len(c) >= 3:
                    s += _signed_area(c)
            c = abs(s)
            if even_odd:
                c = c - 2 * math.floor(c / 2)
                if c > 1:
                    c = 2 - c
            else:
                c = min(c, 1.0)
            out[y * w + x] = int(c * 255 + 0.5)
    return out


def _q(v: float) -> float:
    """A coordinate on a grid of 1/64, exact in float32 and in decimal."""
    return round(v * 64) / 64


def random_polygons(rng: random.Random, w: int, h: int):
    """A polygon set of one of several kinds, within or across the raster."""
    kind = rng.choice(["convex", "star", "random", "two", "outside"])
    polys = []
    count = 2 if kind == "two" else 1
    for _ in range(count):
        cx = rng.uniform(-0.2 * w, 1.2 * w) if kind == "outside" else rng.uniform(0.2 * w, 0.8 * w)
        cy = rng.uniform(-0.2 * h, 1.2 * h) if kind == "outside" else rng.uniform(0.2 * h, 0.8 * h)
        n = rng.randint(3, 9)
        r_max = 0.45 * min(w, h)
        pts = []
        if kind == "random":
            for _ in range(n):
                pts.append((_q(rng.uniform(-2, w + 2)), _q(rng.uniform(-2, h + 2))))
        else:
            angles = sorted(rng.uniform(0, 2 * math.pi) for _ in range(n))
            if kind == "star":
                angles = [2 * math.pi * k * 2 / (2 * n + 1) for k in range(n)]  # a star polygon {n/2}
            for a in angles:
                r = rng.uniform(0.3, 1.0) * r_max if kind != "star" else r_max
                pts.append((_q(cx + r * math.cos(a)), _q(cy + r * math.sin(a))))
        if rng.random() < 0.5:
            pts.reverse()
        polys.append(pts)
    return polys


def fill_command(polys, w: int, h: int, even_odd: bool) -> str:
    ops = []
    for p in polys:
        ops.append(f"M {p[0][0]!r} {p[0][1]!r}")
        ops.extend(f"L {x!r} {y!r}" for x, y in p[1:])
        ops.append("Z")
    rule = "evenodd" if even_odd else "nonzero"
    return f"fill {rule} {w} {h} 0.25 " + " ".join(ops)


# --- the supersampled scenes ------------------------------------------------

# name, width, height, the driver's command (tolerance 0.01), and the
# shape for numpy: ("circle", cx, cy, r), ("ellipse", cx, cy, rx, ry),
# ("rrect", x, y, w, h, r), ("pie", cx, cy, r, a0, a1), ("ring", cx, cy, r0,
# r1), ("capsule", hw, points), ("pieces", hw, points, join, cap),
# ("dashes", hw, a, b, pattern)
SCENES = [
    ("circle", 24, 24, "fill nonzero 24 24 0.01 E 11.3 12.6 8.7 8.7", ("circle", 11.3, 12.6, 8.7)),
    ("small circle", 8, 8, "fill nonzero 8 8 0.01 E 3.9 4.2 2.15 2.15", ("circle", 3.9, 4.2, 2.15)),
    ("clipped circle", 20, 16, "fill nonzero 20 16 0.01 E 17.5 -1.25 11.0 11.0", ("circle", 17.5, -1.25, 11.0)),
    ("ellipse", 32, 20, "fill nonzero 32 20 0.01 E 15.5 9.75 13.2 6.1", ("ellipse", 15.5, 9.75, 13.2, 6.1)),
    ("rounded rect", 30, 22, "fill nonzero 30 22 0.01 R 2.4 3.6 24.5 15.25 5.5", ("rrect", 2.4, 3.6, 24.5, 15.25, 5.5)),
    ("pie", 24, 24, "fill nonzero 24 24 0.01 M 12 12.5 A 12 12.5 10.5 0.3 2.2 Z", ("pie", 12.0, 12.5, 10.5, 0.3, 2.2)),
    ("ring", 26, 26, "fill evenodd 26 26 0.01 E 13 13 11.5 11.5 E 13 13 6.25 6.25", ("ring", 13.0, 13.0, 6.25, 11.5)),
    ("round stroke", 32, 24, "stroke 3.5 round round 32 24 0.01 0 M 3.5 4 L 27 6.5 L 9 20.25 L 29.5 21",
     ("capsule", 1.75, [(3.5, 4), (27, 6.5), (9, 20.25), (29.5, 21)])),
    ("thin round stroke", 24, 24, "stroke 1.25 round round 24 24 0.01 0 M 2 2 L 21.5 13.25 L 4.75 20",
     ("capsule", 0.625, [(2, 2), (21.5, 13.25), (4.75, 20)])),
    ("sharp round stroke", 30, 16, "stroke 5 round round 30 16 0.01 0 M 3 3 L 27 8 L 3 13",
     ("capsule", 2.5, [(3, 3), (27, 8), (3, 13)])),
    ("miter stroke", 32, 24, "stroke 4 miter square 32 24 0.01 0 M 4 5 L 24 7 L 10 18 L 27 19.5",
     ("pieces", 2.0, [(4, 5), (24, 7), (10, 18), (27, 19.5)], "miter", "square")),
    ("bevel stroke", 30, 24, "stroke 3 bevel butt 30 24 0.01 0 M 2.5 3 L 26 11.75 L 4 20",
     ("pieces", 1.5, [(2.5, 3), (26, 11.75), (4, 20)], "bevel", "butt")),
    ("dashed stroke", 32, 20, "stroke 2 round round 32 20 0.01 2 5 3 M 2 4 L 30 16.5",
     ("dashes", 1.0, (2, 4), (30, 16.5), [5, 3])),
]


def stroke_pieces(hw: float, pts, join: str, cap: str):
    """The convex polygons whose union is a miter- or bevel-joined stroke:
    a rectangle a segment (lengthened by `hw` at the ends for square caps)
    and each join's wedge on the outer side."""
    pieces = []
    dirs = []
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        length = math.hypot(bx - ax, by - ay)
        dirs.append(((bx - ax) / length, (by - ay) / length))
    for k, ((ax, ay), (bx, by)) in enumerate(zip(pts, pts[1:])):
        dx, dy = dirs[k]
        nx, ny = -dy * hw, dx * hw
        if cap == "square" and k == 0:
            ax, ay = ax - dx * hw, ay - dy * hw
        if cap == "square" and k == len(dirs) - 1:
            bx, by = bx + dx * hw, by + dy * hw
        pieces.append([(ax + nx, ay + ny), (bx + nx, by + ny), (bx - nx, by - ny), (ax - nx, ay - ny)])
    for k in range(1, len(pts) - 1):
        px, py = pts[k]
        (d0x, d0y), (d1x, d1y) = dirs[k - 1], dirs[k]
        cross = d0x * d1y - d0y * d1x
        side = -1 if cross > 0 else 1  # the outer side's normals
        n0 = (-d0y * hw * side, d0x * hw * side)
        n1 = (-d1y * hw * side, d1x * hw * side)
        wedge = [(px, py), (px + n0[0], py + n0[1])]
        if join == "miter":
            mx, my = n0[0] + n1[0], n0[1] + n1[1]
            k2 = hw * hw / (mx * n1[0] + my * n1[1])
            if math.hypot(mx * k2, my * k2) <= 4 * hw:
                wedge.append((px + mx * k2, py + my * k2))
        wedge.append((px + n1[0], py + n1[1]))
        pieces.append(wedge)
    return pieces


def dash_segments(a, b, pattern):
    """The dashes of the line from `a` to `b` as `(start, end)` points."""
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    out = []
    pos = 0.0
    k = 0
    while pos < length:
        end = min(pos + pattern[k % len(pattern)], length)
        if k % 2 == 0:
            t0, t1 = pos / length, end / length
            out.append(((a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0),
                        (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)))
        pos = end
        k += 1
    return out


def supersample(shape, w: int, h: int, n: int = 32):
    """The share of each pixel inside `shape`, sampled on an n by n grid."""
    import numpy as np
    off = (np.arange(n) + 0.5) / n
    xs = (np.arange(w)[:, None] + off[None, :]).reshape(-1)
    ys = (np.arange(h)[:, None] + off[None, :]).reshape(-1)
    X, Y = np.meshgrid(xs, ys)
    kind = shape[0]
    if kind == "circle":
        _, cx, cy, r = shape
        inside = (X - cx) ** 2 + (Y - cy) ** 2 <= r * r
    elif kind == "ellipse":
        _, cx, cy, rx, ry = shape
        inside = ((X - cx) / rx) ** 2 + ((Y - cy) / ry) ** 2 <= 1
    elif kind == "pie":
        _, cx, cy, r, a0, a1 = shape
        angle = np.mod(np.arctan2(Y - cy, X - cx), 2 * np.pi)
        inside = ((X - cx) ** 2 + (Y - cy) ** 2 <= r * r) & (angle >= a0) & (angle <= a1)
    elif kind == "ring":
        _, cx, cy, r0, r1 = shape
        d2 = (X - cx) ** 2 + (Y - cy) ** 2
        inside = (d2 <= r1 * r1) & (d2 >= r0 * r0)
    elif kind == "rrect":
        _, x, y, rw, rh, r = shape
        qx = np.abs(X - (x + rw / 2)) - (rw / 2 - r)
        qy = np.abs(Y - (y + rh / 2)) - (rh / 2 - r)
        outside = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r
        inside = outside <= 0
    elif kind == "pieces":
        _, hw, pts, join, cap = shape
        inside = np.zeros(X.shape, dtype=bool)
        for poly in stroke_pieces(hw, pts, join, cap):
            signs = []
            for (ax, ay), (bx, by) in zip(poly, poly[1:] + poly[:1]):
                signs.append((bx - ax) * (Y - ay) - (by - ay) * (X - ax))
            inside |= np.all([v >= 0 for v in signs], axis=0) | np.all([v <= 0 for v in signs], axis=0)
    elif kind in ("capsule", "dashes"):
        if kind == "capsule":
            _, hw, pts = shape
            segs = list(zip(pts, pts[1:]))
        else:
            _, hw, a, b, pattern = shape
            segs = dash_segments(a, b, pattern)
        d2 = np.full(X.shape, np.inf)
        for (ax, ay), (bx, by) in segs:
            dx, dy = bx - ax, by - ay
            t = np.clip(((X - ax) * dx + (Y - ay) * dy) / (dx * dx + dy * dy), 0, 1)
            d2 = np.minimum(d2, (X - ax - t * dx) ** 2 + (Y - ay - t * dy) ** 2)
        inside = d2 <= hw * hw
    else:
        raise ValueError(kind)
    share = inside.reshape(h, n, w, n).mean(axis=(1, 3))
    return [int(v) for v in np.floor(share.reshape(-1) * 255 + 0.5)]


# --- the Pillow scenes ------------------------------------------------------

LINE_W, LINE_H = 40, 32


def pillow_lines(seed: int = 5):
    """Lines in every octant, as `(x0, y0, x1, y1)`."""
    rng = random.Random(seed)
    lines = []
    for _ in range(40):
        lines.append((rng.randint(0, LINE_W - 1), rng.randint(0, LINE_H - 1), rng.randint(0, LINE_W - 1),
                      rng.randint(0, LINE_H - 1)))
    return lines


RECTS = [(1, 1, 5, 3), (10, 2, 1, 9), (3, 12, 20, 4), (30, 20, 9, 11), (0, 31, 40, 1)]


def scaled_source(seed: int = 9):
    rng = random.Random(seed)
    return 5, 4, bytes(rng.randrange(256) for _ in range(5 * 4 * 3))


SCALES = [(7, 9, "nearest"), (16, 12, "nearest"), (3, 2, "nearest"), (17, 13, "bilinear"), (10, 8, "bilinear")]


def vendor() -> None:
    """Writes the supersampled and Pillow references (needs numpy and Pillow)."""
    from PIL import Image, ImageDraw
    sup = {}
    for name, w, h, _, shape in SCENES:
        sup[name] = bytes(supersample(shape, w, h)).hex()
    with open(SUPERSAMPLED, "w", encoding="utf-8") as fh:
        json.dump({"made_by": "numpy, a 32 by 32 grid of samples a pixel (tests/burn/test_draw.py --vendor)",
                   "scenes": sup}, fh, indent=1)
        fh.write("\n")
    pil = {"made_by": f"Pillow {__import__('PIL').__version__} (tests/burn/test_draw.py --vendor)"}
    lines = []
    for ln in pillow_lines():
        im = Image.new("L", (LINE_W, LINE_H), 0)
        ImageDraw.Draw(im).line(ln, fill=255, width=1)
        lines.append([i for i, v in enumerate(im.tobytes()) if v])
    # each line as the indices of the pixels it lights
    pil["lines"] = lines
    im = Image.new("L", (LINE_W, LINE_H), 0)
    d = ImageDraw.Draw(im)
    for x, y, w, h in RECTS:
        d.rectangle((x, y, x + w - 1, y + h - 1), fill=255)
    pil["rects"] = im.tobytes().hex()
    sw, sh, data = scaled_source()
    src = Image.frombytes("RGB", (sw, sh), data)
    pil["scaled"] = [src.resize((dw, dh), Image.NEAREST if f == "nearest" else Image.BILINEAR).tobytes().hex()
                     for dw, dh, f in SCALES]
    with open(PILLOW, "w", encoding="utf-8") as fh:
        json.dump(pil, fh)
        fh.write("\n")


# --- the font -----------------------------------------------------------------

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUV"


def read_font() -> list[list[str]]:
    """The 96 glyphs of font.txt, each 10 rows of 5 pixels."""
    with open(FONT_TXT, encoding="utf-8") as fh:
        lines = [ln.rstrip("\n") for ln in fh if ln.strip() and not ln.startswith("# ")]
    glyphs = []
    for i in range(0, len(lines), 11):
        rows = lines[i + 1:i + 11]
        assert len(rows) == 10 and all(len(r) == 5 and set(r) <= {"#", "."} for r in rows), lines[i]
        glyphs.append(rows)
    return glyphs


def font_constant() -> str:
    """The Myla constant FONT for font.txt."""
    enc = "".join(ALPHABET[int(r.replace("#", "1").replace(".", "0"), 2)] for g in read_font() for r in g)
    parts = [enc[i:i + 80] for i in range(0, len(enc), 80)]
    return "const FONT: str = (" + " +\n    ".join(f'"{p}"' for p in parts) + ")"


# --- the tests ----------------------------------------------------------------


def _unhex(line: str) -> list[int]:
    return list(bytes.fromhex(line))


class DrawTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.mkdtemp()
        path = os.path.join(cls.tmp, "driver.my")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(DRIVER)
        cls.path = path
        cls.native = None
        cls.checked = None
        if CAN_BUILD_NATIVE:
            asm = subprocess.run([selfhost_tool("gen_main"), path, STDLIB_ROOT], capture_output=True, text=True,
                                 check=True)
            exe = os.path.join(cls.tmp, "driver")
            with open(exe + ".s", "w", encoding="utf-8") as fh:
                fh.write(asm.stdout)
            subprocess.run([*AS_CMD, "-o", exe + ".o", exe + ".s"], check=True)
            subprocess.run(["ld", "-o", exe, exe + ".o"], check=True)
            cls.native = exe
            cls.checked = os.path.join(cls.tmp, "driver-checked")
            subprocess.run([selfhost_tool("main"), "build", path, "-o", cls.checked, "--stdlib", STDLIB_ROOT,
                            "--checked"], capture_output=True, check=True)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_driver(self, how: str, commands: list[str]) -> list[str]:
        if how == "native":
            argv = [self.native]
        elif how == "checked":
            argv = [self.checked]
        else:
            argv = [selfhost_tool("main"), "run", self.path, "--stdlib", STDLIB_ROOT]
        proc = subprocess.run(argv, input="\n".join(commands) + "\n", capture_output=True, text=True, timeout=900)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = proc.stdout.splitlines()
        self.assertEqual(len(out), len(commands))
        return out

    def hows(self) -> list[str]:
        if self.native is None:
            self.skipTest(SKIP_REASON)
        return ["native", "checked"]

    # --- exact areas ---------------------------------------------------------

    def check_exact(self, how: str, count: int, sizes) -> None:
        rng = random.Random(942)
        cases = []
        for k in range(count):
            w, h = sizes[k % len(sizes)]
            polys = random_polygons(rng, w, h)
            even_odd = k % 3 == 2
            cases.append((polys, w, h, even_odd))
        out = self.run_driver(how, [fill_command(p, w, h, eo) for p, w, h, eo in cases])
        worst = 0
        for (polys, w, h, eo), line in zip(cases, out):
            got = _unhex(line)
            want = exact_coverage(polys, w, h, eo)
            diff = max(abs(a - b) for a, b in zip(got, want))
            worst = max(worst, diff)
            with self.subTest(how=how, polys=polys, even_odd=eo):
                self.assertLessEqual(diff, 1)
        self.assertLessEqual(worst, 1)

    def test_exact_area_native(self) -> None:
        for how in self.hows():
            self.check_exact(how, 120, [(16, 16), (23, 11), (9, 30)])

    def test_exact_area_interpreted(self) -> None:
        self.check_exact("interpreted", 6, [(8, 8), (11, 6)])

    # --- supersampled references ---------------------------------------------

    def test_supersampled(self) -> None:
        with open(SUPERSAMPLED, encoding="utf-8") as fh:
            ref = json.load(fh)["scenes"]
        for how in self.hows()[:1]:
            out = self.run_driver(how, [cmd for _, _, _, cmd, _ in SCENES])
            for (name, w, h, _, _), line in zip(SCENES, out):
                got = _unhex(line)
                want = _unhex(ref[name])
                self.assertEqual(len(got), w * h)
                diffs = [abs(a - b) for a, b in zip(got, want)]
                with self.subTest(scene=name):
                    self.assertLessEqual(max(diffs), 4, name)
                    self.assertLessEqual(sum(diffs) / len(diffs), 0.4, name)
                    edge = sum(1 for v in want if 0 < v < 255) or 1
                    self.assertLessEqual(abs(sum(got) - sum(want)) / 255, 0.006 * edge + 0.05, name)

    # --- Pillow ----------------------------------------------------------------

    def test_pillow(self) -> None:
        with open(PILLOW, encoding="utf-8") as fh:
            ref = json.load(fh)
        lines = pillow_lines()
        sw, sh, data = scaled_source()
        commands = [f"lines {LINE_W} {LINE_H} " + " ".join(map(str, ln)) for ln in lines]
        commands.append(f"rects {LINE_W} {LINE_H} " + " ".join(" ".join(map(str, r)) for r in RECTS))
        commands.extend(f"scaled {sw} {sh} {dw} {dh} {f} {data.hex()}" for dw, dh, f in SCALES)
        for how in self.hows()[:1]:
            out = self.run_driver(how, commands)
            for ln, line, lit_at in zip(lines, out, ref["lines"]):
                with self.subTest(line=ln):
                    self.assertEqual([i for i, v in enumerate(_unhex(line)) if v], lit_at)
            self.assertEqual(_unhex(out[len(lines)]), _unhex(ref["rects"]))
            for (dw, dh, f), line, want_hex in zip(SCALES, out[len(lines) + 1:], ref["scaled"]):
                got = _unhex(line)
                want = _unhex(want_hex)
                with self.subTest(scale=(dw, dh, f)):
                    if f == "nearest":
                        self.assertEqual(got, want)
                    else:
                        self.assertLessEqual(max(abs(a - b) for a, b in zip(got, want)), 1)

    # --- the font ----------------------------------------------------------------

    def test_font_constant(self) -> None:
        with open(os.path.join(_REPO, "lib", "std", "draw.my"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn(font_constant(), src, "draw.my's FONT is not font.txt: run `python3 -m tests.burn.test_draw --font`")

    def test_glyphs(self) -> None:
        glyphs = read_font()
        for how in (self.hows()[:1] + ["interpreted"]) if self.native else ["interpreted"]:
            got = _unhex(self.run_driver(how, ["glyphs"])[0])
            w = 6 * len(glyphs)
            for k, g in enumerate(glyphs):
                for row in range(10):
                    want = [255 if c == "#" else 0 for c in g[row]] + [0]
                    with self.subTest(how=how, glyph=k + 32, row=row):
                        self.assertEqual(got[row * w + k * 6:row * w + k * 6 + 6], want)


if __name__ == "__main__":
    if "--vendor" in sys.argv:
        vendor()
    elif "--font" in sys.argv:
        print(font_constant())
    else:
        unittest.main()
