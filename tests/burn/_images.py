"""The image and font corpus and the harness the codec lanes plug into (MYLA-945).

The corpus is `tests/burn/data/images/`: a folder per format (`png/`, `jpeg/`,
`gif/`, `tiff/`, `bmp/`, `pnm/`, `qoi/`, `fonts/`), the expected pixels under
`expected/`, the licences in `LICENSES.md`, and `manifest.json`, which lists
every file. `python3 -m tests.burn.test_images --vendor` makes all of it again
with Pillow (`tests/burn/_images_vendor.py`); nothing here needs a package
that isn't Python's own.

The manifest
------------

`images` is a list of entries, one per file (`entries()` reads them):

- `path` (from the corpus folder), `format` (`png`, `jpeg`, `gif`, `tiff`,
  `bmp`, `pnm`, `qoi`), `source` (`pngsuite`, `pillow`, `generated`: our own
  writer in `_images_vendor.py`, `imagemagick`), `features` (words such as
  `interlaced`, `palette`, `trns`, `bits2`, `progressive`, `s420`, `lzw`,
  `tiles`, `animated`), `notes`.
- `expect`: `ok` (it decodes, to the pixels below), `err` (a decoder must
  return `Err`: a broken or unsupported file) or `any` (it may be either,
  never a runtime error: a file cut inside its pixel data, which some
  decoders read as far as it goes).
- For `ok`: `width`, `height`, `layout` (std.image's names: `gray`,
  `gray+alpha`, `rgb`, `rgba`), `bits` (8 or 16 a sample, 32 for float32),
  `frames` (an animation's frames as shown, composited by Pillow; 1
  otherwise), `sha256` (of the samples as the driver protocol hashes them,
  below), and `pam`: the expected pixels as a PAM file (P7, MAXVAL 255 or
  65535, all frames one after the other), or null for a large image, which
  has only its hash. A sample of fewer than 8 bits is scaled to 8
  (`v * 255 / (2^bits - 1)`); 16-bit files keep 16 bits.
- Format-specific keys: `orientation` (a JPEG's EXIF orientation; the pixels
  are as stored, not turned), `pages` (a TIFF's pages after the first, each
  with `width`, `height`, `layout`, `bits`, `sha256`, `pam`), `cmyk_sha256`
  (an Adobe CMYK JPEG's CMYK samples as Pillow gives them), `disposals` (a
  GIF's disposal method a frame), `tolerance` (`max_abs`, `min_psnr`; none
  so far: every expected image is exact).

`fonts` lists the font files: `MylaTestSans.ttf` (a subset of Liberation Sans,
OFL; TrueType outlines, composite accented letters, a format 0 `kern` table
of 104 pairs, cmap format 4) with its metrics, a sample of its kerning pairs
and advances (font units), and `MylaTestSans.ttc` (Regular and Bold).
`renders` are coverage masks (gray PAM, 255 full) of text in it: `engine`
`freetype-unhinted` (FreeType without hinting: single glyphs moved right by
`dx` of 0, 1/4, 1/2 and 3/4 pixel, the bitmap's top left at (`left`, -`top`)
from the pen; and strings with each glyph at its fractional pen position from
`origin` on the baseline, kerned), which std.font's rasteriser should match
within a level or two, and `pillow` (Pillow's text, autohinted, at whole
pixels), to compare within a tolerance.

The driver protocol
-------------------

A codec lane writes `tests/burn/drivers/<format>.my`, about ten lines, which
hands its decoder to `tests/burn/drivers/image_driver.my`:

    import std.png as png
    import image_driver as driver

    fun main() {
        driver.serve8((b: [uint8], max: int64) => png.decode(b, max))
    }

(`serve16`, `serve_f32` and `serve8_frames`/`serve16_frames` for 16-bit,
float32 and animated decoders.) The driver reads lines from stdin, each an
input path or `<input path>\\t<output path>`, until an empty line or the end,
and prints a line for each:

    ok <width> <height> <layout> <bits> <frames> <sha256>
    err <message>
    bad <message>

`sha256` is the hex SHA-256 of the samples, interleaved, row by row, frame
after frame: a byte each at 8 bits, two big endian at 16 (as PAM holds them),
four big endian (the float's bits) at 32. With an output path the frames are
also written there as PAM images. `bad` is a decoder bug the driver caught
(samples that don't fill the image). `--max-pixels N` passes `max_pixels`.

Then `test_images.py`'s `CODECS` table names the driver, and its tests run it
(skipped while `lib/std/<module>.my` or the driver doesn't exist):

- `check_corpus`: every manifest entry of the format, natively, its pixels
  compared exactly (or within the codec's tolerance: max abs difference,
  PSNR) with the expected ones; `err` entries must be `Err`.
- the smallest files the same in the interpreter (`myla run`).
- `fuzz`: every truncation of a few of the format's files up to 512 bytes,
  and 10,000 seeded mutations (bit flips, bytes overwritten with random or
  boundary values, a slice repeated, deleted or inserted, a 16- or 32-bit
  field set to 0, a boundary value or a large one, in either byte order) of
  all of them, natively plain and `--checked`. Each run must print `ok` or
  `err`, never `bad` or a runtime error; a failure names the seed, the file,
  the mutation, and where the case was saved. `MYLA_FUZZ_SEED` and
  `MYLA_FUZZ_CASES` change the seed and the number of mutations.

With MYLA_TEST_TARGET set (`scripts/test-target.py`), drivers are built for
that target and run under qemu-aarch64, Node or Wine (`_native.run_argv`).
"""
from __future__ import annotations

