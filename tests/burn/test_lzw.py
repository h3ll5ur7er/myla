"""Burn tests: std.compress's LZW (GIF and TIFF) and PackBits (MYLA-932).

The corpus in `tests/burn/data/lzw/` holds LZW streams of GIF images written
by Pillow (minimum code size 8) and ImageMagick (2 to 8), the LZW and
PackBits strips of TIFF images written by Pillow (libtiff) and ffmpeg, each
with the bytes it stands for (`manifest.json`; the outputs zlib-compressed).
`python3 -m tests.burn.test_lzw --vendor` makes it again, with Pillow,
`convert` and `ffmpeg`; the tests need none of them.

A Myla driver, built natively (plain and `--checked`), decodes the corpus;
encodes random, repetitive and textual data, which its own decoders and an
independent decoder written here in Python must give back (and Pillow too,
inside a GIF or TIFF file, when it is installed); and decodes truncated and
mutated streams, where it must give what the Python decoder gives (the same
bytes, or the same error), the two builds alike, never a runtime error. A
few cases run on the interpreter.

`python3 -m tests.burn.test_lzw --bench` prints the native speed.
"""
from __future__ import annotations

import io
import json
import os
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

from ._native import CAN_BUILD_NATIVE, SKIP_REASON
from ._tools import STDLIB_ROOT, selfhost_tool

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "lzw")

# the driver's operations
GIF_DECODE, GIF_ENCODE, TIFF_DECODE, TIFF_ENCODE, PB_DECODE, PB_ENCODE = range(6)
BENCH_GIF, BENCH_TIFF, BENCH_PB = 6, 7, 8
ALL = 0x7FFFFFFF

DRIVER = r"""import std.compress as compress
import std.io as io
import std.process as process
import std.time as time
from std.io import Read, Write
from std.compress import CompressError

// Records on stdin: an operation (a byte), the minimum code size (a byte),
// max_output and the data's length (uint32, little-endian), the data. One
// answer each on stdout: 0 and the output, or 1 and the error's message,
// its length first (uint32).

fun u32_at(b: [uint8], p: int) -> int {
    return (b[p] as int) | ((b[p + 1] as int) << 8) | ((b[p + 2] as int) << 16) | ((b[p + 3] as int) << 24)
}

struct Out {
    b: [uint8],
}

impl Out {
    fun answer(var self, status: int, data: [uint8]) {
        self.b.push(status as uint8)
        let n = data.len()
        for k in 0..4 { self.b.push(((n >> (8 * k)) & 255) as uint8) }
        for x in data { self.b.push(x) }
    }

    fun result(var self, r: Result<[uint8], CompressError>) {
        match r {
            Ok(v) => self.answer(0, v)
            Err(e) => self.answer(1, e.message().bytes())
        }
    }
}

fun decode(op: int, mcs: int, most: int, data: [uint8]) -> Result<[uint8], CompressError> {
    if op == 0 { return compress.lzw_decode_gif(data, mcs, most) }
    if op == 2 { return compress.lzw_decode_tiff(data, most) }
    return compress.packbits_decode(data, most)
}

fun encode(op: int, mcs: int, data: [uint8]) -> [uint8] {
    if op == 1 { return compress.lzw_encode_gif(data, mcs) }
    if op == 3 { return compress.lzw_encode_tiff(data) }
    return compress.packbits_encode(data)
}

// The best of `runs` times of each way through `data` (op 6: GIF with
// `mcs`; 7: TIFF; 8: PackBits), in microseconds, as text.
fun bench(op: int, mcs: int, data: [uint8], runs: int) -> str {
    let enc_op = (op - 6) * 2 + 1
    var packed: [uint8] = []
    var best_enc: int64 = 0
    var best_dec: int64 = 0
    var ok = true
    for r in 0..runs {
        let t0 = time.now_ns()
        packed = encode(enc_op, mcs, data)
        let t1 = time.now_ns()
        let back = decode(enc_op - 1, mcs, 0x7FFFFFFF, packed)
        let t2 = time.now_ns()
        if back != Ok(data) { ok = false }
        if r == 0 || t1 - t0 < best_enc { best_enc = t1 - t0 }
        if r == 0 || t2 - t1 < best_dec { best_dec = t2 - t1 }
    }
    return f"{data.len()} {packed.len()} {best_enc / 1000} {best_dec / 1000} {ok}\n"
}

fun main() {
    let read = io.read_all(io.fd_stream(0))
    if read.is_err() {
        io.eprintln("error: can't read stdin")
        process.exit(1)
    }
    let input = read.unwrap_or([])
    var out = Out { b: [] }
    var p = 0
    while p + 10 <= input.len() {
        let op = input[p] as int
        let mcs = input[p + 1] as int
        let most = u32_at(input, p + 2)
        let n = u32_at(input, p + 6)
        let data = input[p + 10:p + 10 + n]
        p += 10 + n
        if op == 0 || op == 2 || op == 4 {
            out.result(decode(op, mcs, most, data))
        } else if op == 1 || op == 3 || op == 5 {
            out.answer(0, encode(op, mcs, data))
        } else {
            out.answer(0, bench(op, mcs, data, most).bytes())
        }
    }
    var w = io.fd_stream(1)
    var at = 0
    while at < out.b.len() {
        match w.write(out.b[at:]) {
            Ok(k) => { at += k }
            Err(_) => process.exit(3)
        }
    }
}
"""

