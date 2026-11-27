"""Burn tests: `std.imgproc` (MYLA-967) against references independent of it.

Each case runs one function of the module through a driver (`DRIVER`, built
natively once) on images that pure Python makes from a seed (a scene of a
gradient, a rectangle, a disc and noise, in gray, RGB and RGBA; a mask of
discs and bars), and compares what it writes with an expected output
vendored in `tests/burn/data/imgproc/` (`<case>.gz`). The expected outputs
were made once by `python3 -m tests.burn.test_imgproc --vendor`, which needs
Pillow and numpy; the test itself needs neither.

The references: Pillow's own function where it has one with the same
meaning (gray, RGB, invert, histogram, difference, resize with each filter
for gray and RGB, BOX for `Area` at whole factors, MedianFilter,
MinFilter/MaxFilter for a square element), Python's `colorsys` for HSV,
`numpy.pad` for `pad`, `numpy.linalg.solve` for the transforms, and
otherwise a short textbook implementation in numpy or plain Python written
from the definition (not from std.imgproc's code): convolution, the
Gaussian (Pillow's GaussianBlur is an approximation by box blurs, so it
isn't used), the derivatives, morphology, Canny (OpenCV's rules), Harris,
Shi-Tomasi, template matching, components, flood fill, the brute-force
Euclidean distance, MSE, PSNR and SSIM. Each case states its tolerance:
`exact`, `abs d` (every sample within d), `frac d f` (all but a fraction f
of the samples within d), `rel e` (floats within e relative, or e absolute
near 0), or the same per number of a text output.
"""
from __future__ import annotations

import colorsys
import gzip
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from array import array

from ._native import CAN_BUILD_NATIVE, SKIP_REASON, check_file, native_build, run_argv

DATA = os.path.join(os.path.dirname(__file__), "data", "imgproc")

