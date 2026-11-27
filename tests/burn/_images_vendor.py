"""Makes the image and font corpus of `tests/burn/data/images/` (MYLA-971):
`python3 -m tests.burn.test_images --vendor`.

It needs Pillow and numpy (the tests that read the corpus need neither).
What it makes:

- PNG: PngSuite (2017-07-19, downloaded once and kept in `png/pngsuite/`;
  `--vendor` downloads it again only when that folder is missing), and our
  own files (`png/gen/`): every filter on odd widths at 2, 8 and 16 bits,
  IDAT split into single bytes, empty IDATs, a medium photo-like image, and
  broken ones (bad CRC, cut short, a huge size, an unknown critical chunk,
  a bad filter byte, a bad zlib stream). Their expected pixels come from a
  small PNG decoder below (it keeps 16 bits and `tRNS` exactly, which
  Pillow doesn't), checked against Pillow's own decode of every file.
- JPEG: Pillow (libjpeg-turbo) writes synthetic pictures (a photo-like one,
  gradients, noise, sharp edges, text) at several qualities, 4:4:4, 4:2:2,
  4:2:0, gray, progressive, restart markers, optimised Huffman tables,
  Adobe CMYK, EXIF orientations; ImageMagick (if installed) adds 4:4:0 and
  4:1:1, which Pillow can't write. The expected pixels are Pillow's decode
  (islow IDCT, fancy upsampling: libjpeg's defaults, D313's decision 7).
- GIF: Pillow writes static, transparent, interlaced, tiny-palette and
  animated files (each disposal method, local palettes); the expected
  frames are Pillow's, composited, as RGBA.
- TIFF, BMP, PNM: our own writers below (Pillow can't write 16-bit colour,
  tiles with every compression, planar 2, both byte orders, RLE or
  top-down BMP, ASCII PNM), each file checked against Pillow's decode where
  Pillow reads it.
- QOI: Pillow writes it.
- Fonts: a subset of Liberation Sans (OFL; renamed, as the licence asks of
  a modified version) made with fontTools in a Python that has it
  (MYLA_FONTTOOLS_PYTHON, else this one; skipped, keeping the committed
  font, when none has it), Pillow's renderings of strings with it, and
  FreeType's unhinted ones through freetype-py in that Python (kept as
  committed without it).

Everything is seeded, so a run makes the same files again (as long as
Pillow, libjpeg-turbo, zlib and FreeType give the same bytes).
"""
from __future__ import annotations

import array
import hashlib
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zlib

import numpy as np
from PIL import Image, ImageDraw, ImageFont, features

from tests.burn._images import (DATA, LAYOUTS, MANIFEST, Pixels, _ADAM7, _PNG_CHANNELS, _paeth, from_bytes,
                                png_decode, to_bits, to_layout, write_pam)

PNGSUITE_URL = "http://www.schaik.com/pngsuite/PngSuite-2017jul19.tgz"
PNGSUITE_SHA256 = "0294b244c95a8342c01b00010cf34abdcabc7c6a34fd0fe1bd963917537bfdc8"
# Expected pixels larger than this many bytes keep only their hash.
PAM_LIMIT = 64 * 1024
LIBERATION = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
LIBERATION_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
FONT_NAME = "MylaTestSans"


# -- the entries ------------------------------------------------------------------

class Corpus:
    def __init__(self) -> None:
        self.images: list[dict] = []
        self.fonts: list[dict] = []
        self.renders: list[dict] = []

    def write(self, rel: str, data: bytes) -> str:
        path = os.path.join(DATA, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)
        return rel

    def ok(self, rel: str, fmt: str, source: str, p: Pixels, features=(), notes: str = "", **extra) -> dict:
        e = {"path": rel, "format": fmt, "source": source, "expect": "ok", "features": list(features),
             "width": p.width, "height": p.height, "layout": p.layout, "bits": p.bits, "frames": p.frames,
             "sha256": p.sha256(), "pam": self.pam(rel, p), "notes": notes, **extra}
        self.images.append(e)
        return e

    def pam(self, rel: str, p: Pixels) -> str | None:
        if p.bits == 32 or len(p.raw()) > PAM_LIMIT:
            return None
        pam = "expected/" + os.path.splitext(rel)[0] + ".pam"
        write_pam(os.path.join(DATA, pam), p)
        return pam

    def bad(self, rel: str, fmt: str, source: str, expect: str, notes: str, features=()) -> None:
        assert expect in ("err", "any")
        self.images.append({"path": rel, "format": fmt, "source": source, "expect": expect,
                            "features": list(features), "notes": notes})


def np_pixels(a: np.ndarray, layout: str | None = None, frames: int = 1) -> Pixels:
    """Pixels of an array (h, w) or (h, w, c), or (frames, h, w, c)."""
    if a.ndim == 2:
        a = a[:, :, None]
    if a.ndim == 4:
        h, w, c = a.shape[1:]
    else:
        h, w, c = a.shape
    layout = layout or {1: "gray", 2: "gray+alpha", 3: "rgb", 4: "rgba"}[c]
    bits = {np.dtype("uint8"): 8, np.dtype("uint16"): 16, np.dtype("float32"): 32}[a.dtype]
    big = a.astype(a.dtype.newbyteorder(">")) if bits != 8 else a
    return from_bytes(w, h, layout, bits, np.ascontiguousarray(big).tobytes(), frames)


def pil_pixels(im: Image.Image) -> Pixels:
    """Pillow's decode as std.image would hold it: a palette as rgb (rgba
    with transparency), 1-bit as 0 and 255, 16-bit gray as 16 bits."""
    mode = im.mode
    if mode == "1":
        im = im.convert("L")
    elif mode in ("P", "PA"):
        im = im.convert("RGBA" if mode == "PA" or "transparency" in im.info else "RGB")
    elif mode == "RGBX":
        im = im.convert("RGB")
    elif mode in ("RGBa", "La"):
        im = im.convert("RGBA" if mode == "RGBa" else "LA")
    mode = im.mode
    a = np.asarray(im)
    if mode.startswith("I;16"):
        return np_pixels(a.astype(np.uint16), "gray")
    if mode == "I":
        assert a.min() >= 0 and a.max() <= 65535, "32-bit integers"
        return np_pixels(a.astype(np.uint16), "gray")
    if mode == "F":
        return np_pixels(a.astype(np.float32), "gray")
    layout = {"L": "gray", "LA": "gray+alpha", "RGB": "rgb", "RGBA": "rgba"}[mode]
    return np_pixels(a.astype(np.uint8), layout)


def pillow_reads(data: bytes) -> Pixels | None:
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
        return pil_pixels(im)
    except Exception:
        return None


def same_as_pillow(data: bytes, want: Pixels, what: str) -> str:
    """'same' if Pillow decodes `data` to `want` (16-bit compared on Pillow's
    8 bits, which it truncates), else why not; asserts no other result."""
    got = pillow_reads(data)
    if got is None:
        return "Pillow can't read it"
    if (got.width, got.height) != (want.width, want.height):
        raise AssertionError(f"{what}: Pillow reads {got.width}x{got.height}")
    w, how = want, "same as Pillow's"
    if want.bits == 16 and got.bits == 8:
        w = Pixels(want.width, want.height, want.layout, 8, array.array("B", (v >> 8 for v in want.samples)))
        how = "Pillow reads 8 bits of it, the same high bytes"
        if got.layout == w.layout and got.samples != w.samples:
            w = to_bits(want, 8)
            how = "Pillow reads 8 bits of it, the same rounded"
    if got.layout != w.layout:
        conv = to_layout(w, got.layout)
        if conv is not None:
            w, how = conv, how + f" (Pillow as {got.layout})"
        elif w.layout.endswith("alpha") or w.layout == "rgba":
            # Pillow keeps a gray or RGB tRNS aside, in its info: the colours compared
            c = w.channels - 1
            colours = array.array(w.samples.typecode, (v for i, v in enumerate(w.samples) if i % w.channels < c))
            w = Pixels(w.width, w.height, {"gray+alpha": "gray", "rgba": "rgb"}[w.layout], w.bits, colours)
            how += " (its colours: Pillow keeps tRNS aside)"
    if got.layout != w.layout or got.bits != w.bits or got.samples != w.samples:
        raise AssertionError(f"{what}: Pillow reads {got.layout}/{got.bits} differently")
    return how


# -- test pictures -------------------------------------------------------------------