# CompressError's messages
TRUNCATED = "compressed data ends too early"
BAD_CODE = "invalid code"
BAD_CODE_SIZE = "invalid LZW minimum code size"
TOO_LARGE = "output longer than max_output"


# --- reference decoders, written from the specifications -------------------------

def ref_lzw(data: bytes, mcs: int, lsb: bool, early: int, max_output: int = ALL) -> tuple[bool, bytes | str]:
    """(True, output) or (False, message), by GIF89a's LZW (`lsb`, early 0) or
    TIFF 6.0's (MSB-first, early 1): entries as strings, a full table kept,
    the end of the input an end of the data."""
    if not 1 <= mcs <= 8:
        return False, BAD_CODE_SIZE
    clear = 1 << mcs
    end = clear + 1
    width = mcs + 1
    nxt = end + 1
    table: dict[int, bytes] = {}
    prev: bytes | None = None
    out = bytearray()
    acc = 0
    nbits = 0
    pos = 0
    while True:
        while nbits < width and pos < len(data):
            if lsb:
                acc |= data[pos] << nbits
            else:
                acc = (acc << 8) | data[pos]
            pos += 1
            nbits += 8
        if nbits < width:
            break
        nbits -= width
        if lsb:
            code = acc & ((1 << width) - 1)
            acc >>= width
        else:
            code = (acc >> nbits) & ((1 << width) - 1)
            acc &= (1 << nbits) - 1
        if code == end:
            break
        if code == clear:
            width, nxt, prev, table = mcs + 1, end + 1, None, {}
            continue
        if code < clear:
            s = bytes([code])
        elif code < nxt:
            s = table[code]
        elif code == nxt and prev is not None:
            s = prev + prev[:1]
        else:
            return False, BAD_CODE
        if len(out) + len(s) > max_output:
            return False, TOO_LARGE
        out += s
        if prev is not None and nxt < 4096:
            table[nxt] = prev + s[:1]
            nxt += 1
        if nxt >= (1 << width) - early and width < 12:
            width += 1
        prev = s
    return True, bytes(out)


def ref_gif(data: bytes, mcs: int, max_output: int = ALL):
    return ref_lzw(data, mcs, True, 0, max_output)


def ref_tiff(data: bytes, max_output: int = ALL):
    if len(data) >= 2 and data[0] == 0 and data[1] & 1:
        return ref_lzw(data, 8, True, 0, max_output)   # TIFF 5.0's old LZW, as libtiff detects it
    return ref_lzw(data, 8, False, 1, max_output)


def ref_packbits(data: bytes, max_output: int = ALL):
    out = bytearray()
    p = 0
    while p < len(data):
        n = data[p]
        p += 1
        if n < 128:
            if n + 1 > len(data) - p:
                return False, TRUNCATED
            if len(out) + n + 1 > max_output:
                return False, TOO_LARGE
            out += data[p:p + n + 1]
            p += n + 1
        elif n > 128:
            if p >= len(data):
                return False, TRUNCATED
            if len(out) + 257 - n > max_output:
                return False, TOO_LARGE
            out += bytes([data[p]]) * (257 - n)
            p += 1
    return True, bytes(out)