DRIVER = r'''import std.image as image
from std.image import Image, Image8, ImageF, Layout, Color
import std.imgproc as ip
from std.imgproc import Border, Filter
import std.vector32 as v32
from std.vector32 import Vec2
import std.matrix32 as m32
import std.fs as fs
import std.num as num
import std.process as process
import std.float as fl
import std.time as time
import std.list as list_m

// The test files: "MYIM", width, height (uint32 LE), channels, kind (0
// uint8, 1 float32), two zeros, then the samples.
fun u32_at(b: [uint8], i: int) -> int {
    return (b[i] as int) | ((b[i + 1] as int) << 8) | ((b[i + 2] as int) << 16) | ((b[i + 3] as int) << 24)
}

fun header(w: int, h: int, c: int, kind: int) -> [uint8] {
    var out = [77u8, 89u8, 73u8, 77u8]
    for v in [w, h] {
        out.push((v & 255) as uint8)
        out.push(((v >> 8) & 255) as uint8)
        out.push(((v >> 16) & 255) as uint8)
        out.push(((v >> 24) & 255) as uint8)
    }
    out.push(c as uint8)
    out.push(kind as uint8)
    out.push(0u8)
    out.push(0u8)
    return out
}

fun load8(path: str) -> Image8 {
    let b = fs.read_bytes(path).expect("an input")
    let w = u32_at(b, 4)
    let h = u32_at(b, 8)
    let c = b[12] as int
    let layout = image.layout_of(c).expect("a layout")
    return image.from_data(w, h, layout, b[16:16 + w * h * c]).expect("the samples")
}

fun loadf(path: str) -> ImageF {
    let b = fs.read_bytes(path).expect("an input")
    let w = u32_at(b, 4)
    let h = u32_at(b, 8)
    let c = b[12] as int
    let layout = image.layout_of(c).expect("a layout")
    let n = w * h * c
    var data = list_m.filled(n, 0.0f32)
    for i in 0..n {
        data[i] = fl.from_bits32(u32_at(b, 16 + 4 * i) as uint32)
    }
    return image.from_data(w, h, layout, data).expect("the samples")
}

fun save8(path: str, img: Image8) {
    var out = header(img.width, img.height, img.layout.channels(), 0)
    out.extend(img.data)
    fs.write_bytes(path, out).expect("written")
}

fun savef(path: str, img: ImageF) {
    var out = header(img.width, img.height, img.layout.channels(), 1)
    for v in img.data {
        let bits = v.to_bits()
        out.push((bits & 255u32) as uint8)
        out.push(((bits >> 8u32) & 255u32) as uint8)
        out.push(((bits >> 16u32) & 255u32) as uint8)
        out.push(((bits >> 24u32) & 255u32) as uint8)
    }
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

fun fnum(x: float64) -> str {
    return num.format_float(x)
}

fun f(s: str) -> float32 {
    return num.parse_float(s).expect(f"a number: {s}") as float32
}

fun i(s: str) -> int {
    return num.parse_int32(s).expect(f"an integer: {s}")
}

fun border(s: str) -> Border {
    if s.starts_with("constant:") {
        return Border.Constant(f(s[9:]))
    }
    return match s {
        "replicate" => Border.Replicate
        "reflect" => Border.Reflect
        "reflect101" => Border.Reflect101
        "wrap" => Border.Wrap
        _ => panic(f"border {s}")
    }
}

fun filter(s: str) -> Filter {
    return match s {
        "nearest" => Filter.Nearest
        "bilinear" => Filter.Bilinear
        "bicubic" => Filter.Bicubic
        "area" => Filter.Area
        "lanczos3" => Filter.Lanczos3
        _ => panic(f"filter {s}")
    }
}

fun element(shape: str, w: int, h: int) -> ip.Element {
    return match shape {
        "rect" => ip.rect(w, h)
        "cross" => ip.cross(w, h)
        "ellipse" => ip.ellipse(w, h)
        _ => panic(f"element {shape}")
    }
}

fun color(a: [str], at: int) -> Color {
    return image.rgba(i(a[at]) as uint8, i(a[at + 1]) as uint8, i(a[at + 2]) as uint8, i(a[at + 3]) as uint8)
}

fun mat(a: [str], at: int, n: int) -> m32.Mat3 {
    var r = list_m.filled(9, 0.0f32)
    r[8] = 1.0f32
    for k in 0..n {
        r[k] = f(a[at + k])
    }
    return m32.mat3_from_rows(v32.vec3(r[0], r[1], r[2]), v32.vec3(r[3], r[4], r[5]), v32.vec3(r[6], r[7], r[8]))
}

fun points(a: [str], at: int, n: int) -> [Vec2] {
    var out: [Vec2] = []
    for k in 0..n {
        out.push(v32.vec2(f(a[at + 2 * k]), f(a[at + 2 * k + 1])))
    }
    return out
}

fun mat_text(m: Option<m32.Mat3>) -> [str] {
    let Some(mm) = m else {
        return ["none"]
    }
    var out: [str] = []
    for r in 0..3 {
        for c in 0..3 {
            out.push(fnum(mm[(r, c)] as float64))
        }
    }
    return out
}

fun threshold_mode(s: str) -> ip.Threshold {
    return match s {
        "binary" => ip.Threshold.Binary
        "binary_inv" => ip.Threshold.BinaryInv
        "trunc" => ip.Threshold.Trunc
        "to_zero" => ip.Threshold.ToZero
        "to_zero_inv" => ip.Threshold.ToZeroInv
        _ => panic(f"threshold {s}")
    }
}

fun morph_op(s: str) -> ip.Morph {
    return match s {
        "open" => ip.Morph.Open
        "close" => ip.Morph.Close
        "gradient" => ip.Morph.Gradient
        "tophat" => ip.Morph.TopHat
        "blackhat" => ip.Morph.BlackHat
        _ => panic(f"morph {s}")
    }
}

fun match_method(s: str) -> ip.Match {
    return match s {
        "ssd" => ip.Match.Ssd
        "ncc" => ip.Match.Ncc
        "zncc" => ip.Match.Zncc
        _ => panic(f"match {s}")
    }
}

fun weights(a: [str], at: int, n: int) -> [float32] {
    var out: [float32] = []
    for k in 0..n {
        out.push(f(a[at + k]))
    }
    return out
}

// A 1024 by 1024 scene for the timings: gradients, a disc and noise.
fun scene(c: int) -> Image8 {
    let layout = image.layout_of(c).expect("a layout")
    var img: Image8 = image.new(1024, 1024, layout, 0u8)
    var s: uint32 = 12345u32
    for y in 0..1024 {
        for x in 0..1024 {
            s = s.wrapping_mul(1664525u32).wrapping_add(1013904223u32)
            let noise = ((s >> 24u32) as int) % 32
            let dx = x - 512
            let dy = y - 400
            let disc = if dx * dx + dy * dy < 200 * 200 { 120 } else { 0 }
            for k in 0..c {
                img.data[(y * 1024 + x) * c + k] = ((x / 8 + y / 16 + disc + noise + 40 * k) % 256) as uint8
            }
        }
    }
    return img
}

// The best of `reps` runs of `op` over the 1024 by 1024 scene, in ms.
fun bench(op: str, reps: int) {
    let img = scene(1)
    let rgb = scene(3)
    var best: int64 = 0x7FFFFFFFFFFFFFFF
    var check = 0
    for _ in 0..reps {
        let t0 = time.now_ns()
        let r = match op {
            "gray" => ip.gray(rgb).data[1000] as int
            "resize_nearest" => ip.resize(img, 640, 480, Filter.Nearest).data[1000] as int
            "resize_bilinear" => ip.resize(img, 640, 480, Filter.Bilinear).data[1000] as int
            "resize_bicubic" => ip.resize(img, 640, 480, Filter.Bicubic).data[1000] as int
            "resize_area" => ip.resize(img, 640, 480, Filter.Area).data[1000] as int
            "resize_lanczos3" => ip.resize(img, 640, 480, Filter.Lanczos3).data[1000] as int
            "resize_rgb_bilinear" => ip.resize(rgb, 640, 480, Filter.Bilinear).data[1000] as int
            "gaussian" => ip.gaussian_blur(img, 2.0f32).data[1000] as int
            "box" => ip.box_blur(img, 2).data[1000] as int
            "median" => ip.median(img, 2).data[1000] as int
            "sobel" => ip.sobel(img, 1, 0).data[1000] as int
            "canny" => ip.canny(img, 50.0f32, 150.0f32).data[1000] as int
            "components" => ip.components(ip.threshold(img, 128u8)).count
            "erode" => ip.erode(img, ip.rect(5, 5)).data[1000] as int
            "dilate_ellipse" => ip.dilate(img, ip.ellipse(5, 5)).data[1000] as int
            "distance" => ip.distance_transform(ip.threshold(img, 128u8)).data[1000] as int
            "warp_affine" => ip.warp_affine(img, m32.rotation2d(0.3f32), 1024, 1024).data[1000] as int
            "equalize" => ip.equalize(img).data[1000] as int
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
        "gray" => save8(out, ip.gray(load8(inp)))
        "to_rgb" => save8(out, ip.to_rgb(load8(inp)))
        "to_hsv" => savef(out, ip.to_hsv(load8(inp)))
        "from_hsv" => save8(out, ip.from_hsv(loadf(inp)))
        "to_linear" => savef(out, ip.to_linear(load8(inp)))
        "to_srgb" => save8(out, ip.to_srgb(loadf(inp)))
        "invert" => save8(out, ip.invert(load8(inp)))
        "lut" => {
            var t = list_m.filled(256, 0u8)
            for v in 0..256 {
                t[v] = ((v * 7 + 3) % 256) as uint8
            }
            save8(out, ip.lut(load8(inp), t))
        }
        "adjust" => save8(out, ip.adjust(load8(inp), f(a[4]), f(a[5])))
        "gamma" => save8(out, ip.gamma(load8(inp), f(a[4])))
        "threshold" => save8(out, ip.threshold(load8(inp), i(a[4]) as uint8, threshold_mode(a[5]), i(a[6]) as uint8))
        "otsu" => save_text(out, [f"{ip.otsu(load8(inp))}"])
        "adaptive" => {
            let m = if a[6] == "mean" { ip.Adaptive.Mean } else { ip.Adaptive.Gaussian }
            save8(out, ip.adaptive_threshold(load8(inp), i(a[4]), f(a[5]), m))
        }
        "in_range" => save8(out, ip.in_range(load8(inp), color(a, 4), color(a, 8)))
        "histogram" => {
            var lines: [str] = []
            for v in ip.histogram(load8(inp), i(a[4])) {
                lines.push(f"{v}")
            }
            save_text(out, lines)
        }
        "equalize" => save8(out, ip.equalize(load8(inp)))
        "normalize" => save8(out, ip.normalize(load8(inp), i(a[4]) as uint8, i(a[5]) as uint8))
        "normalize_f" => save8(out, ip.normalize_f(loadf(inp)))
        "abs_diff" => save8(out, ip.abs_diff(load8(inp), load8(a[4])).expect("same shape"))
        "blend" => save8(out, ip.blend(load8(inp), load8(a[4]), f(a[5])).expect("same shape"))
        "apply_mask" => save8(out, ip.apply_mask(load8(inp), load8(a[4])).expect("same size"))
        "resize" => save8(out, ip.resize(load8(inp), i(a[4]), i(a[5]), filter(a[6])))
        "resize_f" => savef(out, ip.resize(loadf(inp), i(a[4]), i(a[5]), filter(a[6])))
        "rotate" => save8(out, ip.rotate(load8(inp), f(a[4]), color(a, 6), a[5] == "expand"))
        "warp_affine" => save8(out, ip.warp_affine(load8(inp), mat(a, 4, 6), i(a[10]), i(a[11]), filter(a[12]), border(a[13])))
        "warp_perspective" => save8(out, ip.warp_perspective(load8(inp), mat(a, 4, 8), i(a[12]), i(a[13]), filter(a[14]), border(a[15])))
        "affine_from" => save_text(out, mat_text(ip.affine_from(points(a, 4, 3), points(a, 10, 3))))
        "perspective_from" => save_text(out, mat_text(ip.perspective_from(points(a, 4, 4), points(a, 12, 4))))
        "pad" => save8(out, ip.pad(load8(inp), i(a[4]), i(a[5]), i(a[6]), i(a[7]), border(a[8])))
        "pyr_down" => save8(out, ip.pyr_down(load8(inp)))
        "pyr_up" => save8(out, ip.pyr_up(load8(inp)))
        "convolve" => {
            let kw = i(a[4])
            let kh = i(a[5])
            save8(out, ip.convolve(load8(inp), ip.kernel(kw, kh, weights(a, 6, kw * kh)), border(a[6 + kw * kh])))
        }
        "convolve_sep" => {
            let nx = i(a[4])
            let ny = i(a[5 + nx])
            save8(out, ip.convolve_sep(load8(inp), weights(a, 5, nx), weights(a, 6 + nx, ny), border(a[6 + nx + ny])))
        }
        "box_blur" => save8(out, ip.box_blur(load8(inp), i(a[4]), border(a[5])))
        "gaussian" => save8(out, ip.gaussian_blur(load8(inp), f(a[4]), border(a[5])))
        "gaussian_f" => savef(out, ip.gaussian_blur(loadf(inp), f(a[4]), border(a[5])))
        "median" => save8(out, ip.median(load8(inp), i(a[4])))
        "sharpen" => save8(out, ip.sharpen(load8(inp), f(a[4])))
        "unsharp" => save8(out, ip.unsharp_mask(load8(inp), f(a[4]), f(a[5]), f(a[6])))
        "sobel" => savef(out, ip.sobel(load8(inp), i(a[4]), i(a[5]), i(a[6]), border(a[7])))
        "scharr" => savef(out, ip.scharr(load8(inp), i(a[4]), i(a[5])))
        "laplacian" => savef(out, ip.laplacian(load8(inp), i(a[4])))
        "magnitude" => {
            let (m, _) = ip.gradients(load8(inp))
            savef(out, m)
        }
        "angle" => {
            let (_, g) = ip.gradients(load8(inp))
            savef(out, g)
        }
        "erode" => save8(out, ip.erode(load8(inp), element(a[4], i(a[5]), i(a[6]))))
        "dilate" => save8(out, ip.dilate(load8(inp), element(a[4], i(a[5]), i(a[6]))))
        "morph" => save8(out, ip.morph(load8(inp), morph_op(a[4]), element(a[5], i(a[6]), i(a[7]))))
        "canny" => save8(out, ip.canny(load8(inp), f(a[4]), f(a[5])))
        "harris" => savef(out, ip.harris(load8(inp), i(a[4]), f(a[5])))
        "good_features" => {
            var lines: [str] = []
            for p in ip.good_features(load8(inp), i(a[4]), f(a[5]), f(a[6])) {
                lines.push(f"{p.x as int} {p.y as int}")
            }
            save_text(out, lines)
        }
        "match_template" => savef(out, ip.match_template(load8(inp), load8(a[4]), match_method(a[5])).expect("fits"))
        "min_max" => {
            let e = ip.min_max(loadf(inp))
            save_text(out, [fnum(e.min as float64), fnum(e.max as float64), f"{e.min_x}", f"{e.min_y}", f"{e.max_x}", f"{e.max_y}"])
        }
        "integral" => {
            let t = ip.integral(load8(inp), i(a[4]))
            var lines: [str] = []
            for v in t.sums {
                lines.push(fnum(v))
            }
            lines.push(fnum(t.sum(image.rect(3, 2, 7, 5))))
            save_text(out, lines)
        }
        "labels" => {
            let cs = ip.components(load8(inp), i(a[4]))
            var labels = list_m.filled(cs.labels.len(), 0.0f32)
            for k in 0..labels.len() {
                labels[k] = cs.labels[k] as float32
            }
            savef(out, Image { width: cs.width, height: cs.height, layout: Layout.Gray, data: labels })
        }
        "regions" => {
            let cs = ip.components(load8(inp), i(a[4]))
            var lines = [f"{cs.count}"]
            for r in cs.stats {
                lines.push(f"{r.area}")
                lines.push(f"{r.bbox.x}")
                lines.push(f"{r.bbox.y}")
                lines.push(f"{r.bbox.w}")
                lines.push(f"{r.bbox.h}")
                lines.push(fnum(r.centroid.x as float64))
                lines.push(fnum(r.centroid.y as float64))
            }
            save_text(out, lines)
        }
        "flood_fill" => save8(out, ip.flood_fill(load8(inp), i(a[4]), i(a[5]), color(a, 6), i(a[10]), i(a[11])))
        "distance" => savef(out, ip.distance_transform(load8(inp)))
        "quality" => {
            let x = load8(inp)
            let y = load8(a[4])
            save_text(out, [fnum(ip.mse(x, y).expect("same")), fnum(ip.psnr(x, y).expect("same")), fnum(ip.ssim(x, y).expect("same"))])
        }
        _ => panic(f"unknown op {op}")
    }
}
'''