def photo(w: int, h: int, seed: int) -> np.ndarray:
    """A photo-like RGB picture: a sky gradient, soft blobs, a little noise."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w].astype(np.float64)
    img = np.zeros((h, w, 3))
    img[..., 0] = 90 + 80 * y / max(1, h - 1)
    img[..., 1] = 140 + 50 * y / max(1, h - 1)
    img[..., 2] = 220 - 60 * y / max(1, h - 1)
    for _ in range(7):
        cx, cy = rng.uniform(0, w), rng.uniform(0, h)
        r = rng.uniform(0.08, 0.3) * max(w, h)
        color = rng.uniform(-120, 120, 3)
        g = np.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (2 * r * r))
        img += g[..., None] * color
    img += rng.normal(0, 3, img.shape)
    return np.clip(np.rint(img), 0, 255).astype(np.uint8)


def gradient(w: int, h: int) -> np.ndarray:
    y, x = np.mgrid[0:h, 0:w]
    r = x * 255 // max(1, w - 1)
    g = y * 255 // max(1, h - 1)
    b = (x + y) * 255 // max(1, w + h - 2)
    return np.stack([r, g, b], axis=-1).astype(np.uint8)


def noise(w: int, h: int, seed: int, c: int = 3) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, 256, (h, w, c), dtype=np.uint8)


def edges(w: int, h: int) -> np.ndarray:
    """Sharp edges: a checkerboard, coloured bars and a diagonal."""
    y, x = np.mgrid[0:h, 0:w]
    img = np.where(((x // 4) + (y // 4)) % 2 == 0, 230, 25)[..., None].repeat(3, axis=-1)
    bars = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]
    for i, c in enumerate(bars):
        img[(y >= h // 2) & (x * len(bars) // w == i)] = c
    img[np.abs(x - y) <= 1] = (255, 255, 255)
    return img.astype(np.uint8)


def text_picture(w: int, h: int) -> np.ndarray:
    im = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(im)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
    for i, line in enumerate(["The quick brown", "fox jumps over", "the lazy dog 0123"]):
        d.text((2, 2 + 13 * i), line, fill=(0, 0, 0), font=font)
    return np.asarray(im).copy()


def alpha_of(w: int, h: int) -> np.ndarray:
    y, x = np.mgrid[0:h, 0:w]
    r = np.hypot(x - w / 2, y - h / 2) / (max(w, h) / 2)
    return np.clip(255 * (1.2 - r), 0, 255).astype(np.uint8)


# -- PNG: our own files (the expected pixels from _images.png_decode) ------------------

def png_chunk(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))


def png_encode(rows: list[list[int]], w: int, h: int, ctype: int, depth: int, filters, palette: bytes | None = None,
               trns: bytes | None = None, interlace: bool = False, idat_sizes=None, extra=()) -> bytes:
    """A PNG of `rows` (each the row's raw samples at `depth`), each row's
    filter `filters(pass_index, row_index)`; IDAT split into chunks of
    `idat_sizes` (one chunk without), with `extra` chunks before IDAT."""
    ch = _PNG_CHANNELS[ctype]
    bpp_bits = depth * ch
    bpp = max(1, bpp_bits // 8)
    raw = bytearray()
    for pi, (xs, ys, dx, dy) in enumerate(_ADAM7 if interlace else [(0, 0, 1, 1)]):
        pw, ph = (w - xs + dx - 1) // dx, (h - ys + dy - 1) // dy
        if pw <= 0 or ph <= 0:
            continue
        prev = bytearray((pw * bpp_bits + 7) // 8)
        for r in range(ph):
            src = rows[ys + r * dy]
            samples = [src[(xs + c * dx) * ch + s] for c in range(pw) for s in range(ch)]
            line = bytearray()
            if depth == 16:
                for v in samples:
                    line += struct.pack(">H", v)
            elif depth == 8:
                line += bytes(samples)
            else:
                acc, nbits = 0, 0
                for v in samples:
                    acc, nbits = (acc << depth) | v, nbits + depth
                    if nbits == 8:
                        line.append(acc)
                        acc, nbits = 0, 0
                if nbits:
                    line.append(acc << (8 - nbits))
            f = filters(pi, r)
            out = bytearray(len(line))
            for i in range(len(line)):
                a = line[i - bpp] if i >= bpp else 0
                b, c = prev[i], (prev[i - bpp] if i >= bpp else 0)
                pred = [0, a, b, (a + b) // 2, _paeth(a, b, c)][f]
                out[i] = (line[i] - pred) & 255
            raw.append(f)
            raw += out
            prev = line
    z = zlib.compress(bytes(raw), 9)
    body = b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, depth, ctype, 0, 0, int(interlace)))
    if palette is not None:
        body += png_chunk(b"PLTE", palette)
    if trns is not None:
        body += png_chunk(b"tRNS", trns)
    for kind, data in extra:
        body += png_chunk(kind, data)
    if idat_sizes is None:
        body += png_chunk(b"IDAT", z)
    else:
        at = 0
        for n in idat_sizes:
            body += png_chunk(b"IDAT", z[at:at + n])
            at += n
        body += png_chunk(b"IDAT", z[at:])
    return body + png_chunk(b"IEND", b"")


def make_png(c: Corpus) -> None:
    suite = os.path.join(DATA, "png", "pngsuite")
    if not os.path.isdir(suite):
        with urllib.request.urlopen(PNGSUITE_URL, timeout=60) as r:
            tgz = r.read()
        if hashlib.sha256(tgz).hexdigest() != PNGSUITE_SHA256:
            raise RuntimeError("PngSuite's archive isn't the one expected")
        with tempfile.TemporaryDirectory() as tmp:
            with tarfile.open(fileobj=io.BytesIO(tgz)) as tar:
                tar.extractall(tmp, filter="data")
            os.makedirs(suite)
            for name in sorted(os.listdir(tmp)):
                if name.endswith(".png") or name == "PngSuite.LICENSE":
                    shutil.copyfile(os.path.join(tmp, name), os.path.join(suite, name))
    for name in sorted(os.listdir(suite)):
        if not name.endswith(".png"):
            continue
        rel = f"png/pngsuite/{name}"
        with open(os.path.join(suite, name), "rb") as fh:
            data = fh.read()
        feats = _pngsuite_features(name)
        if name.startswith("x"):
            try:
                png_decode(data)
                raise AssertionError(f"{name} decodes")
            except (ValueError, zlib.error, struct.error):
                pass
            why = _PNGSUITE_BROKEN.get(name[:4], "a broken file")
            if pillow_reads(data) is not None:
                why += " (Pillow reads it anyway: it doesn't check IDAT's CRC)"
            c.bad(rel, "png", "pngsuite", "err", why, feats)
            continue
        p = png_decode(data)
        note = same_as_pillow(data, p, name)
        c.ok(rel, "png", "pngsuite", p, feats, f"PngSuite {name[:-4]}; {note}")
    make_png_own(c)


_PNGSUITE_BROKEN = {
    "xs1n": "signature byte 1 MSBit reset", "xs2n": "signature byte 2 is a 'Q'", "xs4n": "signature byte 4 lowercase",
    "xs7n": "7th byte a space instead of control-Z", "xcrn": "added cr bytes", "xlfn": "added lf bytes",
    "xhdn": "incorrect IHDR checksum", "xc1n": "color type 1", "xc9n": "color type 9", "xd0n": "bit-depth 0",
    "xd3n": "bit-depth 3", "xd9n": "bit-depth 99", "xdtn": "missing IDAT chunk", "xcsn": "incorrect IDAT checksum",
}


def _pngsuite_features(name: str) -> list[str]:
    feats = []
    if len(name) >= 8 and name[3] in "in" and name[4:5].isdigit():
        ctype, bits = int(name[4]), int(name[6:8])
        feats.append({0: "gray", 2: "rgb", 3: "palette", 4: "gray+alpha", 6: "rgba"}.get(ctype, f"ctype{ctype}"))
        feats.append(f"bits{bits}")
        if name[3] == "i":
            feats.append("interlaced")
    prefix = {"bas": "basic", "s0": "size", "s3": "size", "s4": "size", "bg": "background", "tb": "trns",
              "tp": "trns", "tm": "trns", "g0": "gamma", "g1": "gamma", "g2": "gamma", "f0": "filter",
              "f9": "filter", "pp": "palette-hist", "ps": "suggested-palette", "cs": "sbit", "cc": "chroma",
              "cd": "pixel-size", "ch": "hist", "ct": "text", "cm": "time", "ex": "exif", "oi": "idat-split",
              "z0": "zlib-level", "x": "broken"}
    for k, v in prefix.items():
        if name.startswith(k):
            feats.append(v)
            break
    return feats


def make_png_own(c: Corpus) -> None:
    def add(name: str, data: bytes, feats, notes: str) -> None:
        rel = c.write(f"png/gen/{name}", data)
        p = png_decode(data)
        c.ok(rel, "png", "generated", p, feats, f"{notes}; {same_as_pillow(data, p, name)}")

    # every filter, cycled row by row, on odd widths and sub-byte samples
    rng = np.random.default_rng(935)
    g2 = rng.integers(0, 4, (13, 17))
    add("filters-gray2.png", png_encode([list(r) for r in g2], 17, 13, 0, 2, lambda p, r: r % 5),
        ["gray", "bits2", "filter"], "2-bit gray, 17x13, row r filtered with filter r % 5")
    rgb = photo(19, 11, 1)
    add("filters-rgb8.png", png_encode([list(r.reshape(-1)) for r in rgb], 19, 11, 2, 8, lambda p, r: r % 5),
        ["rgb", "bits8", "filter"], "8-bit RGB, 19x11, filters 0 to 4 cycled")
    rgba16 = (photo(9, 10, 2).astype(np.uint16) * 257) ^ rng.integers(0, 256, (10, 9, 3), dtype=np.uint16)
    rgba16 = np.concatenate([rgba16, (alpha_of(9, 10).astype(np.uint16) * 257)[..., None]], axis=-1)
    add("filters-rgba16.png", png_encode([list(r.reshape(-1)) for r in rgba16], 9, 10, 6, 16, lambda p, r: (r + 2) % 5),
        ["rgba", "bits16", "filter"], "16-bit RGBA, 9x10, filters cycled; Pillow keeps only 8 bits of it")
    add("interlaced-filters-rgba16.png",
        png_encode([list(r.reshape(-1)) for r in rgba16], 9, 10, 6, 16, lambda p, r: (p + r) % 5, interlace=True),
        ["rgba", "bits16", "interlaced", "filter"], "Adam7, 16-bit RGBA, each pass's rows filtered differently")
    pal = bytes(photo(1, 7, 3).reshape(-1))
    idx = rng.integers(0, 7, (5, 7))
    add("palette-trns-short.png",
        png_encode([list(r) for r in idx], 7, 5, 3, 4, lambda p, r: 0, palette=pal, trns=bytes([0, 128, 255])),
        ["palette", "bits4", "trns"], "a 7-colour palette, tRNS for the first 3 only (the rest opaque)")
    add("one-pixel.png", png_encode([[200]], 1, 1, 0, 8, lambda p, r: 0), ["gray", "bits8", "size"], "1x1")
    data = png_encode([list(r.reshape(-1)) for r in rgb], 19, 11, 2, 8, lambda p, r: 4,
                      idat_sizes=[1] * 40 + [0, 0, 3])
    add("idat-split.png", data, ["rgb", "bits8", "idat-split"], "IDAT in 1-byte chunks, two empty, then the rest")
    big = photo(512, 384, 4)
    add("photo-512x384.png", png_encode([list(r.reshape(-1)) for r in big], 512, 384, 2, 8, lambda p, r: 4),
        ["rgb", "bits8", "medium"], "a medium photo-like image, Paeth on every row (hash only)")

    # broken files
    good = png_encode([list(r.reshape(-1)) for r in rgb], 19, 11, 2, 8, lambda p, r: 1)

    def broken(name: str, data: bytes, expect: str, notes: str) -> None:
        rel = c.write(f"png/gen/{name}", data)
        if expect == "err":
            try:
                png_decode(data)
                raise AssertionError(f"{name} decodes")
            except (ValueError, zlib.error, struct.error):
                pass
        c.bad(rel, "png", "generated", expect, notes, ["broken"])

    ihdr_end = 8 + 8 + 13 + 4
    idat_at = good.index(b"IDAT") - 4
    broken("bad-crc-idat.png", good[:idat_at + 9] + bytes([good[idat_at + 9] ^ 1]) + good[idat_at + 10:], "err",
           "a byte of IDAT changed: the CRC doesn't match")
    broken("cut-in-idat.png", good[:idat_at + 20], "err", "cut inside IDAT: no IEND")
    broken("no-iend.png", good[:-12], "any", "IEND missing; every pixel is there")
    huge = b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", struct.pack(">IIBBBBB", 65535, 65535, 8, 6, 0, 0, 0)) + good[ihdr_end:]
    broken("huge.png", huge, "err", "IHDR says 65535x65535 RGBA: TooLarge before allocating")
    zero = b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", struct.pack(">IIBBBBB", 0, 11, 8, 2, 0, 0, 0)) + good[ihdr_end:]
    broken("zero-width.png", zero, "err", "width 0")
    crit = good[:ihdr_end] + png_chunk(b"ABCD", b"xyz") + good[ihdr_end:]
    broken("unknown-critical.png", crit, "err", "an unknown critical chunk ABCD: Unsupported")
    anc = good[:ihdr_end] + png_chunk(b"abCd", b"xyz") + good[ihdr_end:]
    rel = c.write("png/gen/unknown-ancillary.png", anc)
    c.ok(rel, "png", "generated", png_decode(anc), ["rgb", "bits8"], "an unknown ancillary chunk abCd, skipped")
    raw = bytearray(zlib.decompress(png_idat(good)))
    raw[0] = 7
    broken("bad-filter.png", png_with_idat(good, zlib.compress(bytes(raw))), "err", "filter type 7 on the first row")
    z = bytearray(png_idat(good))
    z[0] = 0x78 ^ 0x0F
    broken("bad-zlib.png", png_with_idat(good, bytes(z)), "err", "a zlib header that isn't one")
    short = png_with_idat(good, zlib.compress(bytes(zlib.decompress(png_idat(good))[:-30])))
    broken("short-idat.png", short, "err", "the image data stops 30 bytes short of the last row")
    pal_bad = png_encode([[0, 1, 2, 9]], 4, 1, 3, 8, lambda p, r: 0, palette=bytes(9))
    broken("palette-index-out-of-range.png", pal_bad, "any", "index 9 in a 3-colour palette (libpng: black)")


def png_idat(data: bytes) -> bytes:
    out, pos = b"", 8
    while pos < len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        if kind == b"IDAT":
            out += data[pos + 8:pos + 8 + n]
        pos += 12 + n
    return out


def png_with_idat(data: bytes, z: bytes) -> bytes:
    out, pos, done = data[:8], 8, False
    while pos < len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        if kind == b"IDAT":
            if not done:
                out += png_chunk(b"IDAT", z)
                done = True
        else:
            out += data[pos:pos + 12 + n]
        pos += 12 + n
    return out


# -- JPEG -----------------------------------------------------------------------------

def jpeg_markers(data: bytes) -> list[str]:
    """Which coding and options a JPEG file uses, read from its markers."""
    feats, pos = [], 2
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            break
        m = data[pos + 1]
        n = struct.unpack(">H", data[pos + 2:pos + 4])[0]
        if m in (0xC0, 0xC1, 0xC2):
            feats.append({0xC0: "baseline", 0xC1: "extended", 0xC2: "progressive"}[m])
            comps = data[pos + 9]
            factors = [data[pos + 11 + 3 * i] for i in range(comps)]
            if comps == 1:
                feats.append("gray")
            else:
                h, v = factors[0] >> 4, factors[0] & 15
                feats.append({(1, 1): "s444", (2, 1): "s422", (2, 2): "s420", (1, 2): "s440", (4, 1): "s411"}
                             .get((h, v), f"s{h}x{v}"))
                if comps == 4:
                    feats.append("cmyk")
        elif m == 0xDD:
            feats.append("restart")
        elif m == 0xEE:
            feats.append("adobe")
        elif m == 0xE1 and data[pos + 4:pos + 8] == b"Exif":
            feats.append("exif")
        if m == 0xDA:
            break
        pos += 2 + n
    return feats


def make_jpeg(c: Corpus) -> None:
    pics = {"photo": photo(61, 47, 10), "gradient": gradient(48, 32), "noise": noise(24, 16, 11),
            "edges": edges(40, 24), "text": text_picture(96, 44)}

    def add(name: str, im: Image.Image, notes: str, **save) -> bytes:
        b = io.BytesIO()
        im.save(b, "JPEG", **save)
        data = b.getvalue()
        rel = c.write(f"jpeg/{name}", data)
        dec = Image.open(io.BytesIO(data))
        dec.load()
        extra = {}
        orient = dec.getexif().get(0x0112)
        if orient:
            extra["orientation"] = orient
        if dec.mode == "CMYK":
            cmyk = np.asarray(dec).astype(np.uint32)
            rgb = ((255 - cmyk[..., :3]) * (255 - cmyk[..., 3:4]) + 127) // 255
            extra["cmyk_sha256"] = hashlib.sha256(cmyk.astype(np.uint8).tobytes()).hexdigest()
            p = np_pixels(rgb.astype(np.uint8), "rgb")
            notes += ("; expected rgb = round((255 - C) * (255 - K) / 255) from Pillow's CMYK (which undoes Adobe's "
                      "inversion); cmyk_sha256 is Pillow's CMYK samples")
        else:
            p = pil_pixels(dec)
        c.ok(rel, "jpeg", "pillow", p, jpeg_markers(data), notes + "; Pillow's decode (libjpeg-turbo islow, fancy upsampling)",
             **extra)
        return data

    sub = {"s444": "4:4:4", "s422": "4:2:2", "s420": "4:2:0"}
    for q in (50, 75, 95):
        for s, ss in sub.items():
            add(f"photo-q{q}-{s}.jpg", Image.fromarray(pics["photo"]), f"61x47 (partial MCUs), quality {q}, {ss}",
                quality=q, subsampling=ss)
    add("gradient-q90-s444.jpg", Image.fromarray(pics["gradient"]), "smooth gradients", quality=90, subsampling="4:4:4")
    add("noise-q60-s420.jpg", Image.fromarray(pics["noise"]), "noise: every coefficient", quality=60, subsampling="4:2:0")
    add("edges-q85-s422.jpg", Image.fromarray(pics["edges"]), "sharp edges", quality=85, subsampling="4:2:2")
    add("text-q75-s420.jpg", Image.fromarray(pics["text"]), "dark text on white", quality=75, subsampling="4:2:0")
    gray = Image.fromarray(pics["photo"]).convert("L")
    add("gray-q80.jpg", gray, "one component", quality=80)
    add("gray-progressive.jpg", gray, "one component, progressive", quality=80, progressive=True)
    add("progressive-s420.jpg", Image.fromarray(pics["photo"]), "progressive: spectral selection and successive "
        "approximation", quality=85, progressive=True, subsampling="4:2:0")
    add("progressive-s444-optimized.jpg", Image.fromarray(pics["edges"]), "progressive, optimised Huffman tables",
        quality=85, progressive=True, optimize=True, subsampling="4:4:4")
    add("optimized-s420.jpg", Image.fromarray(pics["photo"]), "baseline, optimised Huffman tables", quality=85,
        optimize=True, subsampling="4:2:0")
    add("restart-blocks-s420.jpg", Image.fromarray(pics["photo"]), "a restart marker every MCU", quality=85,
        subsampling="4:2:0", restart_marker_blocks=1)
    add("restart-rows-s444.jpg", Image.fromarray(pics["edges"]), "a restart marker every MCU row", quality=85,
        subsampling="4:4:4", restart_marker_rows=1)
    add("restart-progressive.jpg", Image.fromarray(pics["photo"]), "progressive with restart markers", quality=85,
        progressive=True, subsampling="4:2:0", restart_marker_blocks=3)
    cmyk = Image.fromarray(pics["photo"]).convert("CMYK")
    add("cmyk-adobe.jpg", cmyk, "Adobe CMYK (APP14, inverted samples)", quality=90)
    for o in (3, 6, 8):
        exif = Image.Exif()
        exif[0x0112] = o
        add(f"exif-orientation-{o}.jpg", Image.fromarray(pics["gradient"]), f"EXIF orientation {o}; pixels as stored",
            quality=90, exif=exif.tobytes())
    add("one-pixel.jpg", Image.fromarray(np.array([[[200, 30, 90]]], dtype=np.uint8)), "1x1, 4:2:0", quality=90)
    add("mcu-16x16.jpg", Image.fromarray(photo(16, 16, 12)), "exactly one 4:2:0 MCU", quality=90)
    add("photo-512x384-q85.jpg", Image.fromarray(photo(512, 384, 4)), "a medium photo (hash only)", quality=85)
    add("photo-256x192-q92-s444.jpg", Image.fromarray(photo(256, 192, 13)), "a medium photo, 4:4:4", quality=92,
        subsampling="4:4:4")
    magick = shutil.which("convert")
    for s, factor in (("s440", "1x2"), ("s411", "4x1")):
        rel = f"jpeg/photo-q85-{s}.jpg"
        path = os.path.join(DATA, rel)
        if magick:
            with tempfile.TemporaryDirectory() as tmp:
                src = os.path.join(tmp, "src.png")
                Image.fromarray(pics["photo"]).save(src)
                subprocess.run([magick, src, "-sampling-factor", factor, "-quality", "85", "-strip", path], check=True)
        if os.path.exists(path):
            with open(path, "rb") as fh:
                data = fh.read()
            assert s in jpeg_markers(data), (s, jpeg_markers(data))
            c.ok(rel, "jpeg", "imagemagick", pil_pixels(Image.open(io.BytesIO(data))), jpeg_markers(data),
                 f"{s[1]}:{s[2]}:{s[3]} by ImageMagick (Pillow can't write it); Pillow's decode")

    # broken and unsupported files, made from a good one
    good = open(os.path.join(DATA, "jpeg/photo-q75-s420.jpg"), "rb").read()
    sof = good.index(b"\xff\xc0")
    sos = good.index(b"\xff\xda")

    def broken(name: str, data: bytes, expect: str, notes: str) -> None:
        c.bad(c.write(f"jpeg/{name}", data), "jpeg", "generated", expect, notes, ["broken"])

    broken("not-jpeg.jpg", b"\xff\xd9" + good[2:], "err", "no SOI")
    broken("soi-only.jpg", good[:2], "err", "SOI and nothing else")
    broken("cut-before-sos.jpg", good[:sos], "err", "cut before the scan: no image data")
    broken("cut-in-scan.jpg", good[:sos + (len(good) - sos) // 2], "any",
           "cut halfway through the scan (libjpeg fills the rest and warns)")
    broken("no-eoi.jpg", good[:-2], "any", "EOI missing; all the data is there")
    huge = bytearray(good)
    huge[sof + 5:sof + 9] = struct.pack(">HH", 65535, 65535)
    broken("huge.jpg", bytes(huge), "err", "SOF says 65535x65535: TooLarge before allocating")
    zero = bytearray(good)
    zero[sof + 7:sof + 9] = b"\x00\x00"
    broken("zero-width.jpg", bytes(zero), "err", "width 0")
    for marker, what in ((0xC9, "SOF9: arithmetic coding"), (0xC3, "SOF3: lossless")):
        d = bytearray(good)
        d[sof + 1] = marker
        broken(f"sof{marker - 0xC0}.jpg", bytes(d), "err", f"{what}: Unsupported")
    d = bytearray(good)
    d[sof + 4] = 12
    broken("precision-12.jpg", bytes(d), "err", "12-bit samples in a baseline frame: Unsupported or Corrupt")
    d = bytearray(good)
    dht = good.index(b"\xff\xc4")
    d[dht + 5:dht + 21] = b"\xff" * 16
    broken("bad-huffman-counts.jpg", bytes(d), "err", "a DHT whose code counts overflow its length")


# -- GIF ------------------------------------------------------------------------------

def gif_blocks(data: bytes) -> dict:
    """What a GIF file holds: frames, local palettes, interlaced frames,
    disposals, transparency, the loop extension."""
    info = {"version": data[:6].decode("ascii", "replace"), "frames": 0, "local": 0, "interlaced": 0,
            "disposals": [], "transparent": False, "loop": False}
    flags = data[10]
    pos = 13 + (3 << ((flags & 7) + 1) if flags & 0x80 else 0)
    while pos < len(data):
        b = data[pos]
        if b == 0x3B:
            break
        if b == 0x21:
            label = data[pos + 1]
            if label == 0xF9:
                info["disposals"].append((data[pos + 3] >> 2) & 7)
                info["transparent"] |= bool(data[pos + 3] & 1)
            if label == 0xFF and data[pos + 3:pos + 14] == b"NETSCAPE2.0":
                info["loop"] = True
            pos += 2
            while data[pos]:
                pos += data[pos] + 1
            pos += 1
        elif b == 0x2C:
            info["frames"] += 1
            f = data[pos + 9]
            info["local"] += bool(f & 0x80)
            info["interlaced"] += bool(f & 0x40)
            pos += 10 + (3 << ((f & 7) + 1) if f & 0x80 else 0)
            pos += 1
            while data[pos]:
                pos += data[pos] + 1
            pos += 1
        else:
            raise ValueError("a GIF block")
    return info


def gif_frames(data: bytes) -> Pixels:
    im = Image.open(io.BytesIO(data))
    frames = []
    for i in range(getattr(im, "n_frames", 1)):
        im.seek(i)
        frames.append(np.asarray(im.convert("RGBA")))
    return np_pixels(np.stack(frames), "rgba", len(frames))


def make_gif(c: Corpus) -> None:
    def add(name: str, data: bytes, notes: str) -> None:
        rel = c.write(f"gif/{name}", data)
        info = gif_blocks(data)
        feats = [info["version"]]
        if info["frames"] > 1:
            feats.append("animated")
        if info["local"]:
            feats.append("local-palette")
        if info["interlaced"]:
            feats.append("interlaced")
        if info["transparent"]:
            feats.append("transparent")
        feats += sorted({f"disposal{d}" for d in info["disposals"]})
        p = gif_frames(data)
        c.ok(rel, "gif", "pillow", p, feats, f"{notes}; frames={p.frames}; Pillow's frames as RGBA, composited",
             disposals=info["disposals"])

    def save(frames, **kw) -> bytes:
        b = io.BytesIO()
        frames[0].save(b, "GIF", save_all=len(frames) > 1, append_images=frames[1:], **kw)
        return b.getvalue()

    pic = Image.fromarray(photo(40, 30, 20)).quantize(64, dither=Image.Dither.NONE)
    add("static-64.gif", save([pic]), "one frame, a 64-colour global palette")
    add("interlaced.gif", save([pic], interlace=True), "interlaced rows (4 passes)")
    two = Image.fromarray(edges(13, 7)).convert("1").convert("P")
    add("two-colours-13x7.gif", save([two]), "a 2-colour palette: the smallest LZW code size")
    trans = Image.fromarray(edges(24, 16)).quantize(8, dither=Image.Dither.NONE)
    add("transparent.gif", save([trans], transparency=0), "palette index 0 transparent")
    add("one-pixel.gif", save([Image.new("P", (1, 1), 3)]), "1x1")
    # animations: a moving square over a background, one file a disposal
    base = Image.fromarray(gradient(32, 24)).quantize(32, dither=Image.Dither.NONE)
    for disposal in (0, 1, 2, 3):
        frames = []
        for i in range(4):
            f = base.copy()
            d = ImageDraw.Draw(f)
            d.rectangle([4 + 6 * i, 6, 11 + 6 * i, 15], fill=(i * 7) % 32)
            frames.append(f)
        add(f"animated-disposal{disposal}.gif",
            save(frames, duration=[100, 50, 80, 120], loop=0, disposal=disposal, transparency=31, optimize=False),
            f"4 frames, disposal {disposal}, index 31 transparent, frames cropped to what changed")
    # local palettes: frames quantised on their own
    frames = [Image.fromarray(photo(20, 16, 30 + i)).quantize(16, dither=Image.Dither.NONE) for i in range(3)]
    add("local-palettes.gif", save(frames, duration=70, loop=2), "3 frames, each with its own 16-colour palette")
    # broken
    good = open(os.path.join(DATA, "gif/static-64.gif"), "rb").read()

    def broken(name: str, data: bytes, expect: str, notes: str) -> None:
        c.bad(c.write(f"gif/{name}", data), "gif", "generated", expect, notes, ["broken"])

    broken("not-gif.gif", b"GIF88a" + good[6:], "err", "a signature GIF88a")
    broken("cut-in-header.gif", good[:10], "err", "cut inside the logical screen descriptor")
    broken("cut-in-palette.gif", good[:100], "err", "cut inside the global palette")
    broken("cut-in-data.gif", good[:len(good) * 2 // 3], "any", "cut inside the LZW data (no trailer)")
    huge = bytearray(good)
    huge[6:10] = struct.pack("<HH", 65535, 65535)
    broken("huge-screen.gif", bytes(huge), "any", "a 65535x65535 screen around a 40x30 frame (TooLarge or the frame)")
    d = bytearray(good)
    img = _gif_first_image(good)
    flags = good[img + 9]
    d[img + 10 + (3 << ((flags & 7) + 1) if flags & 0x80 else 0)] = 12
    broken("lzw-code-size-12.gif", bytes(d), "err", "an LZW minimum code size of 12 (GIF allows 2 to 8)")
    frame = bytearray(good)
    frame[img + 5:img + 9] = struct.pack("<HH", 60000, 60000)
    broken("frame-outside-screen.gif", bytes(frame), "any", "a 60000x60000 frame on a 40x30 screen, with 40x30's data")


def _gif_first_image(data: bytes) -> int:
    flags = data[10]
    pos = 13 + (3 << ((flags & 7) + 1) if flags & 0x80 else 0)
    while data[pos] == 0x21:
        pos += 2
        while data[pos]:
            pos += data[pos] + 1
        pos += 1
    assert data[pos] == 0x2C
    return pos


# -- TIFF: a writer --------------------------------------------------------------------

def lzw_tiff(data: bytes) -> bytes:
    """TIFF's LZW (MSB first, 9 to 12 bits, early change), as libtiff writes it."""
    out, acc, nacc = bytearray(), 0, 0

    def put(code: int, nbits: int) -> None:
        nonlocal acc, nacc
        acc, nacc = (acc << nbits) | code, nacc + nbits
        while nacc >= 8:
            nacc -= 8
            out.append((acc >> nacc) & 255)

    nbits, maxcode, free = 9, 511, 258
    table: dict[tuple[int, int], int] = {}
    put(256, nbits)
    if not data:
        put(257, nbits)
    else:
        ent = data[0]
        for ch in data[1:]:
            if (ent, ch) in table:
                ent = table[(ent, ch)]
                continue
            put(ent, nbits)
            table[(ent, ch)] = free
            free += 1
            ent = ch
            if free == 4094:
                put(256, nbits)
                table.clear()
                nbits, maxcode, free = 9, 511, 258
            elif free > maxcode:
                nbits += 1
                maxcode = (1 << nbits) - 1
        put(ent, nbits)
        free += 1
        if free == 4094:
            put(256, nbits)
            nbits = 9
        elif free > maxcode:
            nbits += 1
        put(257, nbits)
    if nacc:
        out.append((acc << (8 - nacc)) & 255)
    return bytes(out)


def packbits(data: bytes) -> bytes:
    out, i = bytearray(), 0
    while i < len(data):
        j = i
        while j + 1 < len(data) and data[j + 1] == data[i] and j - i < 127:
            j += 1
        if j > i:
            out += bytes([257 - (j - i + 1), data[i]])
            i = j + 1
            continue
        j = i
        while j < len(data) and j - i < 128 and not (j + 2 < len(data) and data[j] == data[j + 1] == data[j + 2]):
            j += 1
        out.append(j - i - 1)
        out += data[i:j]
        i = j
    return bytes(out)


def _pack_rows(a: np.ndarray, bits: int, order: str) -> list[bytes]:
    """Each row of `a` (h, w, c) as the bytes TIFF stores: packed MSB first
    below 8 bits, in the byte order `order` above."""
    rows = []
    for row in a:
        flat = row.reshape(-1)
        if bits < 8:
            acc, n, line = 0, 0, bytearray()
            for v in flat:
                acc, n = (acc << bits) | int(v), n + bits
                if n == 8:
                    line.append(acc)
                    acc, n = 0, 0
            if n:
                line.append(acc << (8 - n))
            rows.append(bytes(line))
        else:
            rows.append(flat.astype(flat.dtype.newbyteorder(order)).tobytes())
    return rows


def _predict(row: bytes, bits: int, spp: int, predictor: int, order: str, float_: bool) -> bytes:
    if predictor == 1:
        return row
    if predictor == 2:
        dt = np.dtype({8: "u1", 16: "u2", 32: "u4"}[bits]).newbyteorder(order)
        v = np.frombuffer(row, dt).astype(np.int64)
        d = v.copy()
        d[spp:] = v[spp:] - v[:-spp]
        return (d % (1 << bits)).astype(dt).tobytes()
    # 3: floating point: bytes split into planes, most significant first, then differenced
    assert float_ and bits == 32
    v = np.frombuffer(row, np.dtype(">f4" if order == ">" else "<f4")).astype(">f4")
    be = np.frombuffer(v.tobytes(), np.uint8).reshape(-1, 4)
    planes = be.T.reshape(-1).astype(np.int64)
    d = planes.copy()
    d[spp:] = planes[spp:] - planes[:-spp]
    return (d % 256).astype(np.uint8).tobytes()


def tiff_encode(pages: list[dict], order: str = "<") -> bytes:
    """A TIFF of `pages`, each a dict: `a` (h, w, c), `bits`, `photometric`,
    `compression` (1, 5, 8, 32946, 32773), `predictor`, `rows` (rows a strip)
    or `tile` (w, h), `planar` (1, 2), `extra` (ExtraSamples), `colormap`
    (a list of 16-bit r, g, b triples), `float`."""
    out = bytearray(b"II*\x00" if order == "<" else b"MM\x00*")
    out += b"\x00\x00\x00\x00"
    ifd_slots = [4]
    for page in pages:
        a = page["a"]
        if a.ndim == 2:
            a = a[:, :, None]
        h, w, spp = a.shape
        bits, comp, pred = page["bits"], page.get("compression", 1), page.get("predictor", 1)
        planar = page.get("planar", 1)
        planes = [a] if planar == 1 else [a[:, :, i:i + 1] for i in range(spp)]
        pspp = spp if planar == 1 else 1
        blocks = []
        tile = page.get("tile")
        for plane in planes:
            if tile:
                tw, th = tile
                for ty in range(0, h, th):
                    for tx in range(0, w, tw):
                        t = np.zeros((th, tw, pspp), a.dtype)
                        part = plane[ty:ty + th, tx:tx + tw]
                        t[:part.shape[0], :part.shape[1]] = part
                        blocks.append(_pack_rows(t, bits, order))
            else:
                rps = page.get("rows", h)
                for y in range(0, h, rps):
                    blocks.append(_pack_rows(plane[y:y + rps], bits, order))
        offsets, counts = [], []
        for rows in blocks:
            predicted = [_predict(r, bits, pspp, pred, order, page.get("float", False)) for r in rows]
            raw = b"".join(predicted)
            if comp == 32773:
                data = b"".join(packbits(r) for r in predicted)   # each row on its own, as libtiff does
            else:
                data = {1: lambda r: r, 5: lzw_tiff, 8: zlib.compress, 32946: zlib.compress}[comp](raw)
            if len(out) % 2:
                out.append(0)
            offsets.append(len(out))
            counts.append(len(data))
            out += data
        tags = {256: (4, [w]), 257: (4, [h]), 258: (3, [bits] * spp), 259: (3, [comp]),
                262: (3, [page["photometric"]]), 277: (3, [spp]), 284: (3, [planar])}
        if tile:
            tags.update({322: (3, [tile[0]]), 323: (3, [tile[1]]), 324: (4, offsets), 325: (4, counts)})
        else:
            tags.update({273: (4, offsets), 278: (4, [page.get("rows", h)]), 279: (4, counts)})
        if pred != 1:
            tags[317] = (3, [pred])
        if "extra" in page:
            tags[338] = (3, [page["extra"]])
        if "colormap" in page:
            cm = page["colormap"]
            tags[320] = (3, [t[0] for t in cm] + [t[1] for t in cm] + [t[2] for t in cm])
        if page.get("float"):
            tags[339] = (3, [3] * spp)
        if len(out) % 2:
            out.append(0)
        ifd = len(out)
        struct.pack_into(order + "I", out, ifd_slots[-1], ifd)
        entries, values = bytearray(), bytearray()
        values_at = ifd + 2 + 12 * len(tags) + 4
        for tag in sorted(tags):
            typ, vals = tags[tag]
            fmt = {3: "H", 4: "I"}[typ]
            packed = struct.pack(order + fmt * len(vals), *vals)
            if len(packed) <= 4:
                entries += struct.pack(order + "HHI", tag, typ, len(vals)) + packed.ljust(4, b"\x00")
            else:
                entries += struct.pack(order + "HHII", tag, typ, len(vals), values_at + len(values))
                values += packed
                if len(values) % 2:
                    values.append(0)
        out += struct.pack(order + "H", len(tags)) + entries
        ifd_slots.append(len(out))
        out += b"\x00\x00\x00\x00" + values
    return bytes(out)


def make_tiff(c: Corpus) -> None:
    def add(name: str, pages: list[dict], order: str, notes: str, feats=(), want: Pixels | None = None) -> None:
        data = tiff_encode(pages, order)
        rel = c.write(f"tiff/{name}", data)
        page = pages[0]
        p = want or page["want"]
        names = {1: "none", 5: "lzw", 8: "deflate", 32946: "deflate-old", 32773: "packbits"}
        f = [names[page.get("compression", 1)], "big-endian" if order == ">" else "little-endian",
             "tiles" if "tile" in page else "strips", f"bits{page['bits']}", *feats]
        if page.get("predictor", 1) != 1:
            f.append(f"predictor{page['predictor']}")
        if page.get("planar", 1) == 2:
            f.append("planar2")
        extra = {}
        if len(pages) > 1:
            f.append("multipage")
            extra["pages"] = [{"width": q["want"].width, "height": q["want"].height, "layout": q["want"].layout,
                               "bits": q["want"].bits, "sha256": q["want"].sha256(),
                               "pam": c.pam(f"tiff/{os.path.splitext(name)[0]}-page{i + 1}.tif", q["want"])}
                              for i, q in enumerate(pages[1:])]
        note = same_as_pillow(data, p, name) if p.bits != 32 else _float_check(data, p)
        c.ok(rel, "tiff", "generated", p, f, f"{notes}; {note}", **extra)

    rgb = photo(37, 23, 40)
    gray = rgb[..., 1].copy()
    rgba = np.concatenate([rgb, alpha_of(37, 23)[..., None]], axis=-1)
    g16 = (gray.astype(np.uint16) * 257) ^ np.random.default_rng(41).integers(0, 256, gray.shape, dtype=np.uint16)
    rgb16 = (rgb.astype(np.uint16) * 257) ^ np.random.default_rng(42).integers(0, 256, rgb.shape, dtype=np.uint16)
    P = np_pixels
    for comp, cname in ((1, "none"), (5, "lzw"), (8, "deflate"), (32773, "packbits")):
        add(f"gray8-{cname}.tif", [dict(a=gray, bits=8, photometric=1, compression=comp, rows=5, want=P(gray))], "<",
            f"8-bit gray, strips of 5 rows, {cname}", ["gray"])
        add(f"rgb8-{cname}-mm.tif", [dict(a=rgb, bits=8, photometric=2, compression=comp, rows=7, want=P(rgb))], ">",
            f"8-bit RGB, big endian, strips of 7 rows, {cname}", ["rgb"])
    add("rgb8-lzw-predictor.tif", [dict(a=rgb, bits=8, photometric=2, compression=5, predictor=2, rows=8, want=P(rgb))],
        "<", "LZW with the horizontal predictor", ["rgb"])
    add("rgb8-deflate-old.tif", [dict(a=rgb, bits=8, photometric=2, compression=32946, want=P(rgb))], "<",
        "the old Deflate code 32946, one strip", ["rgb"])
    add("rgba8-lzw.tif", [dict(a=rgba, bits=8, photometric=2, compression=5, extra=2, rows=6, want=P(rgba))], "<",
        "RGBA, ExtraSamples 2 (unassociated alpha)", ["rgba"])
    add("rgb8-tiles-lzw.tif", [dict(a=rgb, bits=8, photometric=2, compression=5, tile=(16, 16), want=P(rgb))], "<",
        "16x16 tiles over 37x23 (partial tiles padded)", ["rgb"])
    add("rgb8-tiles-deflate-mm.tif", [dict(a=rgb, bits=8, photometric=2, compression=8, predictor=2, tile=(16, 32),
                                           want=P(rgb))], ">", "16x32 tiles, Deflate, predictor, big endian", ["rgb"])
    add("rgb8-planar.tif", [dict(a=rgb, bits=8, photometric=2, planar=2, rows=8, want=P(rgb))], "<",
        "planar configuration 2: a plane per channel", ["rgb"])
    add("rgb8-planar-lzw-mm.tif", [dict(a=rgb, bits=8, photometric=2, planar=2, compression=5, predictor=2, rows=12,
                                        want=P(rgb))], ">", "planar 2, LZW, predictor, big endian", ["rgb"])
    for order, oname in (("<", "ii"), (">", "mm")):
        add(f"gray16-{oname}.tif", [dict(a=g16, bits=16, photometric=1, rows=6, want=P(g16))], order,
            f"16-bit gray, {'little' if order == '<' else 'big'} endian", ["gray"])
        add(f"gray16-lzw-predictor-{oname}.tif", [dict(a=g16, bits=16, photometric=1, compression=5, predictor=2,
                                                       want=P(g16))], order, "16-bit gray, LZW, predictor", ["gray"])
        add(f"rgb16-deflate-{oname}.tif", [dict(a=rgb16, bits=16, photometric=2, compression=8, predictor=2, rows=4,
                                                want=P(rgb16))], order, "16-bit RGB, Deflate, predictor", ["rgb"])
    bilevel = (edges(29, 9)[..., 0] > 128).astype(np.uint8)
    add("bilevel-blackiszero.tif", [dict(a=bilevel, bits=1, photometric=1, want=P(bilevel * 255))], "<",
        "1 bit, BlackIsZero, 29 wide (rows padded to a byte)", ["gray", "bilevel"])
    add("bilevel-whiteiszero-packbits.tif", [dict(a=bilevel, bits=1, photometric=0, compression=32773,
                                                  want=P((1 - bilevel) * 255))], "<",
        "1 bit, WhiteIsZero (0 is white), PackBits", ["gray", "bilevel"])
    g4 = (gray >> 4).astype(np.uint8)
    add("gray4.tif", [dict(a=g4, bits=4, photometric=1, want=P(g4 * 17))], "<", "4-bit gray, scaled to 8", ["gray"])
    pal = [(int(r) * 257, int(g) * 257, int(b) * 257) for r, g, b in photo(1, 256, 43).reshape(-1, 3)]
    idx = np.random.default_rng(44).integers(0, 256, (11, 21), dtype=np.uint8)
    cm8 = np.array([[t[0] >> 8, t[1] >> 8, t[2] >> 8] for t in pal], np.uint8)
    add("palette8-lzw.tif", [dict(a=idx, bits=8, photometric=3, compression=5, colormap=pal, want=P(cm8[idx]))], "<",
        "an 8-bit palette (ColorMap 16-bit entries, here v * 257)", ["palette"])
    idx4 = (idx & 15)
    add("palette4-mm.tif", [dict(a=idx4, bits=4, photometric=3, colormap=pal[:16], want=P(cm8[:16][idx4]))], ">",
        "a 4-bit palette, big endian", ["palette"])
    fl = (np.random.default_rng(45).standard_normal((9, 13)) * 0.25 + 0.5).astype(np.float32)
    add("float32.tif", [dict(a=fl, bits=32, photometric=1, float=True, want=P(fl))], "<",
        "float32 gray, SampleFormat 3 (hash only)", ["gray", "float"])
    add("float32-deflate-predictor3-mm.tif", [dict(a=fl, bits=32, photometric=1, float=True, compression=8, predictor=3,
                                                   want=P(fl))], ">", "float32 gray, Deflate, predictor 3", ["gray", "float"])
    pages = [dict(a=rgb, bits=8, photometric=2, compression=5, want=P(rgb)),
             dict(a=gray[:10, :20].copy(), bits=8, photometric=1, want=P(gray[:10, :20].copy())),
             dict(a=g16[:5, :7].copy(), bits=16, photometric=1, compression=8, want=P(g16[:5, :7].copy()))]
    add("multipage.tif", pages, "<", "3 pages: 37x23 RGB, 20x10 gray, 7x5 16-bit gray; the expected pixels are "
        "page 0's, `pages` the others'")
    # broken and unsupported
    good = tiff_encode([dict(a=rgb, bits=8, photometric=2, compression=5, rows=8)], "<")

    def broken(name: str, data: bytes, expect: str, notes: str) -> None:
        c.bad(c.write(f"tiff/{name}", data), "tiff", "generated", expect, notes, ["broken"])

    ifd = struct.unpack("<I", good[4:8])[0]
    broken("bad-byte-order.tif", b"IM" + good[2:], "err", "byte order IM")
    broken("bad-magic.tif", good[:2] + b"\x2b\x00" + good[4:], "err", "magic 43 (BigTIFF): Unsupported")
    broken("ifd-out-of-range.tif", good[:4] + struct.pack("<I", len(good) + 100) + good[8:], "err",
           "the first IFD past the end")
    broken("cut-in-ifd.tif", good[:ifd + 30], "err", "cut inside the IFD")
    broken("cut-in-strips.tif", good[:40], "err", "cut inside the strips (the IFD is after them)")
    for comp, what in ((7, "JPEG"), (3, "CCITT G3"), (4, "CCITT G4"), (99, "compression 99")):
        broken(f"compression-{comp}.tif", _tiff_set(good, 259, comp), "err", f"{what}: Unsupported")
    broken("photometric-cmyk.tif", _tiff_set(good, 262, 5), "err", "photometric 5 (CMYK): Unsupported at first")
    loop = bytearray(good)
    n = struct.unpack("<H", good[ifd:ifd + 2])[0]
    struct.pack_into("<I", loop, ifd + 2 + 12 * n, ifd)
    broken("ifd-loop.tif", bytes(loop), "any", "the IFD's next pointer is itself: page 0 reads, pages() must stop")
    broken("huge.tif", _tiff_set(_tiff_set(good, 256, 65535, 4), 257, 65535, 4), "err",
           "65535x65535 with one small strip: TooLarge before allocating")


def _tiff_set(data: bytes, tag: int, value: int, typ: int | None = None) -> bytes:
    """`data` (little endian) with the first IFD's `tag` set to `value`."""
    d = bytearray(data)
    ifd = struct.unpack("<I", d[4:8])[0]
    for i in range(struct.unpack("<H", d[ifd:ifd + 2])[0]):
        at = ifd + 2 + 12 * i
        t, ty, count = struct.unpack("<HHI", d[at:at + 8])
        if t == tag:
            ty = typ or ty
            struct.pack_into("<HHI", d, at, t, ty, 1)
            d[at + 8:at + 12] = struct.pack("<H" if ty == 3 else "<I", value).ljust(4, b"\x00")
            return bytes(d)
    raise KeyError(tag)


def _float_check(data: bytes, want: Pixels) -> str:
    got = pillow_reads(data)
    if got is None:
        return "Pillow can't read it"
    if got.bits == 32 and got.raw() == want.raw():
        return "same as Pillow's"
    # Pillow 13 swaps the bytes of a big-endian file's floats after libtiff's
    # predictor 3 has made them native: ImageMagick (libtiff) is the check there
    magick = shutil.which("convert")
    if magick:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "f.tif")
            with open(path, "wb") as fh:
                fh.write(data)
            out = subprocess.run([magick, path, "-define", "quantum:format=floating-point", "-depth", "32",
                                  "-endian", "MSB", "gray:-"], capture_output=True, check=True).stdout
        a = np.frombuffer(out, ">f4")
        b = np.frombuffer(want.raw(), ">f4")
        inside = (b >= 0) & (b <= 1)   # ImageMagick clamps to 0..1
        if a.shape == b.shape and inside.sum() > b.size // 2 and np.allclose(a[inside], b[inside], atol=1e-4):
            return ("Pillow misreads it (it swaps the bytes libtiff's predictor made native); libtiff through "
                    "ImageMagick reads the samples written (within its 16-bit quantum)")
    raise AssertionError("Pillow reads the floats differently")