def reference(op: int, mcs: int, data: bytes, max_output: int = ALL):
    if op == GIF_DECODE:
        return ref_gif(data, mcs, max_output)
    if op == TIFF_DECODE:
        return ref_tiff(data, max_output)
    return ref_packbits(data, max_output)


# --- the corpus ---------------------------------------------------------------------

def gif_streams(data: bytes) -> list[tuple[int, bytes, bool]]:
    """(minimum code size, LZW data, interlaced) of each image of the GIF file
    `data`."""
    out = []
    p = 6 + 7
    if data[10] & 0x80:
        p += 3 << ((data[10] & 7) + 1)
    while p < len(data):
        kind = data[p]
        if kind == 0x3B:
            break
        if kind == 0x21:
            p += 2
            while data[p]:
                p += data[p] + 1
            p += 1
            continue
        assert kind == 0x2C, kind
        flags = data[p + 9]
        p += 10
        if flags & 0x80:
            p += 3 << ((flags & 7) + 1)
        mcs = data[p]
        p += 1
        lzw = bytearray()
        while data[p]:
            lzw += data[p + 1:p + 1 + data[p]]
            p += data[p] + 1
        p += 1
        out.append((mcs, bytes(lzw), bool(flags & 0x40)))
    return out


def stored_order(px: bytes, w: int, h: int, interlaced: bool) -> bytes:
    """The rows of `px` in the order a GIF stores them: an interlaced image's
    every 8th row from 0, every 8th from 4, every 4th from 2, every 2nd from 1."""
    if not interlaced:
        return px
    rows = [y for start, step in ((0, 8), (4, 8), (2, 4), (1, 2)) for y in range(start, h, step)]
    return b"".join(px[y * w:(y + 1) * w] for y in rows)


def tiff_strips(path: str):
    """(compression, [strip bytes], [what each strip stands for]) of the TIFF
    file `path`, read with Pillow (its pixels split by strip)."""
    from PIL import Image
    with open(path, "rb") as fh:
        raw = fh.read()
    im = Image.open(path)
    tags = im.tag_v2
    offsets, counts = tags[273], tags[279]
    rows = tags.get(278, im.size[1])
    pixels = im.tobytes()
    row_bytes = len(pixels) // im.size[1]
    strips = [raw[o:o + c] for o, c in zip(offsets, counts)]
    wants = [pixels[i * rows * row_bytes:(i + 1) * rows * row_bytes] for i in range(len(strips))]
    return tags[259], strips, wants