import array
import functools
import gzip
import hashlib
import json
import math
import os
import random
import shutil
import struct
import subprocess
import sys
import zlib
from dataclasses import dataclass, field
from typing import Iterator

from tests.burn._native import check_file, native_build, run_argv
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
DATA = os.path.join(_REPO, "tests", "burn", "data", "images")
MANIFEST = os.path.join(DATA, "manifest.json")
DRIVERS = os.path.join(_REPO, "tests", "burn", "drivers")

# std.image's layout names: channels and PAM's TUPLTYPE.
LAYOUTS = {
    "gray": (1, "GRAYSCALE"),
    "gray+alpha": (2, "GRAYSCALE_ALPHA"),
    "rgb": (3, "RGB"),
    "rgba": (4, "RGB_ALPHA"),
}
_TUPLTYPES = {t: name for name, (_, t) in LAYOUTS.items()}
_BY_CHANNELS = {c: name for name, (c, _) in LAYOUTS.items()}


# -- pixels and PAM -------------------------------------------------------------

@dataclass
class Pixels:
    """Decoded frames: `frames` images of `width` x `height` in `layout`, their
    samples one list (`array('B')`, `array('H')` or `array('f')` for 8, 16
    and 32 bits) of every frame after the other."""
    width: int
    height: int
    layout: str
    bits: int
    samples: array.array
    frames: int = 1

    @property
    def channels(self) -> int:
        return LAYOUTS[self.layout][0]

    def raw(self) -> bytes:
        """The samples as the protocol hashes them (big endian)."""
        return samples_bytes(self.samples, self.bits)

    def sha256(self) -> str:
        return hashlib.sha256(self.raw()).hexdigest()

    def frame(self, i: int) -> "Pixels":
        n = self.width * self.height * self.channels
        return Pixels(self.width, self.height, self.layout, self.bits, self.samples[i * n:(i + 1) * n])


def samples_bytes(samples, bits: int) -> bytes:
    """Samples as bytes: one each at 8 bits, big endian at 16 and 32."""
    if bits == 8:
        return bytes(samples)
    a = array.array("H" if bits == 16 else "f", samples)
    if sys.byteorder == "little":
        a.byteswap()
    return a.tobytes()


def _typecode(bits: int) -> str:
    return {8: "B", 16: "H", 32: "f"}[bits]


def from_bytes(width: int, height: int, layout: str, bits: int, raw: bytes, frames: int = 1) -> Pixels:
    """Pixels from big-endian sample bytes (what `Pixels.raw` gives)."""
    a = array.array(_typecode(bits))
    a.frombytes(raw)
    if bits != 8 and sys.byteorder == "little":
        a.byteswap()
    return Pixels(width, height, layout, bits, a, frames)