# ---- images, as the driver reads and writes them ----------------------------

class Img:
    """`w` by `h` pixels of `c` samples, `kind` "u8" (`data` bytes) or "f32"
    (`data` a list of floats)."""

    def __init__(self, w: int, h: int, c: int, kind: str, data):
        self.w, self.h, self.c, self.kind, self.data = w, h, c, kind, data

    def encode(self) -> bytes:
        head = b"MYIM" + struct.pack("<IIBBxx", self.w, self.h, self.c, 0 if self.kind == "u8" else 1)
        if self.kind == "u8":
            return head + bytes(self.data)
        return head + array("f", self.data).tobytes()

    @staticmethod
    def decode(b: bytes) -> "Img":
        assert b[:4] == b"MYIM", b[:16]
        w, h, c, kind = struct.unpack("<IIBB", b[4:14])
        if kind == 0:
            return Img(w, h, c, "u8", b[16:16 + w * h * c])
        return Img(w, h, c, "f32", list(array("f", b[16:16 + 4 * w * h * c])))


class Lcg:
    def __init__(self, seed: int):
        self.s = seed & 0xFFFFFFFF

    def next(self, n: int) -> int:
        self.s = (self.s * 1664525 + 1013904223) & 0xFFFFFFFF
        return (self.s >> 16) % n


def scene(w: int, h: int, c: int, seed: int) -> Img:
    """A gradient, a bright rectangle, a mid disc and a little noise."""
    rng = Lcg(seed)
    out = bytearray(w * h * c)
    cx, cy, rad = 0.68 * w, 0.62 * h, min(w, h) / 4.5
    for y in range(h):
        for x in range(w):
            inrect = w // 5 <= x < w // 2 and h // 4 <= y < (3 * h) // 5
            indisc = (x - cx) ** 2 + (y - cy) ** 2 < rad * rad
            for k in range(c):
                if k == 3:
                    v = 255 - (x * 200) // max(w - 1, 1)
                elif inrect:
                    v = 210 - 35 * k
                elif indisc:
                    v = 120 + 40 * k
                else:
                    v = 30 + (x * 90) // w + (y * 60) // h + 15 * k
                v += rng.next(13) - 6
                out[(y * w + x) * c + k] = max(0, min(255, v))
    return Img(w, h, c, "u8", bytes(out))


def blobs(w: int, h: int, seed: int) -> Img:
    """A mask (0 and 255): discs, bars, single pixels and diagonal touches."""
    rng = Lcg(seed)
    out = bytearray(w * h)
    shapes = []
    for _ in range(9):
        shapes.append((rng.next(w), rng.next(h), 1 + rng.next(6), rng.next(3)))
    for y in range(h):
        for x in range(w):
            on = False
            for (sx, sy, r, kind) in shapes:
                if kind == 0 and (x - sx) ** 2 + (y - sy) ** 2 <= r * r:
                    on = True
                elif kind == 1 and abs(x - sx) <= r * 2 and abs(y - sy) <= 1:
                    on = True
                elif kind == 2 and abs(x - sx) == abs(y - sy) and abs(x - sx) <= r:
                    on = True
            if on:
                out[y * w + x] = 255
    for _ in range(12):
        out[rng.next(h) * w + rng.next(w)] = 255
    return Img(w, h, 1, "u8", bytes(out))


def floats_of(img: Img, scale: float, offset: float) -> Img:
    return Img(img.w, img.h, img.c, "f32",
               list(array("f", [v * scale + offset for v in img.data])))


def hsv_of(img: Img) -> Img:
    out = []
    for i in range(img.w * img.h):
        r, g, b = (img.data[3 * i + k] / 255.0 for k in range(3))
        hh, s, v = colorsys.rgb_to_hsv(r, g, b)
        out += [hh * 360.0, s, v]
    return Img(img.w, img.h, 3, "f32", list(array("f", out)))


def srgb_to_linear(v: int) -> float:
    s = v / 255.0
    return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4


def linear_of(img: Img) -> Img:
    return Img(img.w, img.h, img.c, "f32", list(array("f", [srgb_to_linear(v) for v in img.data])))


def crop(img: Img, x0: int, y0: int, w: int, h: int) -> Img:
    out = bytearray()
    for y in range(y0, y0 + h):
        out += img.data[(y * img.w + x0) * img.c:(y * img.w + x0 + w) * img.c]
    return Img(w, h, img.c, "u8", bytes(out))


INPUTS = {
    "g": lambda: scene(61, 47, 1, 1),
    "g2": lambda: scene(61, 47, 1, 7),
    "rgb": lambda: scene(41, 33, 3, 2),
    "rgba": lambda: scene(23, 19, 4, 3),
    "even": lambda: scene(60, 48, 1, 5),
    "evenrgb": lambda: scene(36, 24, 3, 6),
    "mask": lambda: blobs(53, 41, 4),
    "small": lambda: scene(16, 12, 1, 8),
    "gf": lambda: floats_of(scene(61, 47, 1, 1), 1.0 / 255.0, -0.25),
    "hsv": lambda: hsv_of(scene(41, 33, 3, 2)),
    "lin": lambda: linear_of(scene(41, 33, 3, 2)),
    "tmpl": lambda: crop(scene(61, 47, 1, 1), 10, 9, 9, 7),
}

E = ["exact"]