def picture(w: int, h: int, seed: int, colours: int = 256) -> bytes:
    """A smooth picture with shapes and a little noise, `colours` levels."""
    rng = random.Random(seed)
    out = bytearray()
    for y in range(h):
        for x in range(w):
            v = (x * 3 + y * 2) // 4 + (40 if (x - w // 2) ** 2 + (y - h // 3) ** 2 < (w // 4) ** 2 else 0)
            if rng.random() < 0.05:
                v += rng.randrange(-20, 21)
            out.append(v * colours // 256 % colours)
    return bytes(out)


def vendor(out_dir: str = DATA) -> None:
    """The corpus made again, from images written by Pillow, ImageMagick and
    ffmpeg."""
    from PIL import Image
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)
    manifest = []
    rng = random.Random(932)

    def add(name: str, kind: str, mcs: int, stream: bytes, want: bytes, producer: str) -> None:
        op = {"gif": GIF_DECODE, "tiff": TIFF_DECODE, "packbits": PB_DECODE}[kind]
        ok, got = reference(op, mcs, stream)
        assert ok and got == want, f"{name}: the reference decoder disagrees"
        with open(os.path.join(out_dir, name + ".bin"), "wb") as fh:
            fh.write(stream)
        with open(os.path.join(out_dir, name + ".out.z"), "wb") as fh:
            fh.write(zlib.compress(want, 9))
        manifest.append({"name": name, "kind": kind, "min_code_size": mcs, "producer": producer,
                         "length": len(want)})

    tmp = tempfile.mkdtemp()
    try:
        # GIF: Pillow (always 8 bits), indexed pictures of several sizes
        gifs = {
            "pillow_noise_64": (64, 64, bytes(rng.randrange(256) for _ in range(64 * 64))),
            "pillow_picture_200x150": (200, 150, picture(200, 150, 1)),
            "pillow_picture_16_160x160": (160, 160, picture(160, 160, 2, 16)),
            "pillow_flat_200x100": (200, 100, bytes(200 * 100)),
            "pillow_1x1": (1, 1, b"\x05"),
        }
        for name, (w, h, px) in gifs.items():
            im = Image.frombytes("P", (w, h), px)
            im.putpalette(bytes(range(256)) * 3)
            path = os.path.join(tmp, name + ".gif")
            im.save(path, optimize=False, interlace=w != 200)
            frames = gif_streams(open(path, "rb").read())
            assert len(frames) == 1
            mcs, lzw, interlaced = frames[0]
            assert Image.open(path).tobytes() == px, name
            add("gif_" + name, "gif", mcs, lzw, stored_order(px, w, h, interlaced), "Pillow " + Image.__version__)
        # GIF: ImageMagick, 2 to 256 colours (minimum code sizes 2 to 8)
        for colours in (2, 4, 16, 64, 256):
            src = os.path.join(tmp, f"src{colours}.png")
            Image.frombytes("L", (240, 160), picture(240, 160, colours)).save(src)
            path = os.path.join(tmp, f"im{colours}.gif")
            subprocess.run(["convert", src, "-colors", str(colours), "+dither", path], check=True)
            mcs, lzw, interlaced = gif_streams(open(path, "rb").read())[0]
            im = Image.open(path)
            add(f"gif_imagemagick_{colours}", "gif", mcs, lzw, stored_order(im.tobytes(), 240, 160, interlaced),
                "ImageMagick 6.9")
        # TIFF: Pillow (libtiff) LZW and PackBits, ffmpeg LZW and PackBits
        images = {
            "gray_200x120": Image.frombytes("L", (200, 120), picture(200, 120, 3)),
            "rgb_160x100": Image.merge("RGB", [Image.frombytes("L", (160, 100), picture(160, 100, s)) for s in (4, 5, 6)]),
            "rgbnoise_64x48": Image.frombytes("RGB", (64, 48), bytes(rng.randrange(256) for _ in range(64 * 48 * 3))),
            "bilevel_203x101": Image.frombytes("L", (203, 101), picture(203, 101, 7)).point(lambda v: 255 * (v > 100)).convert("1"),
        }
        for name, im in images.items():
            for comp, kind in (("tiff_lzw", "tiff"), ("packbits", "packbits")):
                path = os.path.join(tmp, f"{name}_{comp}.tif")
                im.save(path, compression=comp)
                _, strips, wants = tiff_strips(path)
                for i, (s, want) in enumerate(zip(strips, wants)):
                    if i < 3 or i == len(strips) - 1:
                        add(f"tiff_pillow_{name}_{kind}_{i}", kind, 8, s, want, "Pillow (libtiff)")
            if im.mode != "1":
                src = os.path.join(tmp, name + ".png")
                im.save(src)
                for algo, kind in (("lzw", "tiff"), ("packbits", "packbits")):
                    path = os.path.join(tmp, f"{name}_ffmpeg_{algo}.tif")
                    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", src, "-compression_algo", algo,
                                    path], check=True)
                    _, strips, wants = tiff_strips(path)
                    for i, (s, want) in enumerate(zip(strips, wants)):
                        if i < 3 or i == len(strips) - 1:
                            add(f"tiff_ffmpeg_{name}_{kind}_{i}", kind, 8, s, want, "ffmpeg")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1)
        fh.write("\n")


def corpus() -> list[dict]:
    with open(os.path.join(DATA, "manifest.json"), encoding="utf-8") as fh:
        cases = json.load(fh)
    for c in cases:
        with open(os.path.join(DATA, c["name"] + ".bin"), "rb") as fh:
            c["stream"] = fh.read()
        with open(os.path.join(DATA, c["name"] + ".out.z"), "rb") as fh:
            c["want"] = zlib.decompress(fh.read())
        c["op"] = {"gif": GIF_DECODE, "tiff": TIFF_DECODE, "packbits": PB_DECODE}[c["kind"]]
    return cases