# -- BMP: a writer -------------------------------------------------------------------

def bmp_encode(a: np.ndarray, bpp: int, palette: np.ndarray | None = None, rle: int = 0, top_down: bool = False,
               bitfields: tuple | None = None, v5: bool = False) -> bytes:
    """A BMP of `a` (indices (h, w) for bpp <= 8, else (h, w, 3 or 4) RGB(A))."""
    h, w = a.shape[:2]
    rows = []
    for y in (range(h) if top_down else range(h - 1, -1, -1)):
        r = a[y]
        if bpp <= 8:
            line = bytearray()
            if rle:
                rows.append(_rle_row(list(int(v) for v in r), rle))
                continue
            acc, n = 0, 0
            for v in r:
                acc, n = (acc << bpp) | int(v), n + bpp
                if n == 8:
                    line.append(acc)
                    acc, n = 0, 0
            if n:
                line.append(acc << (8 - n))
        elif bpp == 24:
            line = bytearray(r[:, ::-1].astype(np.uint8).tobytes())
        elif bpp == 32:
            if bitfields:
                line = bytearray(np.stack([r[:, 2], r[:, 1], r[:, 0], r[:, 3]], -1).astype(np.uint8).tobytes())
            else:
                line = bytearray(np.stack([r[:, 2], r[:, 1], r[:, 0], np.zeros(w, np.uint8)], -1).tobytes())
        else:  # 16: 5-5-5, or 5-6-5 with bitfields
            if bitfields:
                v = ((r[:, 0].astype(np.uint16) >> 3) << 11) | ((r[:, 1].astype(np.uint16) >> 2) << 5) | (r[:, 2] >> 3)
            else:
                v = ((r[:, 0].astype(np.uint16) >> 3) << 10) | ((r[:, 1].astype(np.uint16) >> 3) << 5) | (r[:, 2] >> 3)
            line = bytearray(v.astype("<u2").tobytes())
        while len(line) % 4:
            line.append(0)
        rows.append(bytes(line))
    pixels = b"".join(rows)
    if rle:
        pixels += b"\x00\x01"
    header_size = 124 if v5 else (108 if bitfields and bpp == 32 else 40)
    ncolors = 0 if palette is None else len(palette)
    pal = b"" if palette is None else b"".join(bytes([int(b), int(g), int(r), 0]) for r, g, b in palette)
    masks = b""
    if bitfields and header_size == 40:
        masks = struct.pack("<III", *bitfields[:3])
    offset = 14 + header_size + len(masks) + len(pal)
    comp = {8: 1, 4: 2}[bpp] if rle else (3 if bitfields else 0)
    info = struct.pack("<IiiHHIIiiII", header_size, w, -h if top_down else h, 1, bpp, comp, len(pixels), 2835, 2835,
                       ncolors, 0)
    if header_size > 40:
        info += struct.pack("<IIII", *bitfields) + b"BGRs" + bytes(36) + bytes(12)
        if header_size == 124:
            info += struct.pack("<IIII", 4, 0, 0, 0)
    out = b"BM" + struct.pack("<IHHI", offset + len(pixels), 0, 0, offset) + info + masks + pal + pixels
    return out


