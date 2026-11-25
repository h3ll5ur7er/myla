"""Burn tests: `std.imgproc`'s tier B (MYLA-944) against OpenCV and ground truth.

As `test_imgproc` (tier A), each case runs one function through a driver
(`DRIVER`, built natively once) on inputs pure Python makes from a seed, and
compares what it writes with an expected output vendored in
`tests/burn/data/imgproc_b/` (`<case>.gz`). The expected outputs were made
once by `python -m tests.burn.test_imgproc_b --vendor` with OpenCV 5.1
(`opencv-python-headless`, in a throwaway virtual environment) and numpy;
the test itself needs neither.

Two kinds of reference:

- OpenCV's own function where std.imgproc follows it: `findContours`
  (`CHAIN_APPROX_NONE`, each retrieval mode, the hierarchy as parents),
  `contourArea`, `arcLength`, `boundingRect`, `convexHull`, `minAreaRect`
  (its corners, `boxPoints`), `moments` of contours and images, `HuMoments`,
  `pointPolygonTest`, `HoughLinesWithAccumulator`, `FastFeatureDetector`,
  `erode`/`dilate` with large rectangles, `bilateralFilter`, `watershed`
  and `CLAHE`.
- Ground truth where std.imgproc's method is its own (ORB's sampling
  pattern, RANSAC's random numbers, the probabilistic Hough transform's
  order, the circle Hough transform's radius estimate, Ramer-Douglas-Peucker's
  start): polygons with known corners, drawn lines and circles, a known
  homography and affine map of random points with 50% outliers, a scene
  under a known rotation and scale (ORB's matches), and a smooth scene moved
  by a known subpixel translation (optical flow).

Each case states its tolerance (`exact`, `rel e`, `abs d`, or a named
geometric check, see `compare`).
"""
from __future__ import annotations

import gzip
import math
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from array import array

from ._native import CAN_BUILD_NATIVE, SKIP_REASON, check_file, native_build, run_argv
from .test_imgproc import Img, Lcg, blobs, scene

DATA = os.path.join(os.path.dirname(__file__), "data", "imgproc_b")