def pam_bytes(p: Pixels) -> bytes:
    """`p` as PAM images, one a frame (8 or 16 bits)."""
    if p.bits not in (8, 16):
        raise ValueError("PAM holds 8 or 16 bits")
    header = (f"P7\nWIDTH {p.width}\nHEIGHT {p.height}\nDEPTH {p.channels}\n"
              f"MAXVAL {255 if p.bits == 8 else 65535}\nTUPLTYPE {LAYOUTS[p.layout][1]}\nENDHDR\n").encode()
    raw = p.raw()
    n = len(raw) // p.frames
    return b"".join(header + raw[i * n:(i + 1) * n] for i in range(p.frames))


def write_pam(path: str, p: Pixels) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(pam_bytes(p))


def read_pam(data: bytes) -> Pixels:
    """The PAM images of `data` (all the same size and layout) as frames. A
    PAM without TUPLTYPE takes its layout from DEPTH; MAXVAL is 255 or
    65535."""
    pos, frames, chunks, shape = 0, 0, [], None
    while pos < len(data):
        if data[pos:pos + 3] != b"P7\n":
            raise ValueError(f"not a PAM image at {pos}")
        end = data.index(b"ENDHDR\n", pos) + 7
        fields = {}
        for line in data[pos + 3:end - 7].decode("ascii").split("\n"):
            if line and not line.startswith("#"):
                k, _, v = line.partition(" ")
                fields[k] = v.strip()
        w, h, depth, maxval = (int(fields[k]) for k in ("WIDTH", "HEIGHT", "DEPTH", "MAXVAL"))
        layout = _TUPLTYPES.get(fields.get("TUPLTYPE", ""), _BY_CHANNELS.get(depth))
        if layout is None or LAYOUTS[layout][0] != depth or maxval not in (255, 65535):
            raise ValueError(f"unsupported PAM header {fields}")
        bits = 8 if maxval == 255 else 16
        n = w * h * depth * bits // 8
        if shape is not None and shape != (w, h, layout, bits):
            raise ValueError("PAM frames of different shapes")
        shape = (w, h, layout, bits)
        if end + n > len(data):
            raise ValueError("PAM samples cut short")
        chunks.append(data[end:end + n])
        frames += 1
        pos = end + n
    if shape is None:
        raise ValueError("no PAM image")
    return from_bytes(*shape, b"".join(chunks), frames)


def read_pam_file(path: str) -> Pixels:
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rb") as fh:
        return read_pam(fh.read())


# -- a reference PNG decoder ----------------------------------------------------

_ADAM7 = [(0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2)]
_PNG_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
_PNG_DEPTHS = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else (b if pb <= pc else c)