# (name, op, input names, parameters, tolerance)
CASES = [
    ("gray_rgb", "gray", ["rgb"], [], E),
    ("gray_rgba", "gray", ["rgba"], [], E),
    ("to_rgb", "to_rgb", ["g"], [], E),
    ("to_hsv", "to_hsv", ["rgb"], [], ["rel", 1e-5]),
    ("from_hsv", "from_hsv", ["hsv"], [], ["abs", 0]),
    ("to_linear", "to_linear", ["rgba"], [], ["rel", 1e-6]),
    ("to_srgb", "to_srgb", ["lin"], [], E),
    ("invert", "invert", ["rgb"], [], E),
    ("invert_rgba", "invert", ["rgba"], [], E),
    ("lut", "lut", ["rgba"], [], E),
    ("adjust", "adjust", ["rgb"], ["-20", "1.4"], E),
    ("gamma", "gamma", ["g"], ["0.6"], E),
    ("threshold_binary", "threshold", ["g"], ["100", "binary", "200"], E),
    ("threshold_binary_inv", "threshold", ["g"], ["100", "binary_inv", "255"], E),
    ("threshold_trunc", "threshold", ["g"], ["120", "trunc", "255"], E),
    ("threshold_to_zero", "threshold", ["g"], ["90", "to_zero", "255"], E),
    ("threshold_to_zero_inv", "threshold", ["g"], ["90", "to_zero_inv", "255"], E),
    ("otsu", "otsu", ["g"], [], E),
    ("otsu_rgb", "otsu", ["rgb"], [], E),
    ("adaptive_mean", "adaptive", ["g"], ["7", "3", "mean"], E),
    ("adaptive_gaussian", "adaptive", ["g"], ["9", "2", "gaussian"], ["frac", 0, 0.002]),
    ("in_range", "in_range", ["rgb"], ["100", "50", "0", "0", "230", "200", "255", "255"], E),
    ("histogram", "histogram", ["g"], ["0"], E),
    ("histogram_green", "histogram", ["rgb"], ["1"], E),
    ("equalize", "equalize", ["g"], [], E),
    ("normalize", "normalize", ["rgb"], ["10", "240"], E),
    ("normalize_f", "normalize_f", ["gf"], [], ["abs", 1]),
    ("abs_diff", "abs_diff", ["g", "g2"], [], E),
    ("blend", "blend", ["g", "g2"], ["0.3"], E),
    ("apply_mask", "apply_mask", ["g", "g2"], [], E),
    ("resize_nearest_down", "resize", ["g"], ["23", "17", "nearest"], E),
    ("resize_nearest_up", "resize", ["rgb"], ["97", "50", "nearest"], E),
    ("resize_bilinear_down", "resize", ["g"], ["23", "17", "bilinear"], E),
    ("resize_bilinear_up", "resize", ["rgb"], ["97", "50", "bilinear"], E),
    ("resize_bicubic_down", "resize", ["g"], ["23", "17", "bicubic"], E),
    ("resize_bicubic_up", "resize", ["rgb"], ["97", "50", "bicubic"], E),
    ("resize_bicubic_mixed", "resize", ["g"], ["30", "80", "bicubic"], E),
    # the height shrunk by more than twice the width: Pillow's vertical pass first
    ("resize_bilinear_squeeze", "resize", ["g"], ["70", "9", "bilinear"], E),
    ("resize_lanczos3_squeeze", "resize", ["rgb"], ["38", "8", "lanczos3"], E),
    ("resize_lanczos3_down", "resize", ["g"], ["23", "17", "lanczos3"], E),
    ("resize_lanczos3_up", "resize", ["rgb"], ["97", "50", "lanczos3"], E),
    ("resize_area_whole", "resize", ["even"], ["20", "12", "area"], E),
    ("resize_area_whole_rgb", "resize", ["evenrgb"], ["12", "8", "area"], E),
    ("resize_area_fraction", "resize", ["g"], ["23", "17", "area"], ["abs", 1]),
    ("resize_f_bilinear", "resize_f", ["gf"], ["23", "30", "bilinear"], ["rel", 1e-5]),
    ("rotate", "rotate", ["g"], ["30", "same", "10", "20", "30", "40"], ["abs", 1]),
    ("rotate_expand", "rotate", ["rgb"], ["-17", "expand", "250", "0", "0", "255"], ["abs", 1]),
    ("warp_affine_bilinear", "warp_affine", ["g"],
     ["0.85", "-0.3", "6.5", "0.25", "0.9", "-3.25", "50", "40", "bilinear", "constant:0"], ["abs", 1]),
    ("warp_affine_nearest", "warp_affine", ["rgb"],
     ["1.15", "0.1", "-2.4", "-0.2", "1.05", "1.7", "40", "36", "nearest", "replicate"], ["frac", 0, 0.01]),
    ("warp_affine_bicubic", "warp_affine", ["g"],
     ["0.7", "0.0", "3.3", "0.0", "0.6", "2.1", "50", "35", "bicubic", "reflect101"], ["abs", 1]),
    ("warp_perspective", "warp_perspective", ["g"],
     ["0.9", "0.1", "2", "-0.05", "1.1", "1", "0.004", "0.002", "60", "47", "bilinear", "constant:255"], ["abs", 1]),
    ("affine_from", "affine_from", [],
     ["0", "0", "10", "1", "2", "9", "3", "4", "15", "6", "1", "13"], ["rel", 1e-5]),
    ("perspective_from", "perspective_from", [],
     ["0", "0", "10", "0", "10", "10", "0", "10", "1", "2", "12", "1", "11", "13", "-1", "9"], ["rel", 1e-4]),
    ("pad_constant", "pad", ["rgb"], ["2", "3", "1", "4", "constant:7"], E),
    ("pad_replicate", "pad", ["g"], ["3", "1", "2", "5", "replicate"], E),
    ("pad_reflect", "pad", ["g"], ["3", "1", "2", "5", "reflect"], E),
    ("pad_reflect101", "pad", ["g"], ["3", "1", "2", "5", "reflect101"], E),
    ("pad_wrap", "pad", ["g"], ["3", "1", "2", "5", "wrap"], E),
    ("pyr_down", "pyr_down", ["g"], [], ["abs", 1]),
    ("pyr_up", "pyr_up", ["rgb"], [], ["abs", 1]),
    ("convolve", "convolve", ["g"],
     ["4", "3", "0.1", "-0.2", "0.3", "0.05", "0.2", "0.4", "-0.1", "0.15", "0.0", "0.1", "0.05", "-0.05", "reflect101"],
     ["abs", 1]),
    ("convolve_constant", "convolve", ["rgb"],
     ["3", "3", "0.1", "0.1", "0.1", "0.1", "0.2", "0.1", "0.1", "0.1", "0.1", "constant:255"], ["abs", 1]),
    ("convolve_sep", "convolve_sep", ["g"], ["3", "0.25", "0.5", "0.25", "5", "-0.1", "0.2", "0.8", "0.2", "-0.1", "wrap"],
     ["abs", 1]),
    ("box_blur", "box_blur", ["g"], ["3", "reflect101"], E),
    ("box_blur_rgb_constant", "box_blur", ["rgb"], ["2", "constant:100"], E),
    ("gaussian", "gaussian", ["g"], ["2", "reflect101"], ["abs", 1]),
    ("gaussian_rgb", "gaussian", ["rgb"], ["1.3", "replicate"], ["abs", 1]),
    ("gaussian_f", "gaussian_f", ["gf"], ["1.5", "reflect"], ["rel", 1e-5]),
    ("median3_rgb", "median", ["rgb"], ["1"], E),
    ("median5", "median", ["g"], ["2"], E),
    ("sharpen", "sharpen", ["g"], ["0.7"], ["abs", 1]),
    ("unsharp", "unsharp", ["g"], ["1.5", "0.8", "4"], ["abs", 1]),
    ("sobel_dx", "sobel", ["g"], ["1", "0", "3", "reflect101"], E),
    ("sobel_dy5", "sobel", ["g"], ["0", "1", "5", "reflect101"], E),
    ("sobel_dxx", "sobel", ["g"], ["2", "0", "3", "replicate"], E),
    ("sobel_dxy", "sobel", ["rgb"], ["1", "1", "3", "replicate"], E),
    ("sobel_dx1", "sobel", ["g"], ["1", "0", "1", "reflect101"], E),
    ("scharr_dy", "scharr", ["g"], ["0", "1"], E),
    ("laplacian1", "laplacian", ["g"], ["1"], E),
    ("laplacian3", "laplacian", ["g"], ["3"], E),
    ("magnitude", "magnitude", ["g"], [], ["rel", 1e-6]),
    ("angle", "angle", ["g"], [], ["rel", 1e-6]),
    ("erode_rect5", "erode", ["g"], ["rect", "5", "5"], E),
    ("dilate_rect5", "dilate", ["rgb"], ["rect", "5", "5"], E),
    ("erode_rect3x7", "erode", ["g"], ["rect", "3", "7"], E),
    ("dilate_ellipse7", "dilate", ["mask"], ["ellipse", "7", "7"], E),
    ("erode_cross5", "erode", ["g"], ["cross", "5", "5"], E),
    ("dilate_ellipse6x4", "dilate", ["g"], ["ellipse", "6", "4"], E),
    ("morph_open", "morph", ["mask"], ["open", "ellipse", "5", "5"], E),
    ("morph_close_even", "morph", ["mask"], ["close", "rect", "4", "2"], E),
    ("morph_gradient", "morph", ["g"], ["gradient", "cross", "3", "3"], E),
    ("morph_tophat", "morph", ["g"], ["tophat", "rect", "7", "7"], E),
    ("morph_blackhat", "morph", ["g"], ["blackhat", "ellipse", "9", "5"], E),
    ("canny", "canny", ["g"], ["40", "120"], E),
    ("canny_rgb", "canny", ["rgb"], ["60", "200"], E),
    ("harris", "harris", ["g"], ["3", "0.04"], ["rel", 1e-4]),
    ("good_features", "good_features", ["g"], ["12", "0.05", "5"], E),
    ("match_ssd", "match_template", ["g", "tmpl"], ["ssd"], ["rel", 1e-6]),
    ("match_ncc", "match_template", ["g", "tmpl"], ["ncc"], ["rel", 1e-5]),
    ("match_zncc", "match_template", ["g", "tmpl"], ["zncc"], ["rel", 1e-5]),
    ("min_max", "min_max", ["gf"], [], E),
    ("integral", "integral", ["rgb"], ["2"], E),
    ("labels8", "labels", ["mask"], ["8"], E),
    ("labels4", "labels", ["mask"], ["4"], E),
    ("regions8", "regions", ["mask"], ["8"], ["rel", 1e-6]),
    ("regions4", "regions", ["mask"], ["4"], ["rel", 1e-6]),
    ("flood_fill", "flood_fill", ["g"], ["5", "5", "255", "0", "0", "0", "12", "4"], E),
    ("flood_fill_rgb", "flood_fill", ["rgb"], ["20", "15", "1", "2", "3", "0", "20", "8"], E),
    ("distance", "distance", ["mask"], [], E),
    ("quality", "quality", ["g", "g2"], [], ["rel", 1e-9]),
]