DRIVER = r'''import std.image as image
from std.image import Image, Image8, ImageF, Layout
import std.imgproc as ip
from std.imgproc import RetrievalMode
import std.vector32 as v32
from std.vector32 import Vec2
import std.matrix32 as m32
import std.fs as fs
import std.num as num
import std.process as process
import std.float as fl
import std.time as time
import std.random as random
import std.list as list_m

fun u32_at(b: [uint8], i: int) -> int {
    return (b[i] as int) | ((b[i + 1] as int) << 8) | ((b[i + 2] as int) << 16) | ((b[i + 3] as int) << 24)
}

fun load8(path: str) -> Image8 {
    let b = fs.read_bytes(path).expect("an input")
    let w = u32_at(b, 4)
    let h = u32_at(b, 8)
    let c = b[12] as int
    let layout = image.layout_of(c).expect("a layout")
    return image.from_data(w, h, layout, b[16:16 + w * h * c]).expect("the samples")
}

fun save8(path: str, img: Image8) {
    var out = [77u8, 89u8, 73u8, 77u8]
    for v in [img.width, img.height] {
        out.push((v & 255) as uint8)
        out.push(((v >> 8) & 255) as uint8)
        out.push(((v >> 16) & 255) as uint8)
        out.push(((v >> 24) & 255) as uint8)
    }
    out.push(img.layout.channels() as uint8)
    out.push(0u8)
    out.push(0u8)
    out.push(0u8)
    out.extend(img.data)
    fs.write_bytes(path, out).expect("written")
}

fun save_text(path: str, lines: [str]) {
    var sb = StringBuilder()
    for l in lines {
        sb.append(l)
        sb.append("\n")
    }
    fs.write_to_file(path, sb.build()).expect("written")
}

fun numbers(path: str) -> [float64] {
    let t = fs.read_to_string(path).expect("a text input")
    var out: [float64] = []
    for w in t.words() {
        out.push(num.parse_float(w).expect(f"a number: {w}"))
    }
    return out
}

fun fnum(x: float64) -> str {
    return num.format_float(x)
}

fun f(s: str) -> float32 {
    return num.parse_float(s).expect(f"a number: {s}") as float32
}

fun i(s: str) -> int {
    return num.parse_int32(s).expect(f"an integer: {s}")
}

fun mode(s: str) -> RetrievalMode {
    return match s {
        "external" => RetrievalMode.External
        "list" => RetrievalMode.List
        "tree" => RetrievalMode.Tree
        _ => panic(f"mode {s}")
    }
}

fun pts_text(ps: [(int, int)]) -> str {
    var parts: [str] = []
    for (x, y) in ps {
        parts.push(f"{x} {y}")
    }
    return parts.join(" ")
}

fun vec_text(ps: [Vec2]) -> str {
    var parts: [str] = []
    for p in ps {
        parts.push(fnum(p.x as float64))
        parts.push(fnum(p.y as float64))
    }
    return parts.join(" ")
}

fun moments_text(m: ip.Moments) -> str {
    let xs = [m.m00, m.m10, m.m01, m.m20, m.m11, m.m02, m.m30, m.m21, m.m12, m.m03,
        m.mu20, m.mu11, m.mu02, m.mu30, m.mu21, m.mu12, m.mu03,
        m.nu20, m.nu11, m.nu02, m.nu30, m.nu21, m.nu12, m.nu03]
    return xs.map((x: float64) => fnum(x)).join(" ")
}

// Point pairs "sx sy dx dy" of a text input.
fun pairs(path: str) -> ([Vec2], [Vec2]) {
    let v = numbers(path)
    var a: [Vec2] = []
    var b: [Vec2] = []
    var k = 0
    while k + 3 < v.len() {
        a.push(v32.vec2(v[k] as float32, v[k + 1] as float32))
        b.push(v32.vec2(v[k + 2] as float32, v[k + 3] as float32))
        k += 4
    }
    return (a, b)
}

fun estimate_text(r: Option<(m32.Mat3, [bool])>) -> [str] {
    let Some((m, mask)) = r else {
        return ["none"]
    }
    var out: [str] = []
    for row in 0..3 {
        for col in 0..3 {
            out.push(fnum(m[(row, col)] as float64))
        }
    }
    out.push(mask.map((b: bool) => if b { "1" } else { "0" }).join(""))
    return out
}

// A 1024 by 1024 scene for the timings: gradients, rectangles, a disc and
// noise.
fun scene(shift: float64) -> Image8 {
    var img: Image8 = image.new(1024, 1024, Layout.Gray, 0u8)
    var s: uint32 = 12345u32
    for y in 0..1024 {
        for x in 0..1024 {
            s = s.wrapping_mul(1664525u32).wrapping_add(1013904223u32)
            let noise = ((s >> 24u32) as int) % 16
            let fx = (x as float64) - shift
            let fy = (y as float64) + shift * 0.5
            let wave = 60.0 * (fx * 0.05).sin() * (fy * 0.037).cos()
            let dx = fx - 512.0
            let dy = fy - 400.0
            let disc = if dx * dx + dy * dy < 200.0 * 200.0 { 80.0 } else { 0.0 }
            let block = if ((x / 64) + (y / 48)) % 3 == 0 { 50.0 } else { 0.0 }
            img.data[y * 1024 + x] = (((100.0 + wave + disc + block) as int + noise) % 256) as uint8
        }
    }
    return img
}

fun bench(op: str, reps: int) {
    let img = scene(0.0)
    let edges = ip.canny(img, 80.0f32, 200.0f32)
    let mask = ip.threshold(img, 150u8)
    let moved = ip.warp_affine(img, m32.translation2d(v32.vec2(2.5f32, -1.5f32)), 1024, 1024)
    var rng = random.seeded(5u64)
    var src: [Vec2] = []
    var dst: [Vec2] = []
    for k in 0..1000 {
        let x = rng.float() * 1000.0
        let y = rng.float() * 1000.0
        src.push(v32.vec2(x as float32, y as float32))
        if k % 2 == 0 {
            let z = 0.0001 * x + 0.00005 * y + 1.0
            dst.push(v32.vec2(((1.1 * x + 0.05 * y + 7.0) / z) as float32, ((-0.03 * x + 0.95 * y + 3.0) / z) as float32))
        } else {
            dst.push(v32.vec2((rng.float() * 1000.0) as float32, (rng.float() * 1000.0) as float32))
        }
    }
    var pts: [Vec2] = []
    for k in 0..200 {
        pts.push(v32.vec2((100 + (k % 20) * 40) as float32, (100 + (k / 20) * 80) as float32))
    }
    var best: int64 = 0x7FFFFFFFFFFFFFFF
    var check = 0
    for _ in 0..reps {
        let t0 = time.now_ns()
        let r = match op {
            "find_contours" => ip.find_contours(mask).len()
            "hough_lines" => ip.hough_lines(edges, 1.0f32, (fl.PI / 180.0) as float32, 150).len()
            "fast" => ip.fast(img, 20).len()
            "orb" => ip.orb(img, 500).len()
            "find_homography" => {
                let (_, inl) = ip.find_homography(src, dst, 3.0f32).expect("found")
                inl.count((b: bool) => b)
            }
            "optical_flow" => ip.optical_flow(img, moved, pts, 21, 3).expect("same size").count((p: (Vec2, bool)) => p.1)
            "bilateral" => ip.bilateral(img, 9, 50.0f32, 5.0f32).data[1000] as int
            "erode_rect" => ip.erode(img, ip.rect(15, 15)).data[1000] as int
            "clahe" => ip.clahe(img).data[1000] as int
            "watershed" => {
                var marks = list_m.filled(1024 * 1024, 0i32)
                for k in 0..64 {
                    marks[(64 + (k / 8) * 120) * 1024 + 64 + (k % 8) * 120] = (k + 1) as int32
                }
                ip.watershed(img, marks)[5000] as int
            }
            _ => panic(f"bench {op}")
        }
        let dt = time.now_ns() - t0
        check += r
        if dt < best {
            best = dt
        }
    }
    print(f"{op} {(best as float64) / 1000000.0} ms ({check})")
}

fun main() {
    let a = process.args()
    let op = a[1]
    if op == "bench" {
        bench(a[2], i(a[3]))
        return
    }
    let out = a[2]
    let inp = a[3]
    match op {
        "contours" => {
            var lines: [str] = []
            for c in ip.find_contours(load8(inp), mode(a[4])) {
                lines.push(f"{if c.hole { 1 } else { 0 }} {c.parent} {pts_text(c.points)}")
            }
            save_text(out, lines)
        }
        "areas" => save_text(out, ip.find_contours(load8(inp)).map((c: ip.Contour) => fnum(ip.contour_area(c.points, true))))
        "lengths" => save_text(out, ip.find_contours(load8(inp)).map((c: ip.Contour) => fnum(ip.arc_length(c.points, a[4] == "closed"))))
        "rects" => save_text(out, ip.find_contours(load8(inp)).map((c: ip.Contour) => {
            let r = ip.bounding_rect(c.points)
            return f"{r.x} {r.y} {r.w} {r.h}"
        }))
        "hulls" => save_text(out, ip.find_contours(load8(inp)).map((c: ip.Contour) => pts_text(ip.convex_hull(c.points))))
        "approx" => save_text(out, ip.find_contours(load8(inp), RetrievalMode.External).map((c: ip.Contour) => pts_text(ip.approx_poly(c.points, f(a[4]), true))))
        "min_rects" => save_text(out, ip.find_contours(load8(inp)).map((c: ip.Contour) => {
            let r = ip.min_area_rect(c.points)
            return f"{fnum(r.center.x as float64)} {fnum(r.center.y as float64)} {fnum((r.size.x as float64) * (r.size.y as float64))} {vec_text(r.corners())}"
        }))
        "moments" => save_text(out, ip.find_contours(load8(inp)).map((c: ip.Contour) => moments_text(ip.moments(c.points))))
        "hu" => save_text(out, ip.find_contours(load8(inp)).map((c: ip.Contour) => ip.hu_moments(ip.moments(c.points)).map((x: float64) => fnum(x)).join(" ")))
        "image_moments" => save_text(out, [moments_text(ip.image_moments(load8(inp), a[4] == "binary"))])
        "pip" => {
            let cs = ip.find_contours(load8(inp), RetrievalMode.External)
            var lines: [str] = []
            for c in cs {
                var parts: [str] = []
                for y in 0..12 {
                    for x in 0..16 {
                        let p = v32.vec2((x * 4) as float32 + 0.5f32, (y * 4) as float32)
                        parts.push(f"{ip.point_in_polygon(c.points, p)} {fnum(ip.polygon_distance(c.points, p))}")
                    }
                }
                lines.push(parts.join(" "))
            }
            save_text(out, lines)
        }
        "hough_lines" => save_text(out, ip.hough_lines(load8(inp), f(a[4]), f(a[5]), i(a[6])).map((l: ip.Line) => f"{fnum(l.rho as float64)} {fnum(l.theta as float64)} {l.votes}"))
        "hough_segments" => save_text(out, ip.hough_segments(load8(inp), 1.0f32, (fl.PI / 180.0) as float32, i(a[4]), i(a[5]), i(a[6]), 7u64).map((s: ip.Segment) => f"{s.x0} {s.y0} {s.x1} {s.y1}"))
        "hough_circles" => save_text(out, ip.hough_circles(load8(inp), i(a[4]), i(a[5]), f(a[6]), 100.0f32, i(a[7]), 0.3f32).map((c: ip.Circle) => f"{fnum(c.center.x as float64)} {fnum(c.center.y as float64)} {fnum(c.radius as float64)}"))
        // (OpenCV gives no score without the suppression)
        "fast" => save_text(out, ip.fast(load8(inp), i(a[4]), a[5] == "nms").map((k: ip.Keypoint) => if a[5] == "nms" { f"{k.pt.x as int} {k.pt.y as int} {k.score as int}" } else { f"{k.pt.x as int} {k.pt.y as int}" }))
        "orb" => {
            // features of two views, matched: the pairs of points
            let fa = ip.orb(load8(inp), i(a[5]))
            let fb = ip.orb(load8(a[4]), i(a[5]))
            var lines = [f"{fa.len()} {fb.len()}"]
            for m in ip.match_features(fa, fb, true) {
                let p = fa[m.a].keypoint.pt
                let q = fb[m.b].keypoint.pt
                lines.push(f"{fnum(p.x as float64)} {fnum(p.y as float64)} {fnum(q.x as float64)} {fnum(q.y as float64)} {m.distance}")
            }
            save_text(out, lines)
        }
        "homography" => {
            let (s, d) = pairs(inp)
            save_text(out, estimate_text(ip.find_homography(s, d, f(a[4]), 3u64)))
        }
        "affine" => {
            let (s, d) = pairs(inp)
            save_text(out, estimate_text(ip.find_affine(s, d, f(a[4]), 3u64)))
        }
        "flow" => {
            let v = numbers(a[5])
            var pts: [Vec2] = []
            var k = 0
            while k + 1 < v.len() {
                pts.push(v32.vec2(v[k] as float32, v[k + 1] as float32))
                k += 2
            }
            let r = ip.optical_flow(load8(inp), load8(a[4]), pts, i(a[6]), i(a[7])).expect("same size")
            save_text(out, r.map((p: (Vec2, bool)) => f"{fnum(p.0.x as float64)} {fnum(p.0.y as float64)} {if p.1 { 1 } else { 0 }}"))
        }
        "bilateral" => save8(out, ip.bilateral(load8(inp), i(a[4]), f(a[5]), f(a[6])))
        "erode" => save8(out, ip.erode(load8(inp), ip.rect(i(a[4]), i(a[5]))))
        "dilate" => save8(out, ip.dilate(load8(inp), ip.rect(i(a[4]), i(a[5]))))
        "watershed" => {
            let img = load8(inp)
            let m = load8(a[4])
            var marks = list_m.filled(m.data.len(), 0i32)
            for k in 0..marks.len() {
                marks[k] = m.data[k] as int32
            }
            let lab = ip.watershed(img, marks)
            var lines: [str] = []
            for y in 0..img.height {
                lines.push(lab[y * img.width:(y + 1) * img.width].map((v: int32) => f"{v}").join(" "))
            }
            save_text(out, lines)
        }
        "clahe" => save8(out, ip.clahe(load8(inp), f(a[4]), i(a[5])))
        _ => panic(f"unknown op {op}")
    }
}
'''