# --- inputs for the encoders ------------------------------------------------------------

def inputs(rng: random.Random) -> dict[str, bytes]:
    text = b""
    for root in ("docs", "lib/std"):
        for dirpath, _, files in sorted(os.walk(os.path.join(_REPO, root))):
            for f in sorted(files):
                if len(text) < 300_000:
                    with open(os.path.join(dirpath, f), "rb") as fh:
                        text += fh.read()
    return {
        "empty": b"",
        "one": b"\x07",
        "two": b"\x07\x07",
        "random_10": bytes(rng.randrange(256) for _ in range(10)),
        "random_70000": bytes(rng.randrange(256) for _ in range(70000)),
        "zeros_200000": bytes(200000),
        "runs": b"".join(bytes([rng.randrange(256)]) * rng.choice((1, 2, 3, 127, 128, 129, 300)) for _ in range(2000)),
        "periodic": b"".join(bytes(range(p)) * (5000 // p) for p in (1, 2, 3, 17, 255, 256)),
        "text": text[:300_000],
        "picture": picture(512, 384, 9),
        "pairs": b"".join(bytes([a, a]) + bytes([rng.randrange(256)]) for a in range(256)) * 3,
    }


def gif_file(lzw: bytes, mcs: int, w: int, h: int) -> bytes:
    """A GIF file of one image of `w`×`h` indices, the LZW data `lzw`."""
    out = bytearray(b"GIF89a" + struct.pack("<HHBBB", w, h, 0x80 | (mcs - 1), 0, 0))
    out += b"".join(bytes([i, i, i]) for i in range(1 << mcs))
    out += b"\x2c" + struct.pack("<HHHHB", 0, 0, w, h, 0) + bytes([mcs])
    for i in range(0, len(lzw), 255):
        piece = lzw[i:i + 255]
        out += bytes([len(piece)]) + piece
    return bytes(out + b"\x00\x3b")


def tiff_file(strip: bytes, compression: int, w: int, h: int) -> bytes:
    """A little-endian TIFF of one 8-bit grey strip."""
    entries = [(256, 3, 1, w), (257, 3, 1, h), (258, 3, 1, 8), (259, 3, 1, compression), (262, 3, 1, 1),
               (273, 4, 1, 8), (277, 3, 1, 1), (278, 3, 1, h), (279, 4, 1, len(strip))]
    ifd = struct.pack("<H", len(entries))
    for tag, typ, count, value in entries:
        ifd += struct.pack("<HHII", tag, typ, count, value) if typ == 4 else struct.pack("<HHIHH", tag, typ, count, value, 0)
    ifd += struct.pack("<I", 0)
    return b"II*\x00" + struct.pack("<I", 8 + len(strip)) + strip + ifd


def records(cases) -> bytes:
    out = bytearray()
    for op, mcs, most, data in cases:
        out += struct.pack("<BBII", op, mcs, most, len(data)) + data
    return bytes(out)


def answers(data: bytes) -> list[tuple[bool, bytes | str]]:
    out = []
    p = 0
    while p < len(data):
        status, n = struct.unpack_from("<BI", data, p)
        body = data[p + 5:p + 5 + n]
        out.append((True, body) if status == 0 else (False, body.decode()))
        p += 5 + n
    return out


def build_driver(tmp: str) -> tuple[str, str, str]:
    path = os.path.join(tmp, "driver.my")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(DRIVER)
    plain = os.path.join(tmp, "driver")
    checked = os.path.join(tmp, "driver-checked")
    for exe, flags in ((plain, []), (checked, ["--checked"])):
        subprocess.run([selfhost_tool("main"), "build", path, "-o", exe, "--stdlib", STDLIB_ROOT, *flags],
                       capture_output=True, check=True)
    return path, plain, checked


class LzwTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.mkdtemp()
        cls.path = None
        if CAN_BUILD_NATIVE:
            cls.path, cls.native, cls.checked = build_driver(cls.tmp)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_driver(self, cases, exes=None) -> list[tuple[bool, bytes | str]]:
        """The driver's answers to `cases`, each build in `exes` alike."""
        got = None
        for exe in exes or (self.native, self.checked):
            argv = [exe] if exe != "interpreter" else [selfhost_tool("main"), "run", self.path, "--stdlib",
                                                       STDLIB_ROOT]
            proc = subprocess.run(argv, input=records(cases), capture_output=True, timeout=600)
            self.assertEqual(proc.returncode, 0, proc.stderr.decode(errors="replace")[-2000:])
            mine = answers(proc.stdout)
            self.assertEqual(len(mine), len(cases))
            if got is not None:
                self.assertTrue(got == mine, f"{exe} differs")
            got = mine
        return got

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_corpus_natively(self) -> None:
        cases = corpus()
        self.assertGreater(len(cases), 25)
        kinds = {c["kind"] for c in cases}
        self.assertEqual(kinds, {"gif", "tiff", "packbits"})
        got = self.run_driver([(c["op"], c["min_code_size"], ALL, c["stream"]) for c in cases])
        for c, (ok, out) in zip(cases, got):
            with self.subTest(c["name"]):
                self.assertTrue(ok, out)
                self.assertTrue(out == c["want"], f"{len(out)} bytes, not {len(c['want'])}")
        # max_output at the output's length, and one byte below it
        got = self.run_driver([(c["op"], c["min_code_size"], len(c["want"]) - d, c["stream"])
                               for c in cases for d in (0, 1)])
        for i, c in enumerate(cases):
            self.assertEqual(got[2 * i], (True, c["want"]), c["name"])
            self.assertEqual(got[2 * i + 1], (False, TOO_LARGE), c["name"])

    def check_encoders(self, data: dict[str, bytes], exes=None) -> tuple[list, list]:
        cases = []
        for name, b in data.items():
            cases.append((GIF_ENCODE, 8, 0, b))
            cases.append((TIFF_ENCODE, 0, 0, b))
            cases.append((PB_ENCODE, 0, 0, b))
            for mcs in (2, 3, 5, 7):
                cases.append((GIF_ENCODE, mcs, 0, bytes(x & ((1 << mcs) - 1) for x in b)))
        encoded = self.run_driver(cases, exes)
        back = self.run_driver([(op - 1, mcs, ALL, out) for (op, mcs, _, _), (_, out) in zip(cases, encoded)], exes)
        for (op, mcs, _, b), (_, packed), got in zip(cases, encoded, back):
            with self.subTest(op=op, mcs=mcs, n=len(b)):
                self.assertTrue(got == (True, b), "the driver's decoder")
                self.assertTrue(reference(op - 1, mcs, packed) == (True, b), "the Python decoder")
                if op == PB_ENCODE:
                    self.assertLessEqual(len(packed), len(b) + (len(b) + 127) // 128)
        return cases, encoded

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_encoders_natively(self) -> None:
        data = inputs(random.Random(1))
        cases, encoded = self.check_encoders(data)
        # sizes: text and pictures shrink, a long run to almost nothing
        sizes = {(op, mcs, len(b)): len(out) for (op, mcs, _, b), (_, out) in zip(cases, encoded)}
        self.assertLess(sizes[(GIF_ENCODE, 8, len(data["text"]))], len(data["text"]) * 0.6)
        self.assertLess(sizes[(TIFF_ENCODE, 0, len(data["picture"]))], len(data["picture"]) * 0.6)
        self.assertLess(sizes[(TIFF_ENCODE, 0, 200000)], 2000)
        self.assertLess(sizes[(PB_ENCODE, 0, 200000)], 3200)
        try:
            from PIL import Image
        except ImportError:
            return
        # Pillow reads them inside a GIF and a TIFF file
        checked = 0
        for (op, mcs, _, b), (_, packed) in zip(cases, encoded):
            if len(b) == 0:
                continue
            w, h = (len(b), 1) if len(b) <= 65535 else (256, len(b) // 256)
            if w * h != len(b):
                continue
            with self.subTest(op=op, mcs=mcs, n=len(b)):
                if op == GIF_ENCODE:
                    im = Image.open(io.BytesIO(gif_file(packed, mcs, w, h)))
                else:
                    im = Image.open(io.BytesIO(tiff_file(packed, 5 if op == TIFF_ENCODE else 32773, w, h)))
                self.assertTrue(im.tobytes() == b, "Pillow")
                checked += 1
        self.assertGreater(checked, 40)

    def test_encoders_interpreted(self) -> None:
        if self.path is None:
            self.skipTest(SKIP_REASON)
        rng = random.Random(2)
        self.check_encoders({"random": bytes(rng.randrange(256) for _ in range(3000)), "runs": bytes(5000),
                             "text": b"to be or not to be, " * 100}, exes=["interpreter"])

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_fuzz_natively(self) -> None:
        """Truncated and mutated streams: the Python decoder's answer, in both
        builds, never a runtime error."""
        rng = random.Random(932)
        seeds = [(c["op"], c["min_code_size"], c["stream"]) for c in corpus()]
        cases = []
        for i in range(3000):
            op, mcs, s = rng.choice(seeds)
            if len(s) > 4000:
                s = s[:rng.randrange(1, 4000)]
            s = bytearray(s)
            how = rng.randrange(6)
            if how == 0 and s:
                s = s[:rng.randrange(len(s))]
            elif how == 1 and s:
                for _ in range(rng.randrange(1, 4)):
                    s[rng.randrange(len(s))] ^= 1 << rng.randrange(8)
            elif how == 2 and s:
                for _ in range(rng.randrange(1, 9)):
                    s[rng.randrange(len(s))] = rng.randrange(256)
            elif how == 3:
                at = rng.randrange(len(s) + 1)
                s[at:at] = bytes(rng.randrange(256) for _ in range(rng.randrange(1, 5)))
            elif how == 4:
                s = bytearray(rng.randrange(256) for _ in range(rng.randrange(0, 600)))
            else:
                mcs = rng.randrange(0, 11) if op == GIF_DECODE else mcs
            most = rng.choice((ALL, ALL, rng.randrange(0, 5000)))
            cases.append((op, mcs, most, bytes(s)))
        got = self.run_driver(cases)
        kinds = set()
        for (op, mcs, most, s), answer in zip(cases, got):
            want = reference(op, mcs, s, most)
            kinds.add((op, want[0] or want[1]))
            if answer != want:
                self.fail(f"op {op}, mcs {mcs}, max {most}, {s.hex()}: {answer!r:.200}, not {want!r:.200}")
        # every outcome is among them
        for op in (GIF_DECODE, TIFF_DECODE):
            for outcome in (True, BAD_CODE, TOO_LARGE):
                self.assertIn((op, outcome), kinds)
        self.assertIn((GIF_DECODE, BAD_CODE_SIZE), kinds)
        for outcome in (True, TRUNCATED, TOO_LARGE):
            self.assertIn((PB_DECODE, outcome), kinds)


def bench() -> None:
    """The best of five times of each, natively, on a few MB."""
    tmp = tempfile.mkdtemp()
    try:
        _, exe, _ = build_driver(tmp)
        data = inputs(random.Random(3))
        sets = {
            "picture 4 MB": picture(2048, 2048, 4),
            "text 4 MB": (data["text"] * 14)[:4_000_000],
            "random 4 MB": random.Random(4).randbytes(4_000_000),
            "zeros 4 MB": bytes(4_000_000),
        }
        for name, b in sets.items():
            cases = [(BENCH_GIF, 8, 5, b), (BENCH_TIFF, 8, 5, b), (BENCH_PB, 0, 5, b)]
            proc = subprocess.run([exe], input=records(cases), capture_output=True, check=True)
            for label, (_, line) in zip(("GIF LZW", "TIFF LZW", "PackBits"), answers(proc.stdout)):
                n, packed, enc, dec, ok = line.decode().split()
                mb = int(n) / 1e6
                print(f"{name:14} {label:9} {int(packed) / int(n) * 100:6.1f} %  encode {int(enc) / 1000:7.1f} ms "
                      f"({mb / (int(enc) / 1e6):6.1f} MB/s)  decode {int(dec) / 1000:7.1f} ms "
                      f"({mb / (int(dec) / 1e6):6.1f} MB/s)  {ok}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    if sys.argv[1:] == ["--vendor"]:
        vendor()
    elif sys.argv[1:] == ["--bench"]:
        bench()
    else:
        unittest.main()