def _rle_row(r: list[int], rle: int) -> bytes:
    """A row in RLE8 (rle 8) or RLE4 (rle 4): runs of equal pixels encoded,
    other stretches absolute, the end of line marker after."""
    out, i, n = bytearray(), 0, len(r)
    while i < n:
        j = i
        while j + 1 < n and r[j + 1] == r[i] and j - i < 254:
            j += 1
        if j - i + 1 >= 3 or n - i < 3:
            count = j - i + 1
            out += bytes([count, r[i] if rle == 8 else (r[i] << 4) | r[i]])
            i = j + 1
            continue
        j = i
        while j < n and j - i < 254 and not (j + 2 < n and r[j] == r[j + 1] == r[j + 2]):
            j += 1
        count = j - i
        if count < 3:
            for v in r[i:j]:
                out += bytes([1, v if rle == 8 else (v << 4)])
        else:
            out += bytes([0, count])
            vals = r[i:j]
            if rle == 8:
                data = bytes(vals)
            else:
                vals = vals + [0] * (len(vals) % 2)
                data = bytes((vals[k] << 4) | vals[k + 1] for k in range(0, len(vals), 2))
            out += data + (b"\x00" if len(data) % 2 else b"")
        i = j
    return bytes(out + b"\x00\x00")


def make_bmp(c: Corpus) -> None:
    def add(name: str, data: bytes, notes: str, feats, want: Pixels | None = None) -> None:
        rel = c.write(f"bmp/{name}", data)
        p = want or pillow_reads(data)
        note = same_as_pillow(data, p, name)
        c.ok(rel, "bmp", "generated", p, feats, f"{notes}; {note}")

    rng = np.random.default_rng(60)
    rgb = photo(21, 13, 61)
    pal256 = photo(1, 256, 62).reshape(-1, 3)
    idx = rng.integers(0, 256, (13, 21), dtype=np.uint8)
    for bpp, w in ((1, 37), (4, 23), (8, 21)):
        n = 1 << bpp
        ix = ((idx[:, :w] if w <= 21 else rng.integers(0, 256, (13, w), dtype=np.uint8)).astype(np.int64) % n).astype(np.uint8)
        add(f"pal{bpp}-{w}x13.bmp", bmp_encode(ix, bpp, pal256[:n]), f"{bpp}-bit palette, {w} wide (padded rows)",
            ["palette", f"bits{bpp}"], np_pixels(pal256[:n][ix]))
    add("rgb24.bmp", bmp_encode(rgb, 24), "24-bit, bottom-up, 21 wide (rows padded)", ["rgb", "bits24"], np_pixels(rgb))
    add("rgb24-top-down.bmp", bmp_encode(rgb, 24, top_down=True), "24-bit, top-down (negative height)",
        ["rgb", "bits24", "top-down"], np_pixels(rgb))
    rgba = np.concatenate([rgb, alpha_of(21, 13)[..., None]], axis=-1)
    add("rgb32.bmp", bmp_encode(rgba, 32), "32-bit BI_RGB: the 4th byte unused (0), so no alpha",
        ["rgb", "bits32"], np_pixels(rgb))
    add("rgba32-bitfields-v4.bmp", bmp_encode(rgba, 32, bitfields=(0xFF0000, 0xFF00, 0xFF, 0xFF000000)),
        "32-bit BI_BITFIELDS with an alpha mask, BITMAPV4HEADER", ["rgba", "bits32", "bitfields"], np_pixels(rgba))
    add("rgba32-bitfields-v5.bmp", bmp_encode(rgba, 32, bitfields=(0xFF0000, 0xFF00, 0xFF, 0xFF000000), v5=True),
        "32-bit BI_BITFIELDS with an alpha mask, BITMAPV5HEADER", ["rgba", "bits32", "bitfields"], np_pixels(rgba))
    add("rgb16-555.bmp", bmp_encode(rgb, 16), "16-bit BI_RGB, 5-5-5; Pillow's scaling of 5 bits to 8",
        ["rgb", "bits16"])
    add("rgb16-565.bmp", bmp_encode(rgb, 16, bitfields=(0xF800, 0x7E0, 0x1F)), "16-bit BI_BITFIELDS 5-6-5",
        ["rgb", "bits16", "bitfields"])
    runs = np.repeat(rng.integers(0, 16, (9, 6), dtype=np.uint8), [5, 1, 2, 7, 3, 1], axis=1)
    add("rle8.bmp", bmp_encode(runs, 8, pal256, rle=8), "RLE8: runs and absolute stretches", ["palette", "rle8"],
        np_pixels(pal256[runs]))
    add("rle4.bmp", bmp_encode(runs, 4, pal256[:16], rle=4), "RLE4: runs and absolute stretches", ["palette", "rle4"],
        np_pixels(pal256[:16][runs]))
    good = bmp_encode(rgb, 24)

    def broken(name: str, data: bytes, expect: str, notes: str) -> None:
        c.bad(c.write(f"bmp/{name}", data), "bmp", "generated", expect, notes, ["broken"])

    broken("not-bmp.bmp", b"MB" + good[2:], "err", "signature MB")
    broken("cut-in-header.bmp", good[:30], "err", "cut inside BITMAPINFOHEADER")
    broken("cut-in-pixels.bmp", good[:len(good) // 2], "any", "half the rows")
    broken("offset-past-end.bmp", good[:10] + struct.pack("<I", len(good) + 10) + good[14:], "err",
           "the pixel offset past the end")
    huge = bytearray(good)
    huge[18:26] = struct.pack("<ii", 100000, 100000)
    broken("huge.bmp", bytes(huge), "err", "100000x100000: TooLarge before allocating")
    bad_bpp = bytearray(good)
    bad_bpp[28:30] = struct.pack("<H", 7)
    broken("bpp-7.bmp", bytes(bad_bpp), "err", "7 bits a pixel")
    rle = bytearray(bmp_encode(runs, 8, pal256, rle=8))
    off = struct.unpack("<I", rle[10:14])[0]
    rle[off] = 250
    broken("rle8-overrun.bmp", bytes(rle), "any", "an RLE8 run of 250 in a row of 19 pixels")


# -- PNM -----------------------------------------------------------------------------

def make_pnm(c: Corpus) -> None:
    def add(name: str, data: bytes, want: Pixels, notes: str, feats) -> None:
        rel = c.write(f"pnm/{name}", data)
        c.ok(rel, "pnm", "generated", want, feats, f"{notes}; {same_as_pillow(data, want, name)}")

    rgb = photo(11, 7, 70)
    gray = rgb[..., 0].copy()
    bits = (edges(13, 5)[..., 0] > 128).astype(np.uint8)
    rng = np.random.default_rng(71)
    g16 = (gray.astype(np.uint16) * 257) ^ rng.integers(0, 256, gray.shape, dtype=np.uint16)
    rgb16 = (rgb.astype(np.uint16) * 257) ^ rng.integers(0, 256, rgb.shape, dtype=np.uint16)

    def ascii_rows(a, per_line=12) -> bytes:
        vals = [str(int(v)) for v in a.reshape(-1)]
        return ("\n".join(" ".join(vals[i:i + per_line]) for i in range(0, len(vals), per_line)) + "\n").encode()

    # PBM: 1 is black
    add("p1-ascii.pbm", b"P1\n# a comment\n13 5\n" + ascii_rows(1 - bits, 13), np_pixels(bits * 255),
        "P1, a comment in the header (1 is black)", ["pbm", "ascii"])
    packed = b"".join(bytes(np.packbits(1 - r)) for r in bits)
    add("p4-binary.pbm", b"P4\n13 5\n" + packed, np_pixels(bits * 255), "P4, 13 wide (rows padded to a byte)",
        ["pbm", "binary"])
    add("p2-ascii.pgm", b"P2\n11 7\n255\n" + ascii_rows(gray), np_pixels(gray), "P2", ["pgm", "ascii"])
    g15 = (gray >> 4).astype(np.uint8)
    add("p2-maxval15.pgm", b"P2\n11 7\n15\n" + ascii_rows(g15), np_pixels((g15.astype(np.uint16) * 17).astype(np.uint8)),
        "P2 with MAXVAL 15: scaled to 0..255 (v * 255 / 15)", ["pgm", "ascii", "maxval"])
    add("p5-binary.pgm", b"P5\n11 7\n255\n" + gray.tobytes(), np_pixels(gray), "P5", ["pgm", "binary"])
    add("p5-16bit.pgm", b"P5\n11 7\n65535\n" + g16.astype(">u2").tobytes(), np_pixels(g16),
        "P5, 16 bits big endian", ["pgm", "binary", "bits16"])
    m1000 = (gray.astype(np.uint32) * 1000 // 255).astype(np.uint16)
    add("p5-maxval1000.pgm", b"P5\n11 7\n1000\n" + m1000.astype(">u2").tobytes(),
        np_pixels(((m1000.astype(np.uint32) * 65535 + 500) // 1000).astype(np.uint16)),
        "P5 with MAXVAL 1000: two bytes a sample, scaled to 16 bits (round(v * 65535 / 1000))", ["pgm", "binary", "maxval"])
    add("p3-ascii.ppm", b"P3\n11 7 255\n" + ascii_rows(rgb), np_pixels(rgb), "P3, the header on one line", ["ppm", "ascii"])
    add("p6-binary.ppm", b"P6\n11\n7\n255\n" + rgb.tobytes(), np_pixels(rgb), "P6, a field a line", ["ppm", "binary"])
    add("p6-16bit.ppm", b"P6\n11 7\n65535\n" + rgb16.astype(">u2").tobytes(), np_pixels(rgb16), "P6, 16 bits",
        ["ppm", "binary", "bits16"])
    rgba = np.concatenate([rgb, alpha_of(11, 7)[..., None]], axis=-1)
    for layout, arr in (("gray", gray), ("gray+alpha", np.stack([gray, alpha_of(11, 7)], -1)), ("rgb", rgb),
                        ("rgba", rgba)):
        p = np_pixels(arr, layout)
        name = {"gray": "gray", "gray+alpha": "gray-alpha", "rgb": "rgb", "rgba": "rgba"}[layout]
        data = (f"P7\nWIDTH 11\nHEIGHT 7\nDEPTH {p.channels}\nMAXVAL 255\nTUPLTYPE {LAYOUTS[layout][1]}\nENDHDR\n").encode()
        add(f"pam-{name}.pam", data + p.raw(), p, f"PAM, TUPLTYPE {LAYOUTS[layout][1]}", ["pam"])
    p = np_pixels(rgb16)
    add("pam-rgb16.pam", b"P7\n# a comment\nWIDTH 11\nHEIGHT 7\nDEPTH 3\nMAXVAL 65535\nTUPLTYPE RGB\nENDHDR\n" + p.raw(),
        p, "PAM, 16 bits, a comment", ["pam", "bits16"])

    def broken(name: str, data: bytes, expect: str, notes: str) -> None:
        c.bad(c.write(f"pnm/{name}", data), "pnm", "generated", expect, notes, ["broken"])

    broken("not-pnm.ppm", b"P9\n11 7\n255\n" + rgb.tobytes(), "err", "magic P9")
    broken("cut-samples.ppm", b"P6\n11 7\n255\n" + rgb.tobytes()[:100], "err", "the samples cut short")
    broken("maxval-0.pgm", b"P5\n11 7\n0\n" + gray.tobytes(), "err", "MAXVAL 0")
    broken("maxval-70000.pgm", b"P5\n11 7\n70000\n" + gray.tobytes() * 2, "err", "MAXVAL past 65535")
    broken("huge.pgm", b"P5\n100000 100000\n255\n" + gray.tobytes(), "err", "100000x100000: TooLarge before allocating")
    broken("ascii-bad-number.pgm", b"P2\n2 1\n255\n12 x\n", "err", "a sample that isn't a number")
    broken("ascii-over-maxval.pgm", b"P2\n2 1\n15\n12 16\n", "err", "a sample above MAXVAL")
    broken("pam-depth-mismatch.pam", b"P7\nWIDTH 2\nHEIGHT 1\nDEPTH 2\nMAXVAL 255\nTUPLTYPE RGB\nENDHDR\nabcd", "err",
           "TUPLTYPE RGB with DEPTH 2")


# -- QOI -----------------------------------------------------------------------------

def make_qoi(c: Corpus) -> None:
    def add(name: str, a: np.ndarray, notes: str) -> None:
        b = io.BytesIO()
        Image.fromarray(a).save(b, "QOI")
        data = b.getvalue()
        rel = c.write(f"qoi/{name}", data)
        p = np_pixels(a)
        c.ok(rel, "qoi", "pillow", p, [p.layout], f"{notes}; written by Pillow; {same_as_pillow(data, p, name)}")

    rgb = photo(23, 17, 80)
    add("photo-rgb.qoi", rgb, "RGB, 3 channels")
    add("photo-rgba.qoi", np.concatenate([rgb, alpha_of(23, 17)[..., None]], axis=-1), "RGBA: alpha changes")
    add("edges-rgb.qoi", edges(40, 24), "runs and the index")
    add("noise-rgba.qoi", noise(9, 7, 81, 4), "noise: QOI_OP_RGBA everywhere")
    good = open(os.path.join(DATA, "qoi/photo-rgb.qoi"), "rb").read()

    def broken(name: str, data: bytes, expect: str, notes: str) -> None:
        c.bad(c.write(f"qoi/{name}", data), "qoi", "generated", expect, notes, ["broken"])

    broken("not-qoi.qoi", b"qoig" + good[4:], "err", "magic qoig")
    broken("cut-in-header.qoi", good[:9], "err", "cut inside the 14-byte header")
    broken("cut-in-data.qoi", good[:len(good) // 2], "any", "half the data, no end marker")
    broken("channels-5.qoi", good[:12] + b"\x05" + good[13:], "err", "5 channels")
    broken("huge.qoi", good[:4] + struct.pack(">II", 100000, 100000) + good[12:], "err",
           "100000x100000: TooLarge before allocating")


# -- fonts ----------------------------------------------------------------------------

_SUBSET = """
import json, sys
from fontTools import subset
from fontTools.ttLib import TTFont, TTCollection
src, bold, out, ttc, text = sys.argv[1:6]
def make(path, style):
    opts = subset.Options()
    opts.hinting = False
    opts.layout_features = ["kern"]
    opts.legacy_kern = True
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    opts.drop_tables += ["FFTM", "gasp", "DSIG"]
    f = TTFont(path, recalcTimestamp=False)
    s = subset.Subsetter(opts)
    s.populate(text=text)
    s.subset(f)
    name = f["name"]
    family = "Myla Test Sans"
    for rec in list(name.names):
        if rec.nameID in (1, 16):
            rec.string = family
        elif rec.nameID in (3, 4):
            rec.string = family + " " + style
        elif rec.nameID == 6:
            rec.string = "MylaTestSans-" + style
        elif rec.nameID == 2:
            rec.string = style
        elif rec.nameID == 5:
            rec.string = rec.toUnicode() + "; subset (MYLA-971)"
    return f
reg = make(src, "Regular")
reg.save(out)
f = TTFont(out, recalcTimestamp=False)
glyf, cmap = f["glyf"], f.getBestCmap()
kern = f["kern"].kernTables[0].kernTable if "kern" in f else {}
rev = {}
for code, g in cmap.items():
    rev.setdefault(g, chr(code))
pairs = {rev[a] + rev[b]: v for (a, b), v in kern.items() if a in rev and b in rev}
info = {
    "glyphs": len(f.getGlyphOrder()), "units_per_em": f["head"].unitsPerEm,
    "ascender": f["hhea"].ascent, "descender": f["hhea"].descent, "line_gap": f["hhea"].lineGap,
    "tables": sorted(t for t in f.keys() if t != "GlyphOrder"),
    "cmap_formats": sorted({t.format for t in f["cmap"].tables}),
    "kern_pairs": len(kern), "composite_glyphs": sorted(rev.get(g, g) for g in f.getGlyphOrder() if glyf[g].isComposite()),
    "kern_sample": {k: pairs[k] for k in sorted(pairs) if k in ("AV", "AT", "To", "Ty", "LT", "Yo", "AY", "VA", "Te", "P,")},
    "advances": {ch: f["hmtx"][cmap[ord(ch)]][0] for ch in "AVTaegoy é"},
}
c = TTCollection()
c.fonts = [TTFont(out, recalcTimestamp=False), make(bold, "Bold")]
c.save(ttc)
json.dump(info, sys.stdout)
"""

FONT_TEXT = ("".join(chr(i) for i in range(0x20, 0x7F)) + "ÀÁÂÄÅÇÈÉÊËÌÍÎÏÑÒÓÔÖØÙÚÛÜÝàáâäåçèéêëìíîïñòóôöøùúûüýÿ"
             "ßæœÆŒ€–—‘’“”…°±×÷")
RENDER_TEXTS = [("Hello, World!", 16), ("Hello, World!", 32), ("AVATAR To Yo", 24), ("Ångström façade", 20),
                ("g", 48), ("é", 64), ("The quick brown fox", 11)]


def make_fonts(c: Corpus) -> None:
    font_dir = os.path.join(DATA, "fonts")
    os.makedirs(font_dir, exist_ok=True)
    ttf = os.path.join(font_dir, FONT_NAME + ".ttf")
    ttc = os.path.join(font_dir, FONT_NAME + ".ttc")
    info_path = os.path.join(font_dir, "info.json")
    python = os.environ.get("MYLA_FONTTOOLS_PYTHON", sys.executable)
    has = subprocess.run([python, "-c", "import fontTools"], capture_output=True).returncode == 0
    if has and os.path.exists(LIBERATION):
        r = subprocess.run([python, "-c", _SUBSET, LIBERATION, LIBERATION_BOLD, ttf, ttc, FONT_TEXT],
                           capture_output=True, text=True, check=True)
        info = json.loads(r.stdout)
        ver = subprocess.run([python, "-c", "import fontTools; print(fontTools.version)"], capture_output=True,
                             text=True).stdout.strip()
        info["made_with"] = f"fontTools {ver}"
        with open(info_path, "w", encoding="utf-8") as fh:
            json.dump(info, fh, indent=1, sort_keys=True, ensure_ascii=False)
            fh.write("\n")
        with open("/usr/share/doc/fonts-liberation2/copyright", encoding="utf-8") as fh:
            _write_ofl(fh.read(), os.path.join(font_dir, "OFL.txt"))
    with open(info_path, encoding="utf-8") as fh:
        info = json.load(fh)
    for path, faces in ((ttf, 1), (ttc, 2)):
        with open(path, "rb") as fh:
            data = fh.read()
        c.fonts.append({"path": os.path.relpath(path, DATA), "faces": faces, "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "family": "Myla Test Sans", "styles": ["Regular", "Bold"][:faces],
                        "source": "Liberation Sans 2.1.5 (Regular, Bold), subset, renamed, hinting removed; OFL 1.1",
                        **({k: v for k, v in info.items()} if faces == 1 else {})})
    for text, px in RENDER_TEXTS:
        font = ImageFont.truetype(ttf, px, layout_engine=ImageFont.Layout.BASIC)
        ascent, descent = font.getmetrics()
        left, top, right, bottom = font.getbbox(text, anchor="ls")
        x0, y0 = 2 - min(0, left), 2 + ascent
        w, h = x0 + right + 2, y0 + max(descent, bottom) + 2
        im = Image.new("L", (w, h), 0)
        ImageDraw.Draw(im).text((x0, y0), text, fill=255, font=font, anchor="ls")
        p = np_pixels(np.asarray(im).copy(), "gray")
        slug = "".join(ch if ch.isascii() and ch.isalnum() else "-" for ch in text).strip("-").lower() or "glyph"
        rel = f"expected/fonts/{slug}-{px}px.pam"
        write_pam(os.path.join(DATA, rel), p)
        c.renders.append({"font": os.path.relpath(ttf, DATA), "text": text, "px": px, "origin": [x0, y0],
                          "width": w, "height": h, "pam": rel, "sha256": p.sha256(),
                          "engine": "pillow",
                          "notes": f"Pillow {Image.__version__}, FreeType {features.version('freetype2')}, basic "
                                   "layout (kern table pairs, glyphs at whole pixels, advances rounded); white on "
                                   "black coverage; FreeType autohints it (the font has no instructions, and Pillow "
                                   "can't turn hinting off): compare within a tolerance"})
    make_unhinted(c, ttf, python)


# Unhinted FreeType renderings (freetype-py, in MYLA_FONTTOOLS_PYTHON's
# Python): single glyphs at quarter-pixel offsets, and strings with each
# glyph at its fractional pen position, the way std.font places them.
_FREETYPE = """
import json, sys
import freetype
from freetype import raw
font = sys.argv[1]
glyphs, texts = json.loads(sys.argv[2]), json.loads(sys.argv[3])
face = freetype.Face(font)
FLAGS = freetype.FT_LOAD_NO_HINTING | freetype.FT_LOAD_NO_BITMAP

def render(index, px, dx):
    face.set_char_size(px * 64)
    face.load_glyph(index, FLAGS)
    slot = face.glyph
    raw.FT_Outline_Translate(raw.byref(slot.outline._FT_Outline), int(round(dx * 64)), 0)
    slot.render(freetype.FT_RENDER_MODE_NORMAL)
    bm = slot.bitmap
    rows = [bytes(bm.buffer[r * bm.pitch:r * bm.pitch + bm.width]) for r in range(bm.rows)]
    return bm.width, bm.rows, slot.bitmap_left, slot.bitmap_top, b"".join(rows), slot.linearHoriAdvance / 65536

out = {"freetype": ".".join(map(str, freetype.version())), "glyphs": [], "texts": []}
for ch, px, dx in glyphs:
    w, h, left, top, data, adv = render(face.get_char_index(ord(ch)), px, dx)
    out["glyphs"].append({"char": ch, "px": px, "dx": dx, "width": w, "height": h, "left": left, "top": top,
                          "advance": adv, "data": data.hex()})
for text, px in texts:
    face.set_char_size(px * 64)
    scale = px / face.units_per_EM
    asc, desc = face.ascender * scale, -face.descender * scale
    x0, y0 = 2, int(asc) + 3
    pen, prev, parts = float(x0), None, []
    for ch in text:
        g = face.get_char_index(ord(ch))
        if prev is not None:
            pen += face.get_kerning(prev, g, freetype.FT_KERNING_UNSCALED).x * scale
        frac = pen - int(pen)
        w, h, left, top, data, adv = render(g, px, frac)
        parts.append((int(pen) + left, y0 - top, w, h, data))
        pen += adv
        prev = g
    width, height = int(pen) + 4, y0 + int(desc) + 3
    canvas = bytearray(width * height)
    for x, y, w, h, data in parts:
        for r in range(h):
            for c in range(w):
                if 0 <= x + c < width and 0 <= y + r < height:
                    i = (y + r) * width + x + c
                    canvas[i] = min(255, canvas[i] + data[r * w + c])
    out["texts"].append({"text": text, "px": px, "origin": [x0, y0], "width": width, "height": height,
                         "data": bytes(canvas).hex()})
json.dump(out, sys.stdout)
"""

UNHINTED_GLYPHS = [(ch, px, dx) for ch in "Ag@é" for px in (12, 24, 48) for dx in (0.0, 0.25, 0.5, 0.75)]
UNHINTED_TEXTS = [("AVATAR To Yo", 24), ("Hello, World!", 16)]


def make_unhinted(c: Corpus, ttf: str, python: str) -> None:
    """The unhinted renderings, from freetype-py if MYLA_FONTTOOLS_PYTHON's
    Python has it (else the committed ones, as the manifest had them)."""
    rel_font = os.path.relpath(ttf, DATA)
    if subprocess.run([python, "-c", "import freetype"], capture_output=True).returncode != 0:
        with open(MANIFEST, encoding="utf-8") as fh:
            old = json.load(fh)
        c.renders += [r for r in old["renders"] if r.get("engine") == "freetype-unhinted"]
        return
    shutil.rmtree(os.path.join(DATA, "expected", "fonts", "unhinted"), ignore_errors=True)
    r = subprocess.run([python, "-c", _FREETYPE, ttf, json.dumps(UNHINTED_GLYPHS), json.dumps(UNHINTED_TEXTS)],
                       capture_output=True, text=True, check=True)
    out = json.loads(r.stdout)
    note = (f"FreeType {out['freetype']} through freetype-py, FT_LOAD_NO_HINTING, the normal (exact area, 256 "
            "levels) renderer: the coverage std.font's rasteriser should give within a level or two")
    for g in out["glyphs"]:
        if g["width"] == 0:
            continue
        p = from_bytes(g["width"], g["height"], "gray", 8, bytes.fromhex(g["data"]))
        slug = {"A": "A", "g": "g", "@": "at", "é": "eacute"}[g["char"]]
        rel = f"expected/fonts/unhinted/{slug}-{g['px']}px-dx{int(g['dx'] * 100):02d}.pam"
        write_pam(os.path.join(DATA, rel), p)
        c.renders.append({"font": rel_font, "text": g["char"], "px": g["px"], "dx": g["dx"], "left": g["left"],
                          "top": g["top"], "advance": g["advance"], "width": g["width"], "height": g["height"],
                          "pam": rel, "sha256": p.sha256(), "engine": "freetype-unhinted",
                          "notes": note + "; one glyph, its outline moved right by dx pixels; the bitmap's top "
                                          "left corner is (left, -top) from the pen on the baseline (y down)"})
    for t in out["texts"]:
        p = from_bytes(t["width"], t["height"], "gray", 8, bytes.fromhex(t["data"]))
        slug = "".join(ch if ch.isascii() and ch.isalnum() else "-" for ch in t["text"]).strip("-").lower()
        rel = f"expected/fonts/unhinted/{slug}-{t['px']}px.pam"
        write_pam(os.path.join(DATA, rel), p)
        c.renders.append({"font": rel_font, "text": t["text"], "px": t["px"], "origin": t["origin"],
                          "width": t["width"], "height": t["height"], "pam": rel, "sha256": p.sha256(),
                          "engine": "freetype-unhinted",
                          "notes": note + "; each glyph at its fractional pen position (unhinted advances, from "
                                          "the origin on the baseline), coverage added and clamped where glyphs "
                                          "overlap; not kerned: FreeType's get_kerning gave 0 for the kern table's "
                                          "pairs here (MYLA-969 found the strings match unkerned pens, to 2 "
                                          "levels, and not kerned ones)"})


def _write_ofl(copyright_text: str, out: str) -> None:
    """The OFL text and the copyright lines from Debian's copyright file."""
    lines = copyright_text.split("\n")
    start = next(i for i, l in enumerate(lines) if l.startswith("Copyright:"))
    keep = []
    for l in lines[start + 1:]:
        if l.startswith("License:"):
            break
        keep.append(l.strip())
    body = []
    for l in lines[lines.index(next(l for l in lines if l.startswith("License: SIL-OFL-1.1"))) + 1:]:
        if l and not l.startswith(" "):
            break
        s = l[1:] if l.startswith(" ") else l
        body.append("" if s == "." else s.replace(" ? ", " -- ").replace("?", "--"))
    text = ("Myla Test Sans is a subset of Liberation Sans 2.1.5 (Regular and Bold), renamed as the licence\n"
            "asks of a Modified Version, with its hinting removed (MYLA-971).\n\n" + "\n".join(keep) + "\n\n"
            + "\n".join(body).strip() + "\n")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text)


# -- all of it ----------------------------------------------------------------------

def vendor() -> None:
    c = Corpus()
    expected_dir = os.path.join(DATA, "expected")
    for name in os.listdir(expected_dir) if os.path.isdir(expected_dir) else []:
        if name != "fonts":
            shutil.rmtree(os.path.join(expected_dir, name))
    fonts_dir = os.path.join(expected_dir, "fonts")
    for name in os.listdir(fonts_dir) if os.path.isdir(fonts_dir) else []:
        if name != "unhinted":       # make_unhinted keeps them when freetype-py is missing
            os.remove(os.path.join(fonts_dir, name))
    for fmt in ("png/gen", "jpeg", "gif", "tiff", "bmp", "pnm", "qoi"):
        d = os.path.join(DATA, fmt)
        if os.path.isdir(d):
            for name in os.listdir(d):
                if not (fmt == "jpeg" and name in ("photo-q85-s440.jpg", "photo-q85-s411.jpg")
                        and not shutil.which("convert")):
                    os.remove(os.path.join(d, name))
    make_png(c)
    make_jpeg(c)
    make_gif(c)
    make_tiff(c)
    make_bmp(c)
    make_pnm(c)
    make_qoi(c)
    make_fonts(c)
    m = {"about": "MYLA-971's image and font corpus: see tests/burn/_images.py for the fields and LICENSES.md for the "
                  "sources; made by `python3 -m tests.burn.test_images --vendor`",
         "pillow": Image.__version__, "libjpeg_turbo": features.version("libjpeg_turbo"),
         "freetype": features.version("freetype2"), "zlib": features.version("zlib"),
         "images": c.images, "fonts": c.fonts, "renders": c.renders}
    with open(MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(m, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    total = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(DATA) for f in fs)
    print(f"{len(c.images)} images, {len(c.fonts)} fonts, {len(c.renders)} renderings; {total} bytes")