# ---- inputs ----------------------------------------------------------------

def _mask(w: int, h: int, cells) -> Img:
    out = bytearray(w * h)
    for (x, y) in cells:
        if 0 <= x < w and 0 <= y < h:
            out[y * w + x] = 255
    return Img(w, h, 1, "u8", bytes(out))


def nested(w: int, h: int, seed: int) -> Img:
    """Rings with holes holding discs and dots, nested squares, shapes on the
    edge, touching diagonals, single pixels: every case of the hierarchy."""
    rng = Lcg(seed)
    on = set()
    for (cx, cy, r) in [(14, 14, 11), (44, 30, 13), (70, 12, 8)]:
        for y in range(h):
            for x in range(w):
                d2 = (x - cx) ** 2 + (y - cy) ** 2
                if (r - 3) ** 2 < d2 <= r * r or d2 <= (r // 3) ** 2:
                    on.add((x, y))
    # nested squares
    for k in range(4):
        x0, y0, s = 2 + 2 * k, 36 + 2 * k, 18 - 4 * k
        for x in range(x0, x0 + s):
            on.update({(x, y0), (x, y0 + s - 1)})
        for y in range(y0, y0 + s):
            on.update({(x0, y), (x0 + s - 1, y)})
    # touching the edges, a diagonal, a thick bar with a notch
    for y in range(0, 6):
        for x in range(w - 6, w):
            on.add((x, y))
    for k in range(10):
        on.add((60 + k, 40 + k))
    for y in range(26, 32):
        for x in range(66, 80):
            if not (y == 28 and 70 <= x < 74):
                on.add((x, y))
    for _ in range(25):
        on.add((rng.next(w), rng.next(h)))
    return _mask(w, h, on)


# polygons with known corners: (corners, ...)
POLYS = [
    [(6, 5), (30, 9), (26, 30), (4, 26)],
    [(40, 6), (70, 6), (55, 30)],
    [(8, 36), (34, 36), (34, 44), (20, 44), (20, 56), (8, 56)],
    [(46, 50), (60, 36), (74, 50), (60, 58)],
]


def _inside(poly, x: float, y: float) -> bool:
    inside = False
    n = len(poly)
    for i in range(n):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
        if (y0 > y) != (y1 > y):
            xc = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
            if x < xc:
                inside = not inside
    return inside


def polygons(w: int, h: int) -> Img:
    on = set()
    for poly in POLYS:
        for y in range(h):
            for x in range(w):
                if _inside(poly, x + 0.01, y + 0.013):
                    on.add((x, y))
    return _mask(w, h, on)


def _line(on: set, x0: int, y0: int, x1: int, y1: int) -> None:
    n = max(abs(x1 - x0), abs(y1 - y0))
    for k in range(n + 1):
        on.add((round(x0 + (x1 - x0) * k / n), round(y0 + (y1 - y0) * k / n)))


SEGMENTS = [(5, 8, 90, 8), (12, 20, 12, 70), (25, 70, 85, 30), (40, 40, 70, 75), (60, 15, 95, 15)]


def lines(w: int, h: int) -> Img:
    on = set()
    for s in SEGMENTS:
        _line(on, *s)
    rng = Lcg(11)
    for _ in range(30):
        on.add((rng.next(w), rng.next(h)))
    return _mask(w, h, on)


CIRCLES = [(30.3, 28.6, 14.0), (78.5, 40.2, 20.5), (40.0, 68.7, 9.0)]


def circles(w: int, h: int) -> Img:
    """Discs at known centres, 3 by 3 supersampled, on a gradient with noise."""
    rng = Lcg(5)
    out = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            cover = 0
            for sy in range(3):
                for sx in range(3):
                    px, py = x + (sx - 1) / 3, y + (sy - 1) / 3
                    if any((px - cx) ** 2 + (py - cy) ** 2 <= r * r for (cx, cy, r) in CIRCLES):
                        cover += 1
            v = 40 + x // 4 + (cover * 150) // 9 + rng.next(7) - 3
            out[y * w + x] = max(0, min(255, v))
    return Img(w, h, 1, "u8", bytes(out))


def _blocks_value(rects, x: float, y: float) -> float:
    v = 60.0
    for (x0, y0, x1, y1, val) in rects:
        if x0 <= x < x1 and y0 <= y < y1:
            v = val
    return v


def _rects(seed: int, w: int, h: int):
    rng = Lcg(seed)
    out = []
    for _ in range(40):
        x0, y0 = rng.next(w), rng.next(h)
        out.append((x0, y0, x0 + 8 + rng.next(40), y0 + 8 + rng.next(30), 20 + rng.next(220)))
    return out


# the view of `blocks` ORB matches: turned 15 degrees about the centre and
# scaled by 0.9 (a point p of the first view is at A p + t in the second)
ORB_TURN, ORB_SCALE = 15.0, 0.9


def orb_map(w: int, h: int):
    a = math.radians(ORB_TURN)
    c, s = ORB_SCALE * math.cos(a), ORB_SCALE * math.sin(a)
    cx, cy = w / 2, h / 2
    return (c, -s, cx - c * cx + s * cy, s, c, cy - s * cx - c * cy)


def blocks(w: int, h: int, seed: int, turned: bool) -> Img:
    """Overlapping rectangles of random grays, 2 by 2 supersampled; `turned`:
    the same seen through `orb_map`."""
    rects = _rects(seed, w, h)
    m = orb_map(w, h)
    det = m[0] * m[4] - m[1] * m[3]
    out = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            acc = 0.0
            for (sx, sy) in ((0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75)):
                px, py = x + sx - 0.5, y + sy - 0.5
                if turned:
                    # the point of the first view that lands here
                    u, v = px - m[2], py - m[5]
                    px, py = (m[4] * u - m[1] * v) / det, (-m[3] * u + m[0] * v) / det
                acc += _blocks_value(rects, px, py)
            out[y * w + x] = int(acc / 4 + 0.5)
    return Img(w, h, 1, "u8", bytes(out))


FLOW_SHIFT = (2.3, -1.6)


def smooth(w: int, h: int, dx: float, dy: float) -> Img:
    """A smooth textured scene, moved by (dx, dy)."""
    out = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            u, v = x - dx, y - dy
            val = 128 + 50 * math.sin(u * 0.21) * math.cos(v * 0.17) + 30 * math.sin((u + 2 * v) * 0.09) \
                + 25 * math.exp(-((u - 40) ** 2 + (v - 30) ** 2) / 120.0)
            out[y * w + x] = max(0, min(255, int(val + 0.5)))
    return Img(w, h, 1, "u8", bytes(out))


def flow_points() -> str:
    return " ".join(f"{12 + 8 * (k % 9)} {12 + 7 * (k // 9)}" for k in range(54)) + "\n"


# a known homography and affine map, and 1000 pairs, half of them outliers
H_TRUE = (1.08, 0.12, 14.0, -0.07, 0.94, 22.0, 0.00021, -0.00013, 1.0)
A_TRUE = (0.83, -0.31, 40.0, 0.27, 1.12, -15.0, 0.0, 0.0, 1.0)


def _apply(m, x: float, y: float):
    z = m[6] * x + m[7] * y + m[8]
    return (m[0] * x + m[1] * y + m[2]) / z, (m[3] * x + m[4] * y + m[5]) / z


def point_pairs(m, seed: int, noise: float):
    """(text of the pairs, the inlier mask)."""
    rng = Lcg(seed)
    lines, mask = [], []
    for k in range(1000):
        x, y = rng.next(64000) / 100.0, rng.next(48000) / 100.0
        u, v = _apply(m, x, y)
        if k % 2 == 0:
            u += (rng.next(2001) - 1000) / 1000.0 * noise
            v += (rng.next(2001) - 1000) / 1000.0 * noise
            mask.append("1")
        else:
            while True:
                ou, ov = rng.next(80000) / 100.0 - 80.0, rng.next(60000) / 100.0 - 60.0
                if (ou - u) ** 2 + (ov - v) ** 2 > 100.0:
                    break
            u, v = ou, ov
            mask.append("0")
        lines.append(f"{x!r} {y!r} {u!r} {v!r}")
    return "\n".join(lines) + "\n", "".join(mask)


def markers(img: Img, seeds) -> Img:
    out = bytearray(img.w * img.h)
    for k, (x, y) in enumerate(seeds):
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                out[(y + dy) * img.w + x + dx] = k + 1
    return Img(img.w, img.h, 1, "u8", bytes(out))


WS_SEEDS = [(5, 5), (30, 8), (10, 25), (33, 26), (20, 16)]

INPUTS = {
    "nested": lambda: nested(80, 60, 3),
    "blobs": lambda: blobs(53, 41, 4),
    "polys": lambda: polygons(80, 60),
    "lines": lambda: lines(100, 80),
    "circles": lambda: circles(110, 85),
    "scene": lambda: scene(96, 80, 1, 9),
    "scene_odd": lambda: scene(61, 47, 1, 1),
    "rgb": lambda: scene(41, 33, 3, 2),
    "blocks": lambda: blocks(256, 192, 21, False),
    "blocks_turned": lambda: blocks(256, 192, 21, True),
    "smooth": lambda: smooth(96, 80, 0.0, 0.0),
    "smooth_moved": lambda: smooth(96, 80, *FLOW_SHIFT),
    "flow_points": flow_points,
    "h_pairs": lambda: point_pairs(H_TRUE, 31, 0.0)[0],
    "h_pairs_noisy": lambda: point_pairs(H_TRUE, 32, 0.5)[0],
    "a_pairs": lambda: point_pairs(A_TRUE, 33, 0.3)[0],
    "ws_markers": lambda: markers(scene(41, 33, 3, 2), WS_SEEDS),
}

E = ["exact"]
# one degree in float32, as OpenCV's `HoughLines` takes its step
DEGREE = repr(float(array("f", [math.pi / 180])[0]))

# (name, op, input names, parameters, tolerance)
CASES = [
    ("contours_tree", "contours", ["nested"], ["tree"], E),
    ("contours_list", "contours", ["nested"], ["list"], E),
    ("contours_external", "contours", ["nested"], ["external"], E),
    ("contours_blobs", "contours", ["blobs"], ["tree"], E),
    ("areas", "areas", ["nested"], [], ["rel", 1e-12]),
    ("lengths", "lengths", ["nested"], ["closed"], ["rel", 1e-6]),
    ("lengths_open", "lengths", ["blobs"], ["open"], ["rel", 1e-6]),
    ("rects", "rects", ["nested"], [], E),
    ("hulls", "hulls", ["nested"], [], ["cyclic"]),
    ("hulls_blobs", "hulls", ["blobs"], [], ["cyclic"]),
    ("approx", "approx", ["polys"], ["1.5"], ["corners", 1.5]),
    ("min_rects", "min_rects", ["nested"], [], ["boxes", 1e-3]),
    ("moments", "moments", ["nested"], [], ["rel", 1e-9, 1e-6]),
    ("hu", "hu", ["nested"], [], ["rel", 1e-6]),
    ("image_moments", "image_moments", ["scene"], ["gray"], ["rel", 1e-9]),
    ("image_moments_binary", "image_moments", ["nested"], ["binary"], ["rel", 1e-9]),
    ("pip", "pip", ["polys"], [], ["rel", 1e-6]),
    ("hough_lines", "hough_lines", ["lines"], ["1", DEGREE, "20"], ["rel", 1e-6]),
    ("hough_lines_coarse", "hough_lines", ["lines"], ["2", "0.05", "15"], ["rel", 1e-6]),
    ("hough_segments", "hough_segments", ["lines"], ["20", "20", "3"], ["segments", 3.0]),
    ("hough_circles", "hough_circles", ["circles"], ["7", "25", "10", "15"], ["circles", 1.0, 1.0]),
    ("fast", "fast", ["scene"], ["20", "nms"], ["sorted"]),
    ("fast_all", "fast", ["scene"], ["30", "all"], ["sorted"]),
    ("fast_blocks", "fast", ["blocks"], ["20", "nms"], ["sorted"]),
    ("orb", "orb", ["blocks", "blocks_turned"], ["300"], ["orb", 3.0, 0.6]),
    ("homography", "homography", ["h_pairs"], ["3"], ["estimate", 0.01]),
    ("homography_noisy", "homography", ["h_pairs_noisy"], ["3"], ["estimate", 0.25]),
    ("affine", "affine", ["a_pairs"], ["3"], ["estimate", 0.15]),
    ("flow", "flow", ["smooth", "smooth_moved", "flow_points"], ["21", "3"], ["flow", 0.05]),
    ("flow_small_window", "flow", ["smooth", "smooth_moved", "flow_points"], ["9", "2"], ["flow", 0.1]),
    ("bilateral", "bilateral", ["scene"], ["5", "30", "4"], ["abs", 1]),
    ("bilateral_rgb", "bilateral", ["rgb"], ["9", "60", "3"], ["abs", 1]),
    ("bilateral_auto", "bilateral", ["scene_odd"], ["0", "20", "2"], ["abs", 1]),
    ("erode_rect", "erode", ["scene"], ["15", "7"], E),
    ("dilate_rect", "dilate", ["scene_odd"], ["4", "10"], E),
    ("watershed", "watershed", ["rgb", "ws_markers"], [], E),
    ("clahe", "clahe", ["scene"], ["2", "8"], E),
    ("clahe_odd", "clahe", ["scene_odd"], ["4", "3"], E),
    ("clahe_noclip", "clahe", ["scene"], ["0", "4"], E),
]


# ---- comparing -------------------------------------------------------------

def _rows(b: bytes) -> list[list[str]]:
    return [l.split() for l in b.decode().splitlines()]


def _close(a: float, b: float, rel: float) -> bool:
    if math.isinf(a) or math.isinf(b) or math.isnan(a) or math.isnan(b):
        return a == b or (math.isnan(a) and math.isnan(b))
    return abs(a - b) <= rel * max(1.0, abs(b))


def _pairs_of(row: list[str]) -> list[tuple[float, float]]:
    v = [float(t) for t in row]
    return [(v[k], v[k + 1]) for k in range(0, len(v) - 1, 2)]


def _cyclic_equal(a: list, b: list) -> bool:
    if len(a) != len(b):
        return False
    if not a:
        return True
    return any(a[k:] + a[:k] == b for k in range(len(a)))


def compare(got: bytes, want: bytes, tol: list) -> str | None:
    """None if `got` matches `want` within `tol`, else what differs."""
    kind = tol[0]
    if want[:4] == b"MYIM":
        gi, wi = Img.decode(got), Img.decode(want)
        if (gi.w, gi.h, gi.c) != (wi.w, wi.h, wi.c):
            return f"{gi.w}x{gi.h}x{gi.c}, expected {wi.w}x{wi.h}x{wi.c}"
        limit = 0 if kind == "exact" else tol[1]
        for k, (a, b) in enumerate(zip(gi.data, wi.data)):
            if abs(a - b) > limit:
                return f"sample {k} (pixel {(k // gi.c) % gi.w}, {(k // gi.c) // gi.w}): {a}, expected {b}"
        return None
    g, w = _rows(got), _rows(want)
    if kind == "exact":
        if g != w:
            for k, (a, b) in enumerate(zip(g, w)):
                if a != b:
                    return f"line {k}: {' '.join(a[:12])}..., expected {' '.join(b[:12])}..."
            return f"{len(g)} lines, expected {len(w)}"
        return None
    if kind == "rel":
        if len(g) != len(w):
            return f"{len(g)} lines, expected {len(w)}"
        for k, (a, b) in enumerate(zip(g, w)):
            if len(a) != len(b):
                return f"line {k}: {len(a)} values, expected {len(b)}"
            for j, (x, y) in enumerate(zip(a, b)):
                if not _close(float(x), float(y), tol[1]) and not (len(tol) > 2 and abs(float(x) - float(y)) <= tol[2]):
                    return f"line {k}, value {j}: {x}, expected {y}"
        return None
    if kind == "sorted":
        return None if sorted(map(tuple, g)) == sorted(map(tuple, w)) else \
            f"{len(g)} keypoints, expected {len(w)}; first differences {sorted(set(map(tuple, g)) ^ set(map(tuple, w)))[:4]}"
    if kind == "cyclic":
        if len(g) != len(w):
            return f"{len(g)} hulls, expected {len(w)}"
        for k, (a, b) in enumerate(zip(g, w)):
            if not _cyclic_equal(_pairs_of(a), _pairs_of(b)):
                return f"hull {k}: {' '.join(a)}, expected {' '.join(b)}"
        return None
    if kind == "corners":
        # each polygon's corners within the distance of the true ones
        if len(g) != len(w):
            return f"{len(g)} polygons, expected {len(w)}"
        for k, row in enumerate(g):
            got_c = _pairs_of(row)
            match = None
            for want_row in w:
                true_c = _pairs_of(want_row)
                if len(true_c) == len(got_c) and all(
                        min(math.dist(p, q) for q in true_c) <= tol[1] for p in got_c):
                    match = want_row
            if match is None:
                return f"polygon {k}: {' '.join(row)} matches no true polygon"
        return None
    if kind == "boxes":
        # the area OpenCV's; the box OpenCV's, or (of several of the same
        # area) a rectangle that holds every point of the contour
        if len(g) != len(w):
            return f"{len(g)} boxes, expected {len(w)}"
        for k, (a, b) in enumerate(zip(g, w)):
            cut = b.index("|")
            av, bv = [float(t) for t in a], [float(t) for t in b[:cut]]
            if abs(av[2] - bv[2]) > tol[1] * max(1.0, abs(bv[2])):
                return f"box {k}: area {av[2]}, expected {bv[2]}"
            ca, cb = _pairs_of(a[3:]), _pairs_of(b[3:cut])
            if all(min(math.dist(p, q) for q in cb) <= 0.01 for p in ca):
                continue
            (x0, y0), (x1, y1), (x2, y2), (x3, y3) = ca
            ux, uy, vx, vy = x1 - x0, y1 - y0, x3 - x0, y3 - y0
            lu, lv = math.hypot(ux, uy), math.hypot(vx, vy)
            if abs(ux * vx + uy * vy) > 1e-3 * max(1.0, lu * lv) or abs(lu * lv - bv[2]) > tol[1] * max(1.0, bv[2]):
                return f"box {k}: {ca} is no rectangle of area {bv[2]}"
            for (px, py) in _pairs_of(b[cut + 1:]):
                s = ((px - x0) * ux + (py - y0) * uy) / max(lu, 1e-9)
                t = ((px - x0) * vx + (py - y0) * vy) / max(lv, 1e-9)
                if s < -0.01 or t < -0.01 or s > lu + 0.01 or t > lv + 0.01:
                    return f"box {k}: {ca} leaves out the point {(px, py)}"
        return None
    if kind == "segments":
        truth = [tuple(float(t) for t in r) for r in w]
        if not g:
            return "no segments"
        for row in g:
            x0, y0, x1, y1 = (float(t) for t in row)
            # on a true segment: both ends within the distance of its line
            ok = False
            for (a, b, c, d) in truth:
                ln = math.hypot(c - a, d - b)
                def dist(px, py):
                    t = max(0.0, min(1.0, ((px - a) * (c - a) + (py - b) * (d - b)) / (ln * ln)))
                    return math.hypot(px - a - t * (c - a), py - b - t * (d - b))
                if dist(x0, y0) <= tol[1] and dist(x1, y1) <= tol[1]:
                    ok = True
            if not ok:
                return f"segment {row} lies on no true segment"
        # each true segment mostly covered
        for (a, b, c, d) in truth:
            ln = math.hypot(c - a, d - b)
            covered = 0.0
            for row in g:
                x0, y0, x1, y1 = (float(t) for t in row)
                t0 = ((x0 - a) * (c - a) + (y0 - b) * (d - b)) / ln
                t1 = ((x1 - a) * (c - a) + (y1 - b) * (d - b)) / ln
                if abs((c - a) * (y0 - b) - (d - b) * (x0 - a)) / ln <= tol[1]:
                    covered += abs(t1 - t0)
            if covered < 0.8 * ln:
                return f"true segment {(a, b, c, d)} covered {covered:.1f} of {ln:.1f}"
        return None
    if kind == "circles":
        truth = [tuple(float(t) for t in r) for r in w]
        found = [tuple(float(t) for t in r) for r in g]
        if len(found) != len(truth):
            return f"{len(found)} circles {found}, expected {len(truth)}"
        for (cx, cy, r) in truth:
            if not any(math.hypot(x - cx, y - cy) <= tol[1] and abs(rr - r) <= tol[2] for (x, y, rr) in found):
                return f"no circle near {(cx, cy, r)} in {found}"
        return None
    if kind == "orb":
        # matches consistent with the known map; at least a fraction of them
        m = [float(t) for t in w[0]] + [0.0, 0.0, 1.0]
        na, nb = (int(t) for t in g[0][:2])
        if na == 0 or nb == 0:
            return "no features"
        rows = g[1:]
        good = 0
        for row in rows:
            x, y, u, v = (float(t) for t in row[:4])
            pu, pv = _apply(m, x, y)
            if math.hypot(pu - u, pv - v) <= tol[1]:
                good += 1
        if len(rows) < 30 or good < tol[2] * len(rows):
            return f"{good} of {len(rows)} matches agree with the map ({na} and {nb} features)"
        return None
    if kind == "estimate":
        if g == [["none"]]:
            return "no estimate"
        m = [float(t[0]) for t in g[:9]]
        true_m = [float(t) for t in w[0]]
        mask = g[9][0]
        if mask != w[1][0]:
            diff = sum(1 for a, b in zip(mask, w[1][0]) if a != b)
            return f"the inlier mask differs at {diff} points"
        worst = 0.0
        for y in range(0, 480, 40):
            for x in range(0, 640, 40):
                a, b = _apply(m, x, y)
                c, d = _apply(true_m, x, y)
                worst = max(worst, math.hypot(a - c, b - d))
        return None if worst <= tol[1] else f"the map is {worst:.4f} px off the true one at worst"
    if kind == "flow":
        dx, dy = (float(t) for t in w[0])
        pts = _pairs_of(w[1])
        if len(g) != len(pts):
            return f"{len(g)} points, expected {len(pts)}"
        for (x, y), row in zip(pts, g):
            u, v, ok = float(row[0]), float(row[1]), row[2]
            if ok != "1":
                return f"point {(x, y)} lost"
            if math.hypot(u - x - dx, v - y - dy) > tol[1]:
                return f"point {(x, y)} went to {(u, v)}, expected {(x + dx, y + dy)}"
        return None
    raise ValueError(kind)


class ImgprocBTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.mkdtemp()
        cls.exe = None
        if CAN_BUILD_NATIVE:
            path = os.path.join(cls.tmp, "driver.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(DRIVER)
            cls.exe = os.path.join(cls.tmp, "driver")
            native_build(check_file(path), cls.exe)
        cls.inputs = {}
        for name, make in INPUTS.items():
            p = os.path.join(cls.tmp, name + ".in")
            data = make()
            with open(p, "wb") as fh:
                fh.write(data.encode() if isinstance(data, (Img, str)) else data)
            cls.inputs[name] = p

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_case(self, name: str, op: str, ins: list[str], params: list[str]) -> bytes:
        out = os.path.join(self.tmp, name + ".out")
        files = [self.inputs[n] for n in ins]
        args = [op, out, *files, *params]
        argv, exe = run_argv(self.exe, args=args)
        proc = subprocess.run(argv, executable=exe, capture_output=True, timeout=300)
        self.assertEqual(proc.returncode, 0, f"{name}: {proc.stderr.decode(errors='replace')}")
        with open(out, "rb") as fh:
            return fh.read()

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_against_references(self) -> None:
        for (name, op, ins, params, tol) in CASES:
            with self.subTest(case=name):
                got = self.run_case(name, op, ins, params)
                with gzip.open(os.path.join(DATA, name + ".gz"), "rb") as fh:
                    want = fh.read()
                problem = compare(got, want, tol)
                self.assertIsNone(problem, f"{name} ({' '.join(str(t) for t in tol)}): {problem}")

    def test_every_case_vendored(self) -> None:
        names = {c[0] for c in CASES}
        self.assertEqual(len(names), len(CASES))
        on_disk = {n[:-3] for n in os.listdir(DATA) if n.endswith(".gz")}
        self.assertEqual(on_disk, names)


# ---- the references (only for --vendor: they need OpenCV and numpy) --------

cv2 = None
np = None


def _gray(img: Img):
    return np.frombuffer(img.data, np.uint8).reshape(img.h, img.w, img.c)


def _num(x: float) -> str:
    return repr(float(x))


def _contours(img: Img, mode: str = "tree"):
    m = {"tree": cv2.RETR_TREE, "list": cv2.RETR_LIST, "external": cv2.RETR_EXTERNAL}[mode]
    cs, hier = cv2.findContours(_gray(img)[:, :, 0].copy(), m, cv2.CHAIN_APPROX_NONE)
    return list(cs), (hier[0] if hier is not None else [])


def _pts(c) -> str:
    return " ".join(f"{int(x)} {int(y)}" for (x, y) in c.reshape(-1, 2))


def _hole(hier, k: int) -> int:
    depth, p = 0, hier[k][3]
    while p >= 0:
        depth, p = depth + 1, hier[p][3]
    return depth % 2


def _moments_text(m) -> str:
    keys = ["m00", "m10", "m01", "m20", "m11", "m02", "m30", "m21", "m12", "m03",
            "mu20", "mu11", "mu02", "mu30", "mu21", "mu12", "mu03",
            "nu20", "nu11", "nu02", "nu30", "nu21", "nu12", "nu03"]
    return " ".join(_num(m[k]) for k in keys)


def reference(op: str, ins: list, params: list):
    a = ins[0] if ins else None
    if op == "contours":
        cs, hier = _contours(a, params[0])
        out = []
        for k, c in enumerate(cs):
            if params[0] == "tree":
                hole, parent = _hole(hier, k), int(hier[k][3])
            else:
                # without the nesting, whether a border is a hole comes from
                # its orientation: OpenCV's holes have a positive area
                hole, parent = (1 if cv2.contourArea(c, True) > 0 else 0), -1
            out.append(f"{hole} {parent} {_pts(c)}")
        return out
    if op == "areas":
        return [_num(cv2.contourArea(c, True)) for c in _contours(a)[0]]
    if op == "lengths":
        return [_num(cv2.arcLength(c, params[0] == "closed")) for c in _contours(a)[0]]
    if op == "rects":
        return [" ".join(str(v) for v in cv2.boundingRect(c)) for c in _contours(a)[0]]
    if op == "hulls":
        return [_pts(cv2.convexHull(c)) for c in _contours(a)[0]]
    if op == "approx":
        return [" ".join(f"{x} {y}" for (x, y) in poly) for poly in POLYS]
    if op == "min_rects":
        out = []
        for c in _contours(a)[0]:
            r = cv2.minAreaRect(c)
            corners = cv2.boxPoints(r)
            out.append(" ".join([_num(r[0][0]), _num(r[0][1]), _num(r[1][0] * r[1][1])] +
                                [_num(v) for v in corners.ravel()]) + " | " + _pts(c))
        return out
    if op == "moments":
        return [_moments_text(cv2.moments(c)) for c in _contours(a)[0]]
    if op == "hu":
        return [" ".join(_num(v) for v in cv2.HuMoments(cv2.moments(c)).ravel()) for c in _contours(a)[0]]
    if op == "image_moments":
        return [_moments_text(cv2.moments(_gray(a)[:, :, 0], params[0] == "binary"))]
    if op == "pip":
        out = []
        for c in _contours(a, "external")[0]:
            parts = []
            for y in range(12):
                for x in range(16):
                    p = (x * 4 + 0.5, float(y * 4))
                    parts.append(f"{int(cv2.pointPolygonTest(c, p, False))} {_num(cv2.pointPolygonTest(c, p, True))}")
            out.append(" ".join(parts))
        return out
    if op == "hough_lines":
        ls = cv2.HoughLinesWithAccumulator(_gray(a)[:, :, 0], float(params[0]), float(params[1]), int(params[2]))
        if ls is None:
            return []
        return [f"{_num(r)} {_num(t)} {int(v)}" for (r, t, v) in ls.reshape(-1, 3)]
    if op == "hough_segments":
        return [" ".join(str(v) for v in s) for s in SEGMENTS]
    if op == "hough_circles":
        return [" ".join(_num(v) for v in c) for c in CIRCLES]
    if op == "fast":
        det = cv2.FastFeatureDetector_create(int(params[0]), params[1] == "nms", cv2.FAST_FEATURE_DETECTOR_TYPE_9_16)
        ks = det.detect(_gray(a)[:, :, 0])
        if params[1] != "nms":
            return [f"{int(k.pt[0])} {int(k.pt[1])}" for k in ks]
        return [f"{int(k.pt[0])} {int(k.pt[1])} {int(k.response)}" for k in ks]
    if op == "orb":
        return [" ".join(_num(v) for v in orb_map(a.w, a.h))]
    if op in ("homography", "affine"):
        m, seed, noise = {"h_pairs": (H_TRUE, 31, 0.0), "h_pairs_noisy": (H_TRUE, 32, 0.5),
                           "a_pairs": (A_TRUE, 33, 0.3)}[params[-1]]
        return [" ".join(_num(v) for v in m), point_pairs(m, seed, noise)[1]]
    if op == "flow":
        return [f"{_num(FLOW_SHIFT[0])} {_num(FLOW_SHIFT[1])}", flow_points().strip()]
    if op == "bilateral":
        g = _gray(a)
        src = g[:, :, 0] if a.c == 1 else g
        r = cv2.bilateralFilter(src, int(params[0]), float(params[1]), float(params[2]))
        return Img(a.w, a.h, a.c, "u8", r.astype(np.uint8).tobytes())
    if op in ("erode", "dilate"):
        k = np.ones((int(params[1]), int(params[0])), np.uint8)
        f = cv2.erode if op == "erode" else cv2.dilate
        r = f(_gray(a)[:, :, 0], k)
        return Img(a.w, a.h, 1, "u8", r.tobytes())
    if op == "watershed":
        img = _gray(a).copy()
        marks = np.frombuffer(ins[1].data, np.uint8).reshape(a.h, a.w).astype(np.int32).copy()
        cv2.watershed(img, marks)
        return [" ".join(str(int(v)) for v in row) for row in marks]
    if op == "clahe":
        c = cv2.createCLAHE(clipLimit=float(params[0]), tileGridSize=(int(params[1]), int(params[1])))
        r = c.apply(_gray(a)[:, :, 0].copy())
        return Img(a.w, a.h, 1, "u8", r.tobytes())
    raise ValueError(op)


def vendor() -> None:
    global cv2, np
    import cv2 as cv
    import numpy
    cv2, np = cv, numpy
    os.makedirs(DATA, exist_ok=True)
    for old in os.listdir(DATA):
        if old.endswith(".gz"):
            os.remove(os.path.join(DATA, old))
    made = {name: make() for name, make in INPUTS.items()}
    for (name, op, ins, params, _tol) in CASES:
        args = list(params)
        if op in ("homography", "affine"):
            args.append(ins[0])
        out = reference(op, [made[n] for n in ins], args)
        data = out.encode() if isinstance(out, Img) else ("\n".join(out) + "\n").encode()
        with open(os.path.join(DATA, name + ".gz"), "wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as fh:
                fh.write(data)


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--vendor":
        vendor()
    else:
        unittest.main()