def _text_values(b: bytes) -> list[str]:
    return b.decode().split()


def _close(a: float, b: float, rel: float) -> bool:
    if math.isinf(a) or math.isinf(b) or math.isnan(a) or math.isnan(b):
        return a == b or (math.isnan(a) and math.isnan(b))
    return abs(a - b) <= rel * max(1.0, abs(b))


def compare(got: bytes, want: bytes, tol: list) -> str | None:
    """None if `got` matches `want` within `tol`, else what differs."""
    if want[:4] != b"MYIM":
        g, w = _text_values(got), _text_values(want)
        if len(g) != len(w):
            return f"{len(g)} values, expected {len(w)}"
        for k, (a, b) in enumerate(zip(g, w)):
            if tol[0] == "rel" and a != b:
                if not _close(float(a), float(b), tol[1]):
                    return f"value {k}: {a}, expected {b}"
            elif tol[0] != "rel" and a != b:
                return f"value {k}: {a}, expected {b}"
        return None
    gi, wi = Img.decode(got), Img.decode(want)
    if (gi.w, gi.h, gi.c, gi.kind) != (wi.w, wi.h, wi.c, wi.kind):
        return f"{gi.w}x{gi.h}x{gi.c} {gi.kind}, expected {wi.w}x{wi.h}x{wi.c} {wi.kind}"
    worst, off = 0.0, 0
    limit = tol[1] if tol[0] in ("abs", "frac") else 0
    for k, (a, b) in enumerate(zip(gi.data, wi.data)):
        if tol[0] == "rel":
            if not _close(a, b, tol[1]):
                return f"sample {k}: {a}, expected {b}"
            continue
        d = abs(a - b)
        worst = max(worst, d)
        if d > limit:
            off += 1
            if tol[0] != "frac":
                return f"sample {k} (pixel {(k // gi.c) % gi.w}, {(k // gi.c) // gi.w}): {a}, expected {b}"
    if tol[0] == "frac" and off > tol[2] * len(gi.data):
        return f"{off} of {len(gi.data)} samples off by more than {limit} (worst {worst})"
    return None


class ImgprocTest(unittest.TestCase):
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
            p = os.path.join(cls.tmp, name + ".img")
            with open(p, "wb") as fh:
                fh.write(make().encode())
            cls.inputs[name] = p

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_case(self, name: str, op: str, ins: list[str], params: list[str]) -> bytes:
        out = os.path.join(self.tmp, name + ".out")
        files = [self.inputs[n] for n in ins]
        args = [op, out, *(files[:1] or ["-"]), *files[1:], *params]
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
                self.assertIsNone(problem, f"{name} ({' '.join(tol[:1] + [str(t) for t in tol[1:]])}): {problem}")

    def test_every_case_vendored(self) -> None:
        names = {c[0] for c in CASES}
        self.assertEqual(len(names), len(CASES))
        on_disk = {n[:-3] for n in os.listdir(DATA) if n.endswith(".gz")}
        self.assertEqual(on_disk, names)


# ---- the references (only for --vendor: they need numpy and Pillow) -------
#
# Written from the definitions (OpenCV's and Pillow's documentation, the
# papers), not from lib/std/imgproc.my. numpy is `np`, bound by `vendor`.

np = None
PIL = None


def _arr(img: Img):
    if img.kind == "u8":
        return np.frombuffer(img.data, np.uint8).reshape(img.h, img.w, img.c).astype(np.int64)
    return np.array(img.data, np.float64).reshape(img.h, img.w, img.c)


def _u8(a) -> Img:
    a = np.asarray(a)
    return Img(a.shape[1], a.shape[0], a.shape[2], "u8", a.astype(np.uint8).tobytes())


def _f32(a) -> Img:
    a = np.asarray(a, np.float32)
    return Img(a.shape[1], a.shape[0], a.shape[2], "f32", [float(v) for v in a.ravel()])


def _round(x, hi=255):
    """Halves up, clamped, as integers."""
    return np.clip(np.floor(np.asarray(x, np.float64) + 0.5), 0, hi).astype(np.int64)


def _pil(img: Img):
    mode = {1: "L", 3: "RGB", 4: "RGBA"}[img.c]
    return PIL.Image.frombytes(mode, (img.w, img.h), bytes(img.data))


def _from_pil(im) -> Img:
    c = {"L": 1, "RGB": 3, "RGBA": 4}[im.mode]
    return Img(im.size[0], im.size[1], c, "u8", im.tobytes())


def _border(s: str):
    if s.startswith("constant:"):
        return ("constant", float(s[9:]))
    return ({"replicate": "edge", "reflect": "symmetric", "reflect101": "reflect", "wrap": "wrap"}[s], None)


def _pad(a, top, bottom, left, right, border: str):
    mode, value = _border(border)
    width = ((top, bottom), (left, right), (0, 0))
    if mode == "constant":
        return np.pad(a, width, mode="constant", constant_values=value)
    return np.pad(a, width, mode=mode)


def _corr(a, k, border: str):
    """2D correlation of (h, w, c) with the (kh, kw) kernel, anchored at its middle."""
    k = np.asarray(k, np.float64)
    kh, kw = k.shape
    ax, ay = kw // 2, kh // 2
    p = _pad(np.asarray(a, np.float64), ay, kh - 1 - ay, ax, kw - 1 - ax, border)
    h, w = a.shape[0], a.shape[1]
    out = np.zeros(a.shape, np.float64)
    for ty in range(kh):
        for tx in range(kw):
            if k[ty, tx] != 0:
                out += k[ty, tx] * p[ty:ty + h, tx:tx + w]
    return out


def _gauss1(sigma: float, radius: int):
    x = np.arange(-radius, radius + 1, dtype=np.float64)
    k = np.exp(-(x * x) / (2 * sigma * sigma))
    return k / k.sum()


# the derivative kernels of OpenCV's documentation, by size and order
SOBEL = {
    (3, 0): [1, 2, 1], (3, 1): [-1, 0, 1], (3, 2): [1, -2, 1],
    (5, 0): [1, 4, 6, 4, 1], (5, 1): [-1, -2, 0, 2, 1], (5, 2): [1, 0, -2, 0, 1],
    (1, 0): [1], (1, 1): [-1, 0, 1], (1, 2): [1, -2, 1],
}


def _sobel(a, dx, dy, size, border):
    kx = np.array(SOBEL[(size, dx)], np.float64)
    ky = np.array(SOBEL[(size, dy)], np.float64)
    return _corr(a, np.outer(ky, kx), border)