def png_decode(data: bytes) -> Pixels:
    """PNG's pixels as std.png should give them: palette to rgb or rgba,
    `tRNS` to an alpha channel, fewer than 8 bits scaled to 8, 16 kept.
    ValueError for anything wrong (the CRCs are checked)."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("signature")
    pos, ihdr, plte, trns, idat, ended = 8, None, None, None, b"", False
    while pos < len(data):
        if pos + 12 > len(data):
            raise ValueError("chunk cut short")
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        if len(body) != n or pos + 12 + n > len(data):
            raise ValueError("chunk cut short")
        (crc,) = struct.unpack(">I", data[pos + 8 + n:pos + 12 + n])
        if zlib.crc32(kind + body) != crc:
            raise ValueError(f"CRC of {kind!r}")
        pos += 12 + n
        if ihdr is None and kind != b"IHDR":
            raise ValueError("IHDR not first")
        if kind == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            plte = body
        elif kind == b"tRNS":
            trns = body
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            ended = True
            break
        elif not (kind[0] & 0x20):
            raise ValueError(f"unknown critical chunk {kind!r}")
    if not ended:
        raise ValueError("no IEND")
    w, h, depth, ctype, comp, filt, interlace = ihdr
    if ctype not in _PNG_DEPTHS or depth not in _PNG_DEPTHS[ctype] or comp or filt or interlace > 1 or not w or not h:
        raise ValueError("IHDR")
    if w * h > 1 << 26:
        raise ValueError("too large for this decoder")
    if ctype == 3 and (plte is None or len(plte) % 3):
        raise ValueError("PLTE")
    raw = zlib.decompress(idat)
    ch = _PNG_CHANNELS[ctype]
    bpp_bits = depth * ch
    bpp = max(1, bpp_bits // 8)
    grid = [[None] * w for _ in range(h)]
    at = 0
    for xs, ys, dx, dy in (_ADAM7 if interlace else [(0, 0, 1, 1)]):
        pw, ph = (w - xs + dx - 1) // dx, (h - ys + dy - 1) // dy
        if pw <= 0 or ph <= 0:
            continue
        stride = (pw * bpp_bits + 7) // 8
        prev = bytearray(stride)
        for r in range(ph):
            if at + 1 + stride > len(raw):
                raise ValueError("IDAT short")
            f, line = raw[at], bytearray(raw[at + 1:at + 1 + stride])
            at += 1 + stride
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b, c = prev[i], (prev[i - bpp] if i >= bpp else 0)
                if f == 1:
                    line[i] = (line[i] + a) & 255
                elif f == 2:
                    line[i] = (line[i] + b) & 255
                elif f == 3:
                    line[i] = (line[i] + (a + b) // 2) & 255
                elif f == 4:
                    line[i] = (line[i] + _paeth(a, b, c)) & 255
                elif f != 0:
                    raise ValueError(f"filter {f}")
            prev = line
            for col in range(pw):
                px = []
                for s in range(ch):
                    k = col * ch + s
                    if depth == 16:
                        v = (line[2 * k] << 8) | line[2 * k + 1]
                    elif depth == 8:
                        v = line[k]
                    else:
                        bit = k * depth
                        v = (line[bit // 8] >> (8 - depth - bit % 8)) & ((1 << depth) - 1)
                    px.append(v)
                grid[ys + r * dy][xs + col * dx] = px
    bits = 16 if depth == 16 else 8
    full = (1 << depth) - 1
    scale = (lambda v: v * 255 // full) if depth < 8 else (lambda v: v)
    out = array.array("H" if bits == 16 else "B")
    if ctype == 3:
        alphas = trns or b""
        layout = "rgba" if trns else "rgb"
        for row in grid:
            for (i,) in row:
                if 3 * i + 3 > len(plte):
                    raise ValueError("palette index out of range")
                out.extend(plte[3 * i:3 * i + 3])
                if trns:
                    out.append(alphas[i] if i < len(alphas) else 255)
    else:
        key = None
        if trns is not None and ctype in (0, 2):
            key = list(struct.unpack(">" + "H" * (len(trns) // 2), trns))
        has_alpha = ctype in (4, 6) or key is not None
        layout = {1: "gray", 3: "rgb"}.get(ch, None) or ("gray+alpha" if ch == 2 else "rgba")
        if key is not None:
            layout = "gray+alpha" if ch == 1 else "rgba"
        for row in grid:
            for px in row:
                out.extend(scale(v) for v in px)
                if key is not None:
                    out.append(0 if px == key else (65535 if bits == 16 else 255))
        assert has_alpha == (layout in ("gray+alpha", "rgba"))
    return Pixels(w, h, layout, bits, out)


# -- the manifest -------------------------------------------------------------

@functools.cache
def manifest() -> dict:
    with open(MANIFEST, encoding="utf-8") as fh:
        return json.load(fh)


def entries(fmt: str | None = None, expect: str | None = None) -> list[dict]:
    """The manifest's image entries, of the format `fmt` and the verdict
    `expect` if given."""
    return [e for e in manifest()["images"]
            if (fmt is None or e["format"] == fmt) and (expect is None or e["expect"] == expect)]


def renders(engine: str | None = None) -> list[dict]:
    """The manifest's text renderings (`freetype-unhinted` or `pillow`)."""
    return [r for r in manifest()["renders"] if engine is None or r["engine"] == engine]


def path_of(entry: dict) -> str:
    return os.path.join(DATA, entry["path"])


def expected(entry: dict) -> Pixels | None:
    """The expected pixels of an `ok` entry, if it has a PAM file."""
    return read_pam_file(os.path.join(DATA, entry["pam"])) if entry.get("pam") else None


