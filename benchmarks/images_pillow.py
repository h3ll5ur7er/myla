"""Pillow's times for the work benchmarks/images_std.my does (MYLA-971):
`python3 benchmarks/images_pillow.py` (needs Pillow and numpy).

The picture is the same as images_std.my's `photo` (the formula is in
`photo` below and in the Myla file, checked by its `#test` cases): a 12-MP
(4000x3000) RGB "photo" of gradients, two discs and a little noise. Each line
is the fastest of the runs and the median, as std.bench reports them.
Pillow's C code (libpng through zlib-ng, libjpeg-turbo with SIMD) is the
baseline a later optimisation round of the Myla codecs measures against.
"""
from __future__ import annotations

import io
import os
import statistics
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, features

FONT = os.path.join(os.path.dirname(__file__), os.pardir, "tests", "burn", "data", "images", "fonts",
                    "MylaTestSans.ttf")

PARAGRAPH = ("The quick brown fox jumps over the lazy dog. Pack my box with five dozen liquor jugs. "
             "Sphinx of black quartz, judge my vow! How vexingly quick daft zebras jump. "
             "Ångström's façade: naïve café, déjà vu. ") * 4


def photo(w: int, h: int) -> np.ndarray:
    """images_std.my's `photo`: every value an integer formula of x and y
    (gradients, two discs, a hash of x and y as noise of -16 to 15)."""
    y, x = np.mgrid[0:h, 0:w].astype(np.int64)
    m = ((x * 73856093) ^ (y * 19349663)) & 0xFFFFFFFF
    m = ((m ^ (m >> 13)) * 0x5BD1E995) & 0xFFFFFFFF
    n = ((m ^ (m >> 15)) & 31) - 16
    r = x * 200 // w + y * 55 // h + n
    g = y * 180 // h + (x + y) * 60 // (w + h) + n
    b = 255 - x * 128 // w - y * 64 // h + n - 8
    for cx, cy, rad, col in ((w // 3, h // 2, h // 5, (230, 40, 30)), (2 * w // 3, h // 3, h // 7, (20, 90, 200))):
        inside = (x - cx) ** 2 + (y - cy) ** 2 < rad * rad
        r = np.where(inside, col[0] + n, r)
        g = np.where(inside, col[1] + n, g)
        b = np.where(inside, col[2] + n, b)
    return np.clip(np.stack([r, g, b], axis=-1), 0, 255).astype(np.uint8)


def timed(name: str, f, runs: int = 5) -> None:
    f()
    times = []
    for _ in range(runs):
        t = time.perf_counter()
        f()
        times.append(time.perf_counter() - t)
    print(f"{name:<40} min {min(times) * 1000:9.1f} ms   median {statistics.median(times) * 1000:9.1f} ms")


def main() -> None:
    w, h = (int(a) for a in sys.argv[1:3]) if len(sys.argv) == 3 else (4000, 3000)
    print(f"Pillow {Image.__version__}, libjpeg-turbo {features.version('libjpeg_turbo')}, "
          f"zlib {features.version('zlib')}, FreeType {features.version('freetype2')}; {w}x{h} RGB")
    img = Image.fromarray(photo(w, h))
    png = io.BytesIO()
    img.save(png, "PNG", compress_level=6)
    jpg = io.BytesIO()
    img.save(jpg, "JPEG", quality=85, subsampling="4:2:0")
    print(f"the PNG is {len(png.getvalue())} bytes, the JPEG {len(jpg.getvalue())}")

    def decode(data: bytes):
        return lambda: Image.open(io.BytesIO(data)).load()

    timed("png encode (level 6)", lambda: img.save(io.BytesIO(), "PNG", compress_level=6))
    timed("png decode", decode(png.getvalue()))
    timed("jpeg encode (q85, 4:2:0)", lambda: img.save(io.BytesIO(), "JPEG", quality=85, subsampling="4:2:0"))
    timed("jpeg decode", decode(jpg.getvalue()))
    small = img.resize((1024, 1024), Image.Resampling.BILINEAR)
    timed("resize 12 MP to 1155x866, bilinear", lambda: img.resize((1155, 866), Image.Resampling.BILINEAR))
    timed("resize 12 MP to 1155x866, box (area)", lambda: img.resize((1155, 866), Image.Resampling.BOX))
    timed("resize 12 MP to 1155x866, lanczos", lambda: img.resize((1155, 866), Image.Resampling.LANCZOS))
    timed("gaussian blur 1 MP, sigma 2 (box approx.)", lambda: small.filter(ImageFilter.GaussianBlur(2)))
    gray = small.convert("L")
    timed("gray 1 MP, find edges (3x3, no canny)", lambda: gray.filter(ImageFilter.FIND_EDGES))
    font = ImageFont.truetype(FONT, 16, layout_engine=ImageFont.Layout.BASIC)

    def text() -> None:
        canvas = Image.new("L", (800, 400), 0)
        d = ImageDraw.Draw(canvas)
        words, line, y = PARAGRAPH.split(" "), "", 4
        for word in words:
            if font.getlength(line + " " + word) > 780:
                d.text((4, y), line, fill=255, font=font)
                line, y = word, y + 20
            else:
                line = (line + " " + word).strip()
        d.text((4, y), line, fill=255, font=font)

    timed(f"text: {len(PARAGRAPH)} chars at 16 px, wrapped", text)


if __name__ == "__main__":
    main()