def _element(shape: str, w: int, h: int):
    m = np.zeros((h, w), bool)
    if shape == "rect":
        m[:, :] = True
    elif shape == "cross":
        m[h // 2, :] = True
        m[:, w // 2] = True
    else:  # OpenCV's MORPH_ELLIPSE
        r, c = h // 2, w // 2
        inv_r2 = 1.0 / (r * r) if r else 0.0
        for i in range(h):
            dy = i - r
            if abs(dy) <= r:
                dx = int(np.rint(c * math.sqrt((r * r - dy * dy) * inv_r2)))
                m[i, max(c - dx, 0):min(c + dx + 1, w)] = True
    return m


def _rank(a, m, take_max: bool, reflect: bool = False):
    """min or max over the element's pixels, anchor (w/2, h/2), pixels outside ignored."""
    h, w = a.shape[0], a.shape[1]
    eh, ew = m.shape
    ax, ay = ew // 2, eh // 2
    ident = 0 if take_max else 255
    out = np.full(a.shape, ident, np.int64)
    for ty in range(eh):
        for tx in range(ew):
            if not m[ty, tx]:
                continue
            ox, oy = tx - ax, ty - ay
            if reflect:
                ox, oy = -ox, -oy
            shifted = np.full(a.shape, ident, np.int64)
            ys, ye = max(0, -oy), min(h, h - oy)
            xs, xe = max(0, -ox), min(w, w - ox)
            if ys < ye and xs < xe:
                shifted[ys:ye, xs:xe] = a[ys + oy:ye + oy, xs + ox:xe + ox]
            out = np.maximum(out, shifted) if take_max else np.minimum(out, shifted)
    return out


def _canny(g, low, high):
    """OpenCV's Canny with an L2 gradient, from its description and source's rules."""
    h, w = g.shape
    p = np.pad(g, 1, mode="edge")
    gx = (p[0:h, 2:] + 2 * p[1:h + 1, 2:] + p[2:, 2:]) - (p[0:h, :w] + 2 * p[1:h + 1, :w] + p[2:, :w])
    gy = (p[2:, :w] + 2 * p[2:, 1:w + 1] + p[2:, 2:]) - (p[:h, :w] + 2 * p[:h, 1:w + 1] + p[:h, 2:])
    mag = np.zeros((h + 2, w + 2), np.int64)
    mag[1:-1, 1:-1] = gx * gx + gy * gy
    lo, hi = low * low, high * high
    state = np.ones((h + 2, w + 2), np.int64)
    stack = []
    for y in range(h):
        for x in range(w):
            m = int(mag[y + 1, x + 1])
            if not m > lo:
                continue
            xs, ys = int(gx[y, x]), int(gy[y, x])
            ax, ay = abs(xs), abs(ys) << 15
            tg22 = ax * 13573  # tan(22.5°) in 15 bits
            j = (y + 1, x + 1)
            if ay < tg22:
                ok = m > mag[y + 1, x] and m >= mag[y + 1, x + 2]
            elif ay > tg22 + (ax << 16):
                ok = m > mag[y, x + 1] and m >= mag[y + 2, x + 1]
            else:
                s = -1 if (xs < 0) != (ys < 0) else 1
                ok = m > mag[y, x + 1 - s] and m > mag[y + 2, x + 1 + s]
            if ok:
                if m > hi:
                    state[j] = 2
                    stack.append(j)
                else:
                    state[j] = 0
    while stack:
        y, x = stack.pop()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if state[y + dy, x + dx] == 0:
                    state[y + dy, x + dx] = 2
                    stack.append((y + dy, x + dx))
    return np.where(state[1:-1, 1:-1] == 2, 255, 0)


def _tensor(g, block):
    """Sums over `block` of the products of Sobel derivatives / (8 * 255)."""
    a = g.reshape(g.shape[0], g.shape[1], 1) / (8.0 * 255.0)
    gx = _sobel(a, 1, 0, 3, "reflect101")
    gy = _sobel(a, 0, 1, 3, "reflect101")
    ones = np.ones((block, block))
    return (_corr(gx * gx, ones, "reflect101")[:, :, 0], _corr(gx * gy, ones, "reflect101")[:, :, 0],
            _corr(gy * gy, ones, "reflect101")[:, :, 0])


def _bfs_labels(mask, conn):
    h, w = mask.shape
    lab = np.zeros((h, w), np.int64)
    n = 0
    nbs = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    if conn == 8:
        nbs += [(-1, -1), (-1, 1), (1, -1), (1, 1)]
    for y in range(h):
        for x in range(w):
            if mask[y, x] and lab[y, x] == 0:
                n += 1
                lab[y, x] = n
                todo = [(y, x)]
                while todo:
                    cy, cx = todo.pop()
                    for dy, dx in nbs:
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and lab[ny, nx] == 0:
                            lab[ny, nx] = n
                            todo.append((ny, nx))
    return n, lab


def _sample(a, x, y, border, fill):
    """The pixel (x, y) of (h, w, c) through the border; `fill` for a constant."""
    h, w = a.shape[0], a.shape[1]

    def at(i, n):
        if 0 <= i < n:
            return i
        mode, _ = _border(border)
        if mode == "constant":
            return None
        if mode == "edge":
            return 0 if i < 0 else n - 1
        if mode == "wrap":
            return i % n
        if mode == "symmetric":
            j = i % (2 * n)
            return 2 * n - 1 - j if j >= n else j
        if n == 1:
            return 0
        j = i % (2 * n - 2)
        return 2 * n - 2 - j if j >= n else j
    xi, yi = at(x, w), at(y, h)
    if xi is None or yi is None:
        return fill
    return a[yi, xi]


def _keys(t):
    t = abs(t)
    if t < 1:
        return (1.5 * t - 2.5) * t * t + 1
    if t < 2:
        return ((-0.5 * t + 2.5) * t - 4) * t + 2
    return 0.0


def _warp(a, inv, ow, oh, filt, border, fill, perspective=False):
    out = np.zeros((oh, ow, a.shape[2]))
    for oy in range(oh):
        for ox in range(ow):
            v = inv @ np.array([ox, oy, 1.0])
            sx, sy = v[0], v[1]
            if perspective:
                sx, sy = sx / v[2], sy / v[2]
            if filt == "nearest":
                out[oy, ox] = _sample(a, int(math.floor(sx + 0.5)), int(math.floor(sy + 0.5)), border, fill)
                continue
            n = 2 if filt == "bilinear" else 4
            x0 = math.floor(sx) - n // 2 + 1
            y0 = math.floor(sy) - n // 2 + 1
            wf = (lambda d: max(0.0, 1 - abs(d))) if n == 2 else _keys
            wx = [wf(sx - (x0 + t)) for t in range(n)]
            wy = [wf(sy - (y0 + t)) for t in range(n)]
            acc = np.zeros(a.shape[2])
            for ty in range(n):
                for tx in range(n):
                    wt = wy[ty] / sum(wy) * wx[tx] / sum(wx)
                    if wt != 0:
                        acc = acc + wt * _sample(a, x0 + tx, y0 + ty, border, fill)
            out[oy, ox] = acc
    return out


def _f32v(s) -> float:
    return float(np.float32(float(s)))


def _mat(params, n):
    r = [_f32v(v) for v in params[:n]] + [0.0] * (8 - n) + [1.0]
    if n == 6:
        r[6:9] = [0.0, 0.0, 1.0]
    return np.array(r, np.float64).reshape(3, 3)


def _area_matrix(n_in, n_out):
    """Exact coverage weights: output pixel i averages input [i*s, (i+1)*s)."""
    s = n_in / n_out
    m = np.zeros((n_out, n_in))
    for i in range(n_out):
        a, b = i * s, (i + 1) * s
        for j in range(int(math.floor(a)), min(n_in, int(math.ceil(b)))):
            m[i, j] = max(0.0, min(b, j + 1) - max(a, j))
        m[i] /= m[i].sum()
    return m


def _ssim(a, b):
    L = 255.0
    c1, c2 = (0.01 * L) ** 2, (0.03 * L) ** 2
    k = np.outer(_gauss1(1.5, 5), _gauss1(1.5, 5))
    f = lambda x: _corr(x, k, "reflect101")[5:-5, 5:-5]
    ma, mb = f(a), f(b)
    va = f(a * a) - ma * ma
    vb = f(b * b) - mb * mb
    cov = f(a * b) - ma * mb
    m = ((2 * ma * mb + c1) * (2 * cov + c2)) / ((ma * ma + mb * mb + c1) * (va + vb + c2))
    return float(m.mean())


def _num(x: float) -> str:
    return repr(float(x))


def reference(op: str, ins: list, params: list):
    A = [_arr(i) for i in ins]
    a = A[0] if A else None
    P = params
    if op == "gray":
        return _from_pil(_pil(ins[0]).convert("L"))
    if op == "to_rgb":
        return _from_pil(_pil(ins[0]).convert("RGB"))
    if op == "to_hsv":
        out = np.zeros((a.shape[0], a.shape[1], 3))
        for y in range(a.shape[0]):
            for x in range(a.shape[1]):
                hh, s, v = colorsys.rgb_to_hsv(*(a[y, x, :3] / 255.0))
                out[y, x] = (hh * 360.0, s, v)
        return _f32(out)
    if op == "from_hsv":
        out = np.zeros(a.shape)
        for y in range(a.shape[0]):
            for x in range(a.shape[1]):
                out[y, x] = colorsys.hsv_to_rgb(a[y, x, 0] / 360.0, a[y, x, 1], a[y, x, 2])
        return _u8(_round(out * 255.0))
    if op == "to_linear":
        s = a / 255.0
        lin = np.where(s <= 0.04045, s / 12.92, ((s + 0.055) / 1.055) ** 2.4)
        if a.shape[2] == 4:
            lin[:, :, 3] = s[:, :, 3]
        return _f32(lin)
    if op == "to_srgb":
        l = np.clip(a, 0, 1)
        s = np.where(l <= 0.0031308, l * 12.92, 1.055 * l ** (1 / 2.4) - 0.055)
        return _u8(_round(s * 255.0))
    if op == "invert":
        if ins[0].c == 3:
            return _from_pil(PIL.ImageOps.invert(_pil(ins[0])))
        out = 255 - a
        out[:, :, -1] = a[:, :, -1]
        return _u8(out)
    if op == "lut":
        t = (np.arange(256) * 7 + 3) % 256
        out = t[a]
        if a.shape[2] in (2, 4):
            out[:, :, -1] = a[:, :, -1]
        return _u8(out)
    if op == "adjust":
        b, c = _f32v(P[0]), _f32v(P[1])
        return _u8(_round((a - 127.5) * c + 127.5 + b))
    if op == "gamma":
        g = _f32v(P[0])
        return _u8(_round(255.0 * (a / 255.0) ** g))
    if op == "threshold":
        t, mode, mx = int(P[0]), P[1], int(P[2])
        above = a > t
        out = {"binary": np.where(above, mx, 0), "binary_inv": np.where(above, 0, mx),
               "trunc": np.where(above, t, a), "to_zero": np.where(above, a, 0),
               "to_zero_inv": np.where(above, 0, a)}[mode]
        return _u8(out)
    if op == "otsu":
        g = _arr(_from_pil(_pil(ins[0]).convert("L")))[:, :, 0]
        hist = np.bincount(g.ravel(), minlength=256).astype(np.float64)
        best, t = -1.0, 0
        for v in range(256):
            wb, wf = hist[:v + 1].sum(), hist[v + 1:].sum()
            if wb == 0:
                continue
            if wf == 0:
                break
            mb = (np.arange(v + 1) * hist[:v + 1]).sum() / wb
            mf = (np.arange(v + 1, 256) * hist[v + 1:]).sum() / wf
            between = wb * wf * (mb - mf) ** 2
            if between > best:
                best, t = between, v
        return [str(t)]
    if op == "adaptive":
        block, c, method = int(P[0]), float(P[1]), P[2]
        g = a.astype(np.float64)
        if method == "mean":
            s = _corr(g, np.ones((block, block)), "replicate")
            return _u8(np.where((g + c) * block * block > s, 255, 0))
        sigma = 0.3 * ((block - 1) * 0.5 - 1) + 0.8
        k1 = _gauss1(sigma, block // 2)
        t = _corr(g, np.outer(k1, k1), "replicate")
        return _u8(np.where(g > t - c, 255, 0))
    if op == "in_range":
        lo = np.array([int(v) for v in P[0:3]])
        hi = np.array([int(v) for v in P[4:7]])
        ok = np.all((a >= lo) & (a <= hi), axis=2)
        return _u8(np.where(ok, 255, 0)[:, :, None])
    if op == "histogram":
        ch = int(P[0])
        h = _pil(ins[0]).histogram()
        return [str(v) for v in h[256 * ch:256 * (ch + 1)]]
    if op == "equalize":
        out = a.copy()
        n = a.shape[0] * a.shape[1]
        for ch in range(a.shape[2]):
            hist = np.bincount(a[:, :, ch].ravel(), minlength=256)
            cdf = np.cumsum(hist)
            cmin = hist[np.nonzero(hist)[0][0]]
            if n == cmin:
                continue
            table = (2 * (cdf - cmin) * 255 + (n - cmin)) // (2 * (n - cmin))
            table = np.where(cdf >= cmin, table, 0)
            out[:, :, ch] = table[a[:, :, ch]]
        return _u8(out)
    if op == "normalize":
        lo, hi = int(P[0]), int(P[1])
        mn, mx = a.min(), a.max()
        return _u8(lo + (2 * (a - mn) * (hi - lo) + (mx - mn)) // (2 * (mx - mn)))
    if op == "normalize_f":
        return _u8(_round((a - a.min()) * (255.0 / (a.max() - a.min()))))
    if op == "abs_diff":
        return _from_pil(PIL.ImageChops.difference(_pil(ins[0]), _pil(ins[1])))
    if op == "blend":
        al = _f32v(P[0])
        return _u8(_round(A[0] + (A[1] - A[0]) * al))
    if op == "apply_mask":
        return _u8(np.where(A[1][:, :, :1] != 0, A[0], 0))
    if op == "resize":
        w, h, filt = int(P[0]), int(P[1]), P[2]
        if filt == "area" and (ins[0].w % w or ins[0].h % h):
            wx, wy = _area_matrix(ins[0].w, w), _area_matrix(ins[0].h, h)
            return _u8(_round(np.einsum("yi,ijc,xj->yxc", wy, a.astype(np.float64), wx)))
        f = {"nearest": PIL.Image.NEAREST, "bilinear": PIL.Image.BILINEAR, "bicubic": PIL.Image.BICUBIC,
             "area": PIL.Image.BOX, "lanczos3": PIL.Image.LANCZOS}[filt]
        return _from_pil(_pil(ins[0]).resize((w, h), f))
    if op == "resize_f":
        w, h = int(P[0]), int(P[1])
        im = PIL.Image.frombytes("F", (ins[0].w, ins[0].h), array("f", ins[0].data).tobytes())
        r = im.resize((w, h), PIL.Image.BILINEAR)
        return Img(w, h, 1, "f32", list(array("f", r.tobytes())))
    if op == "rotate":
        deg, expand = _f32v(P[0]), P[1] == "expand"
        fill = np.array([float(v) for v in P[2:6]][:ins[0].c] if ins[0].c > 1 else [float(P[2])])
        t = math.radians(deg)
        cs, sn = math.cos(t), math.sin(t)
        w, h = ins[0].w, ins[0].h
        ow, oh = w, h
        if expand:
            ow = math.ceil(abs(w * cs) + abs(h * sn) - 1e-6)
            oh = math.ceil(abs(w * sn) + abs(h * cs) - 1e-6)
        cx, cy, ox, oy = (w - 1) / 2, (h - 1) / 2, (ow - 1) / 2, (oh - 1) / 2
        inv = np.array([[cs, -sn, cx - cs * ox + sn * oy], [sn, cs, cy - sn * ox - cs * oy], [0, 0, 1]])
        return _u8(_round(_warp(a.astype(np.float64), inv, ow, oh, "bilinear", "constant:0", fill)))
    if op in ("warp_affine", "warp_perspective"):
        n = 6 if op == "warp_affine" else 8
        m = _mat(P, n)
        ow, oh, filt, border = int(P[n]), int(P[n + 1]), P[n + 2], P[n + 3]
        mode, value = _border(border)
        fill = np.full(a.shape[2], value if mode == "constant" else 0.0)
        out = _warp(a.astype(np.float64), np.linalg.inv(m), ow, oh, filt, border, fill, op == "warp_perspective")
        return _u8(_round(out))
    if op == "affine_from":
        src = np.array([_f32v(v) for v in P[:6]]).reshape(3, 2)
        dst = np.array([_f32v(v) for v in P[6:]]).reshape(3, 2)
        A3 = np.hstack([src, np.ones((3, 1))])
        u, v = np.linalg.solve(A3, dst[:, 0]), np.linalg.solve(A3, dst[:, 1])
        return [_num(np.float32(x)) for x in list(u) + list(v) + [0.0, 0.0, 1.0]]
    if op == "perspective_from":
        src = np.array([_f32v(v) for v in P[:8]]).reshape(4, 2)
        dst = np.array([_f32v(v) for v in P[8:]]).reshape(4, 2)
        rows, rhs = [], []
        for (x, y), (u, v) in zip(src, dst):
            rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
            rhs.append(u)
            rows.append([0, 0, 0, x, y, 1, -v * x, -v * y])
            rhs.append(v)
        hh = np.linalg.solve(np.array(rows), np.array(rhs))
        return [_num(np.float32(x)) for x in list(hh) + [1.0]]
    if op == "pad":
        t, r, b, l = (int(v) for v in P[:4])
        return _u8(_round(_pad(a, t, b, l, r, P[4])))
    if op == "pyr_down":
        k = np.array([1, 4, 6, 4, 1]) / 16.0
        return _u8(_round(_corr(a, np.outer(k, k), "reflect101")[::2, ::2]))
    if op == "pyr_up":
        z = np.zeros((2 * a.shape[0], 2 * a.shape[1], a.shape[2]))
        z[::2, ::2] = a
        k = np.array([1, 4, 6, 4, 1]) / 8.0
        return _u8(_round(_corr(z, np.outer(k, k), "reflect101")))
    if op == "convolve":
        kw, kh = int(P[0]), int(P[1])
        k = np.array([_f32v(v) for v in P[2:2 + kw * kh]]).reshape(kh, kw)
        return _u8(_round(_corr(a, k, P[2 + kw * kh])))
    if op == "convolve_sep":
        nx = int(P[0])
        kx = np.array([_f32v(v) for v in P[1:1 + nx]])
        ny = int(P[1 + nx])
        ky = np.array([_f32v(v) for v in P[2 + nx:2 + nx + ny]])
        return _u8(_round(_corr(a, np.outer(ky, kx), P[2 + nx + ny])))
    if op == "box_blur":
        r = int(P[0])
        n = 2 * r + 1
        s = _corr(a, np.ones((n, n)), P[1]).round().astype(np.int64)
        return _u8((2 * s + n * n) // (2 * n * n))
    if op in ("gaussian", "gaussian_f"):
        sigma = _f32v(P[0])
        k1 = _gauss1(sigma, max(1, math.ceil(3 * sigma)))
        out = _corr(a, np.outer(k1, k1), P[1])
        return _f32(out) if op == "gaussian_f" else _u8(_round(out))
    if op == "median":
        return _from_pil(_pil(ins[0]).filter(PIL.ImageFilter.MedianFilter(2 * int(P[0]) + 1)))
    if op == "sharpen":
        s = _f32v(P[0])
        k = np.array([[0, -s, 0], [-s, 1 + 4 * s, -s], [0, -s, 0]])
        return _u8(_round(_corr(a, k, "reflect101")))
    if op == "unsharp":
        sigma, amount, thr = _f32v(P[0]), _f32v(P[1]), _f32v(P[2])
        k1 = _gauss1(sigma, max(1, math.ceil(3 * sigma)))
        d = a - _corr(a, np.outer(k1, k1), "reflect101")
        return _u8(_round(np.where(np.abs(d) >= thr, a + amount * d, a)))
    if op == "sobel":
        return _f32(_sobel(a, int(P[0]), int(P[1]), int(P[2]), P[3]))
    if op == "scharr":
        d, s = np.array([-1, 0, 1]), np.array([3, 10, 3])
        k = np.outer(s, d) if P[0] == "1" else np.outer(d, s)
        return _f32(_corr(a, k, "reflect101"))
    if op == "laplacian":
        if P[0] == "1":
            return _f32(_corr(a, [[0, 1, 0], [1, -4, 1], [0, 1, 0]], "reflect101"))
        return _f32(_sobel(a, 2, 0, 3, "reflect101") + _sobel(a, 0, 2, 3, "reflect101"))
    if op in ("magnitude", "angle"):
        gx = _sobel(a, 1, 0, 3, "reflect101")
        gy = _sobel(a, 0, 1, 3, "reflect101")
        return _f32(np.hypot(gx, gy) if op == "magnitude" else np.arctan2(gy, gx))
    if op in ("erode", "dilate"):
        shape, w, h = P[0], int(P[1]), int(P[2])
        if shape == "rect" and w == h:
            f = PIL.ImageFilter.MinFilter(w) if op == "erode" else PIL.ImageFilter.MaxFilter(w)
            return _from_pil(_pil(ins[0]).filter(f))
        return _u8(_rank(a, _element(shape, w, h), op == "dilate"))
    if op == "morph":
        what, m = P[0], _element(P[1], int(P[2]), int(P[3]))
        er, di = _rank(a, m, False), _rank(a, m, True)
        opened = _rank(er, m, True, True)
        closed = _rank(di, m, False, True)
        out = {"open": opened, "close": closed, "gradient": di - er,
               "tophat": np.maximum(a - opened, 0), "blackhat": np.maximum(closed - a, 0)}[what]
        return _u8(out)
    if op == "canny":
        g = _arr(_from_pil(_pil(ins[0]).convert("L")))[:, :, 0]
        return _u8(_canny(g, _f32v(P[0]), _f32v(P[1]))[:, :, None])
    if op == "harris":
        block, k = int(P[0]), _f32v(P[1])
        xx, xy, yy = _tensor(a[:, :, 0].astype(np.float64), block)
        return _f32((xx * yy - xy * xy - k * (xx + yy) ** 2)[:, :, None])
    if op == "good_features":
        mx, quality, md = int(P[0]), _f32v(P[1]), _f32v(P[2])
        xx, xy, yy = _tensor(a[:, :, 0].astype(np.float64), 3)
        e = (xx + yy) / 2 - np.sqrt(((xx - yy) / 2) ** 2 + xy * xy)
        thr = e.max() * quality
        h, w = e.shape
        cands = []
        for y in range(h):
            for x in range(w):
                v = e[y, x]
                if v > thr and v > 0 and v >= e[max(0, y - 1):y + 2, max(0, x - 1):x + 2].max():
                    cands.append((v, y, x))
        cands.sort(key=lambda t: -t[0])
        out = []
        for v, y, x in cands:
            if all((px - x) ** 2 + (py - y) ** 2 >= md * md for px, py in out):
                out.append((x, y))
                if len(out) == mx:
                    break
        return [f"{x} {y}" for x, y in out]
    if op == "match_template":
        img, t = A[0].astype(np.float64), A[1].astype(np.float64)
        th, tw = t.shape[0], t.shape[1]
        oh, ow = img.shape[0] - th + 1, img.shape[1] - tw + 1
        out = np.zeros((oh, ow, 1))
        tz = t - t.mean()
        for y in range(oh):
            for x in range(ow):
                win = img[y:y + th, x:x + tw]
                if P[0] == "ssd":
                    out[y, x] = ((win - t) ** 2).sum()
                elif P[0] == "ncc":
                    d = math.sqrt((win * win).sum() * (t * t).sum())
                    out[y, x] = (win * t).sum() / d if d > 0 else 0
                else:
                    wz = win - win.mean()
                    d = math.sqrt((wz * wz).sum() * (tz * tz).sum())
                    out[y, x] = (wz * tz).sum() / d if d > 0 else 0
        return _f32(out)
    if op == "min_max":
        f = np.array(ins[0].data, np.float32).reshape(ins[0].h, ins[0].w, ins[0].c)[:, :, 0]
        i, j = int(np.argmin(f)), int(np.argmax(f))
        w = ins[0].w
        return [_num(f.min()), _num(f.max()), str(i % w), str(i // w), str(j % w), str(j // w)]
    if op == "integral":
        ch = a[:, :, int(P[0])]
        s = np.zeros((ch.shape[0] + 1, ch.shape[1] + 1), np.int64)
        s[1:, 1:] = ch.cumsum(0).cumsum(1)
        return [_num(v) for v in s.ravel()] + [_num(ch[2:7, 3:10].sum())]
    if op in ("labels", "regions"):
        n, lab = _bfs_labels(a[:, :, 0] != 0, int(P[0]))
        if op == "labels":
            return _f32(lab[:, :, None])
        lines = [str(n)]
        for l in range(n + 1):
            ys, xs = np.nonzero(lab == l)
            if len(xs) == 0:
                lines += ["0", "0", "0", "0", "0", "0.0", "0.0"]
                continue
            lines += [str(len(xs)), str(xs.min()), str(ys.min()), str(xs.max() - xs.min() + 1),
                      str(ys.max() - ys.min() + 1), _num(np.float32(xs.mean())), _num(np.float32(ys.mean()))]
        return lines
    if op == "flood_fill":
        x0, y0 = int(P[0]), int(P[1])
        value = [int(v) for v in P[2:6]]
        tol, conn = int(P[6]), int(P[7])
        c = a.shape[2]
        vs = {1: value[:1], 3: value[:3], 4: value}[c]
        seed = a[y0, x0].copy()
        near = np.all(np.abs(a - seed) <= tol, axis=2)
        n, lab = _bfs_labels(near, conn)
        out = a.copy()
        out[lab == lab[y0, x0]] = vs
        return _u8(out)
    if op == "distance":
        zero = np.argwhere(a[:, :, 0] == 0)
        h, w = a.shape[0], a.shape[1]
        ys, xs = np.mgrid[0:h, 0:w]
        best = np.full((h, w), np.inf)
        for zy, zx in zero:
            best = np.minimum(best, (ys - zy) ** 2 + (xs - zx) ** 2)
        return _f32(np.sqrt(best)[:, :, None])
    if op == "quality":
        x, y = A[0].astype(np.float64), A[1].astype(np.float64)
        mse = float(((x - y) ** 2).mean())
        psnr = 10 * math.log10(255.0 * 255.0 / mse)
        return [_num(mse), _num(psnr), _num(_ssim(x, y))]
    raise ValueError(op)


def vendor() -> None:
    global np, PIL
    import numpy
    import PIL.Image
    import PIL.ImageChops
    import PIL.ImageFilter
    import PIL.ImageOps
    np = numpy
    PIL = sys.modules["PIL"]
    os.makedirs(DATA, exist_ok=True)
    for old in os.listdir(DATA):
        if old.endswith(".gz"):
            os.remove(os.path.join(DATA, old))
    imgs = {name: make() for name, make in INPUTS.items()}
    for (name, op, ins, params, _tol) in CASES:
        out = reference(op, [imgs[n] for n in ins], params)
        data = out.encode() if isinstance(out, Img) else ("\n".join(out) + "\n").encode()
        with open(os.path.join(DATA, name + ".gz"), "wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as fh:
                fh.write(data)


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--vendor":
        vendor()
    else:
        unittest.main()