# -- comparing ------------------------------------------------------------------

def to_bits(p: Pixels, bits: int) -> Pixels:
    """`p` at `bits`: 16 to 8 rounded as libpng and std.image do
    (`(v * 255 + 32767) / 65535`), 8 to 16 widened by 257."""
    if p.bits == bits:
        return p
    if (p.bits, bits) == (16, 8):
        out = array.array("B", ((v * 255 + 32767) // 65535 for v in p.samples))
    elif (p.bits, bits) == (8, 16):
        out = array.array("H", (v * 257 for v in p.samples))
    else:
        raise ValueError(f"no conversion from {p.bits} to {bits} bits")
    return Pixels(p.width, p.height, p.layout, bits, out, p.frames)


def to_layout(p: Pixels, layout: str) -> Pixels | None:
    """`p` in `layout` if that loses nothing (gray to rgb, an alpha of all
    full scale dropped, an opaque alpha added, rgb whose channels agree to
    gray); None otherwise."""
    if p.layout == layout:
        return p
    src_c, dst_c = p.channels, LAYOUTS[layout][0]
    full = (1 << p.bits) - 1 if p.bits != 32 else 1.0
    src_alpha, dst_alpha = p.layout in ("gray+alpha", "rgba"), layout in ("gray+alpha", "rgba")
    src_color, dst_color = p.layout in ("rgb", "rgba"), layout in ("rgb", "rgba")
    out = array.array(p.samples.typecode)
    s = p.samples
    for i in range(0, len(s), src_c):
        px = s[i:i + src_c]
        alpha = px[-1] if src_alpha else full
        color = list(px[:-1] if src_alpha else px)
        if src_alpha and not dst_alpha and alpha != full:
            return None
        if src_color and not dst_color:
            if not color[0] == color[1] == color[2]:
                return None
            color = color[:1]
        elif dst_color and not src_color:
            color = color * 3
        out.extend(color + ([alpha] if dst_alpha else []))
    assert len(out) == len(s) // src_c * dst_c
    return Pixels(p.width, p.height, layout, p.bits, out, p.frames)


@dataclass
class Difference:
    count: int                # samples that differ
    max_abs: float
    psnr: float               # dB; inf when equal
    first: tuple | None       # (frame, x, y, channel, got, want)


def difference(got: Pixels, want: Pixels) -> Difference:
    """How `got` differs from `want` (same shape)."""
    c, n = got.channels, got.width * got.height * got.channels
    count, max_abs, sq, first = 0, 0, 0.0, None
    for i, (a, b) in enumerate(zip(got.samples, want.samples)):
        if a != b:
            d = abs(a - b)
            count += 1
            max_abs = max(max_abs, d)
            sq += d * d
            if first is None:
                f, r = divmod(i, n)
                first = (f, (r // c) % got.width, r // c // got.width, r % c, a, b)
    full = (1 << got.bits) - 1 if got.bits != 32 else 1.0
    mse = sq / max(1, len(got.samples))
    psnr = math.inf if mse == 0 else 10 * math.log10(full * full / mse)
    return Difference(count, max_abs, psnr, first)


def compare(got: Pixels, want: Pixels, max_abs: float = 0, min_psnr: float | None = None,
            convert: bool = True) -> str | None:
    """None if `got` matches `want`, else what differs. Exact unless
    `max_abs` (the largest difference of a sample allowed) or `min_psnr`
    (dB) say otherwise. With `convert`, `want` is first brought to `got`'s
    bits (16 to 8 rounded) and to its layout where that loses nothing."""
    if convert:
        if want.bits != got.bits and {want.bits, got.bits} == {8, 16}:
            want = to_bits(want, got.bits)
        if want.layout != got.layout:
            want = to_layout(want, got.layout) or want

    def shape(p: Pixels) -> tuple:
        return (p.width, p.height, p.layout, p.bits, p.frames)

    if shape(got) != shape(want):
        return f"shape {shape(got)}, expected {shape(want)}"
    d = difference(got, want)
    if d.count == 0:
        return None
    if d.max_abs <= max_abs and (min_psnr is None or d.psnr >= min_psnr):
        return None
    f, x, y, ch, a, b = d.first
    return (f"{d.count} of {len(got.samples)} samples differ, by at most {d.max_abs} (PSNR {d.psnr:.2f} dB); "
            f"the first: frame {f} pixel ({x}, {y}) channel {ch} is {a}, expected {b}")


# -- drivers --------------------------------------------------------------------

@dataclass
class Result:
    """One line a driver printed."""
    kind: str                 # ok, err or bad
    message: str = ""
    width: int = 0
    height: int = 0
    layout: str = ""
    bits: int = 0
    frames: int = 0
    sha256: str = ""
    line: str = ""


def parse_line(line: str) -> Result:
    kind, _, rest = line.partition(" ")
    if kind == "ok":
        w = rest.split(" ")
        if len(w) == 6:
            return Result("ok", "", int(w[0]), int(w[1]), w[2], int(w[3]), int(w[4]), w[5], line)
        return Result("bad", f"a malformed ok line: {line!r}", line=line)
    if kind in ("err", "bad"):
        return Result(kind, rest, line=line)
    return Result("bad", f"not a protocol line: {line!r}", line=line)


def driver_source(name: str) -> str:
    return os.path.join(DRIVERS, name + ".my")


def build_driver(source: str, out_dir: str, checked: bool = False) -> list[str]:
    """`source` built natively (for MYLA_TEST_TARGET's target if set), plain
    or `--checked`, into `out_dir`; the command that runs it."""
    binary = os.path.join(out_dir, os.path.splitext(os.path.basename(source))[0] + ("-checked" if checked else ""))
    native_build(check_file(source), binary, checked=checked)
    return run_argv(binary, binary)[0]


def interpreter_argv(source: str) -> list[str]:
    """The command that runs `source` in the self-hosted interpreter."""
    return [selfhost_tool("main"), "run", source, "--stdlib", STDLIB_ROOT]


class DriverFailed(AssertionError):
    """A run that didn't end with exit 0 and a line per case: `index` is the
    case it stopped at (the lines printed until then)."""

    def __init__(self, message: str, index: int, stderr: str):
        super().__init__(message)
        self.index = index
        self.stderr = stderr


class Driver:
    """A built driver: `argv` and the `--max-pixels` it gets."""

    def __init__(self, argv: list[str], max_pixels: int | None = None, timeout: float = 600):
        self.argv = list(argv) + (["--max-pixels", str(max_pixels)] if max_pixels else [])
        self.timeout = timeout

    def run(self, cases: list[tuple[str, str | None]]) -> list[Result]:
        """A result for each (input path, output path or None)."""
        text = "".join(f"{i}\t{o}\n" if o else f"{i}\n" for i, o in cases)
        try:
            proc = subprocess.run(self.argv, input=text.encode(), capture_output=True, timeout=self.timeout)
        except subprocess.TimeoutExpired as e:
            done = (e.stdout or b"").decode("utf-8", "replace").count("\n")
            raise DriverFailed(f"timed out after {self.timeout} s at case {done}", done, "") from None
        lines = proc.stdout.decode("utf-8", "replace").split("\n")[:-1]
        stderr = proc.stderr.decode("utf-8", "replace")
        if proc.returncode != 0 or len(lines) != len(cases):
            raise DriverFailed(f"exit {proc.returncode} after {len(lines)} of {len(cases)} cases: {stderr[-1500:]}",
                               len(lines), stderr)
        return [parse_line(line) for line in lines]

    def decode(self, path: str, out: str | None = None) -> Result:
        return self.run([(path, out)])[0]


def check_corpus(driver: Driver, items: list[dict], tmp: str, max_abs: float = 0,
                 min_psnr: float | None = None) -> list[str]:
    """Each entry decoded by `driver` and checked against the manifest: the
    problems found (empty when all is well). An entry's own `tolerance`
    (`max_abs`, `min_psnr`) wins over the arguments."""
    cases = []
    for i, e in enumerate(items):
        out = os.path.join(tmp, f"out{i}.pam") if e["expect"] == "ok" else None
        cases.append((path_of(e), out))
    try:
        results = driver.run(cases)
    except DriverFailed as failed:
        name = items[min(failed.index, len(items) - 1)]["path"]
        raise AssertionError(f"the driver stopped at {name}: {failed}") from None
    problems = []
    for e, (_, out), r in zip(items, cases, results):
        name = e["path"]
        if r.kind == "bad":
            problems.append(f"{name}: bad: {r.message}")
        elif e["expect"] == "err" and r.kind != "err":
            problems.append(f"{name}: decoded ({r.line}), expected an error: {e.get('notes', '')}")
        elif e["expect"] == "ok" and r.kind != "ok":
            problems.append(f"{name}: {r.line}")
        elif e["expect"] == "ok":
            want = expected(e)
            tol = e.get("tolerance", {})
            exact = (r.width, r.height, r.layout, r.bits, r.frames, r.sha256) == (
                e["width"], e["height"], e["layout"], e["bits"], e["frames"], e["sha256"])
            if exact:
                continue
            if want is None:
                problems.append(f"{name}: {r.line}, expected {e['width']} {e['height']} {e['layout']} {e['bits']} "
                                f"{e['frames']} {e['sha256']} (no PAM to compare with)")
                continue
            got = read_pam_file(out) if r.bits != 32 else None
            why = "float samples differ" if got is None else compare(
                got, want, tol.get("max_abs", max_abs), tol.get("min_psnr", min_psnr))
            if why:
                problems.append(f"{name}: {why}")
    return problems


# -- fuzzing --------------------------------------------------------------------

def truncations(data: bytes, limit: int = 512) -> Iterator[tuple[str, bytes]]:
    """`data` cut after each length from 0 to `limit` bytes (or one short of
    the whole)."""
    for n in range(min(len(data), limit + 1)):
        yield f"truncated to {n} bytes", data[:n]


_BOUNDARY = [0, 1, 0x7F, 0x80, 0xFF]
_WIDE = [0, 1, 0x7FFF, 0x8000, 0xFFFF, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF, 0x10000, 0x1000000]


def mutate(data: bytes, rng: random.Random) -> tuple[str, bytes]:
    """One seeded mutation of `data`: what was done, and the result. Half the
    offsets fall in the first 64 bytes, where the headers are."""
    b = bytearray(data)
    if not b:
        return "an empty input", bytes([rng.randrange(256)])

    def offset(span: int = 1) -> int:
        top = max(1, len(b) - span + 1)
        return rng.randrange(min(top, 64)) if rng.random() < 0.5 else rng.randrange(top)

    kind = rng.randrange(8)
    if kind == 0:
        flips = [(offset(), rng.randrange(8)) for _ in range(rng.choice([1, 1, 2, 4]))]
        for at, bit in flips:
            b[at] ^= 1 << bit
        return "bits flipped: " + ", ".join(f"{at}.{bit}" for at, bit in flips), bytes(b)
    if kind == 1:
        at = offset()
        v = rng.choice(_BOUNDARY) if rng.random() < 0.5 else rng.randrange(256)
        b[at] = v
        return f"byte {at} set to {v:#04x}", bytes(b)
    if kind == 2:
        at, n = offset(), rng.randrange(1, 17)
        b[at:at + n] = bytes(rng.randrange(256) for _ in range(min(n, len(b) - at)))
        return f"{n} bytes at {at} overwritten", bytes(b)
    if kind == 3:
        at = offset()
        n = rng.randrange(1, max(2, min(256, len(b) - at + 1)))
        chunk = b[at:at + n]
        to = rng.randrange(len(b) + 1)
        b[to:to] = chunk * rng.choice([1, 1, 2, 8])
        return f"{n} bytes at {at} repeated at {to}", bytes(b)
    if kind == 4:
        at = offset()
        n = rng.randrange(1, max(2, min(256, len(b) - at + 1)))
        del b[at:at + n]
        return f"{n} bytes at {at} deleted", bytes(b)
    if kind == 5:
        at, n = rng.randrange(len(b) + 1), rng.randrange(1, 33)
        b[at:at] = bytes(rng.randrange(256) for _ in range(n))
        return f"{n} random bytes inserted at {at}", bytes(b)
    # a length or size field: 2 or 4 bytes set to a boundary or a large value
    width = rng.choice([2, 4])
    if len(b) < width:
        return "one byte inverted", bytes([b[0] ^ 0xFF]) + bytes(b[1:])
    at = offset(width)
    v = rng.choice(_WIDE) if rng.random() < 0.7 else rng.randrange(1 << (8 * width))
    v &= (1 << (8 * width)) - 1
    order = rng.choice(["big", "little"])
    b[at:at + width] = v.to_bytes(width, order)
    return f"{width}-byte field at {at} set to {v:#x} ({order} endian)", bytes(b)


def mutations(data: bytes, rng: random.Random, count: int) -> Iterator[tuple[str, bytes]]:
    for _ in range(count):
        yield mutate(data, rng)


@dataclass
class FuzzStats:
    cases: int = 0
    ok: int = 0
    err: int = 0
    by_file: dict = field(default_factory=dict)


FUZZ_SEED = int(os.environ.get("MYLA_FUZZ_SEED", "945"))
FUZZ_CASES = int(os.environ.get("MYLA_FUZZ_CASES", "10000"))
# Where a failing case is kept, to run it again by hand.
FAILED_DIR = os.path.join(_REPO, "build", "fuzz-failures")


def fuzz_cases(files: list[str], seed: int = FUZZ_SEED, count: int = FUZZ_CASES,
               truncate: list[str] | None = None, limit: int = 512) -> Iterator[tuple[str, str, bytes]]:
    """(file, what was done, bytes): every truncation up to `limit` bytes of
    the files `truncate` (default: all), then `count` mutations spread over
    `files`, from `seed`."""
    for path in (files if truncate is None else truncate):
        with open(path, "rb") as fh:
            data = fh.read()
        for what, case in truncations(data, limit):
            yield path, what, case
    rng = random.Random(seed)
    datas = {}
    for i in range(count):
        path = files[i % len(files)]
        if path not in datas:
            with open(path, "rb") as fh:
                datas[path] = fh.read()
        what, case = mutate(datas[path], rng)
        yield path, f"mutation {i}: {what}", case


def fuzz(driver: Driver, files: list[str], tmp: str, seed: int = FUZZ_SEED, count: int = FUZZ_CASES,
         truncate: list[str] | None = None, limit: int = 512, batch: int = 2000) -> FuzzStats:
    """Every case of `fuzz_cases` run through `driver`: each must print `ok`
    or `err`. A failure raises AssertionError naming the seed, the file, the
    mutation and the case's copy under build/fuzz-failures/."""
    stats = FuzzStats()
    cases = fuzz_cases(files, seed, count, truncate, limit)
    while True:
        chunk = []
        for path, what, data in cases:
            name = os.path.join(tmp, f"case{len(chunk)}")
            with open(name, "wb") as fh:
                fh.write(data)
            chunk.append((path, what, name))
            if len(chunk) == batch:
                break
        if not chunk:
            return stats
        try:
            results = driver.run([(name, None) for _, _, name in chunk])
            bad = next(((i, r.line) for i, r in enumerate(results) if r.kind not in ("ok", "err")), None)
        except DriverFailed as e:
            bad = (e.index, e.stderr.strip()[-1500:] or str(e))
            results = []
        if bad is not None:
            i, why = bad
            path, what, name = chunk[min(i, len(chunk) - 1)]
            os.makedirs(FAILED_DIR, exist_ok=True)
            keep = os.path.join(FAILED_DIR, f"{os.path.basename(path)}-seed{seed}-case{stats.cases + i}")
            shutil.copyfile(name, keep)
            raise AssertionError(
                f"fuzz case {stats.cases + i} (MYLA_FUZZ_SEED={seed}) of {os.path.relpath(path, _REPO)}, "
                f"{what}: {why}\n  the case: {keep}\n  run it: echo {keep} | {' '.join(driver.argv)}")
        for (path, _, _), r in zip(chunk, results):
            stats.cases += 1
            key = os.path.relpath(path, DATA)
            stats.by_file[key] = stats.by_file.get(key, 0) + 1
            if r.kind == "ok":
                stats.ok += 1
            else:
                stats.err += 1
