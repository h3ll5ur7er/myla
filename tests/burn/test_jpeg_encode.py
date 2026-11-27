"""Burn tests: std.jpeg's encoder (MYLA-963). Its decoder is tested over the
image corpus by test_images.py (`JpegDecoder`).

A driver (`tests/burn/drivers/jpeg_encode.my`) encodes an image (a PAM file,
or benchmarks/images_std.my's picture), writes the file and reads it back
with std.jpeg's decoder; it answers with the file's SHA-256, the decoded
samples' and their PSNR against the image. The images:

- every 8-bit still image of the corpus (MYLA-971) with its pixels, at
  quality 75 and each subsampling (gray ones once);
- its photo-like JPEG images at qualities 50, 75, 90 and 95, each
  subsampling;
- one colour and one gray image at every quality from 1 to 100;
- generated images of odd sizes (1x1, a row, a column, partial MCUs) in
  each layout (gray + alpha and RGBA lose their alpha);
- the 12-megapixel picture of benchmarks/images_std.my at quality 85 in each
  subsampling and at 50, 75, 90 and 95 in 4:2:0.

Each file must be the one Pillow (libjpeg-turbo, `optimize` off, not
progressive) writes for the same pixels, quality and subsampling, byte for
byte: the SHA-256 and size of Pillow's files are vendored in
`tests/burn/data/jpeg_encode.json`, so CI needs no Pillow
(`python3 -m tests.burn.test_jpeg_encode --vendor` makes it again, with
Pillow and numpy). The photo-like images and the 12-megapixel picture also
check what the task asks of an encoder that isn't exact: a PSNR within
0.5 dB of Pillow's and a size within 10 %. Some cases run again built
`--checked` and in the interpreter. With Pillow installed, Pillow decodes
every file to the samples our decoder gives, Pillow's own encoder is asked
again (in case the vendored file is stale), and 300 random images of random
sizes, layouts, qualities and subsamplings are compared with it.
"""
from __future__ import annotations

import functools
import hashlib
import io
import json
import os
import random
import subprocess
import sys
import tempfile
import unittest
from dataclasses import dataclass

from tests.burn import _images as im
from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
VENDORED = os.path.join(_REPO, "tests", "burn", "data", "jpeg_encode.json")
SUBSAMPLINGS = ("444", "422", "420")
PILLOW_SUBSAMPLING = {"444": 0, "422": 1, "420": 2}
PHOTO = (4000, 3000)
SHA_DIGITS = 16
ODD_SIZES = [(1, 1), (1, 9), (9, 1), (2, 2), (3, 5), (7, 7), (8, 8), (9, 9), (15, 17), (16, 16),
             (17, 15), (23, 31), (33, 8), (8, 33), (40, 1)]


def _has_pillow() -> bool:
    try:
        import numpy  # noqa: F401
        from PIL import Image  # noqa: F401
        return True
    except ImportError:
        return False


@dataclass
class Case:
    name: str           # the key in the vendored file
    source: str         # `corpus:<path>`, `gen:<w>x<h>:<layout>` or `photo:<w>x<h>`
    quality: int
    sub: str            # 444, 422 or 420
    group: str          # corpus, photo-like, quality, odd, 12mp


def _corpus_entries() -> list[dict]:
    return [e for e in im.entries(None, "ok")
            if e.get("pam") and e["bits"] == 8 and e.get("frames", 1) == 1]


def _photo_like() -> list[dict]:
    return [e for e in _corpus_entries() if e["format"] == "jpeg" and e["layout"] == "rgb"
            and os.path.basename(e["path"]).split("-")[0] in ("photo", "gradient", "noise", "edges", "text")]


def cases() -> list[Case]:
    out = []
    for e in _corpus_entries():
        subs = SUBSAMPLINGS if e["layout"] in ("rgb", "rgba") else ("420",)
        for s in subs:
            out.append(Case(f"corpus {e['path']} q75 {s}", f"corpus:{e['path']}", 75, s, "corpus"))
    for e in _photo_like():
        for q in (50, 75, 90, 95):
            for s in SUBSAMPLINGS:
                out.append(Case(f"photo-like {e['path']} q{q} {s}", f"corpus:{e['path']}", q, s, "photo-like"))
    for path in ("jpeg/photo-q95-s444.jpg", "jpeg/gray-q80.jpg"):
        for q in range(1, 101):
            out.append(Case(f"quality {path} q{q}", f"corpus:{path}", q, "420", "quality"))
    for (w, h) in ODD_SIZES:
        for layout in ("gray", "gray+alpha", "rgb", "rgba"):
            for s in (SUBSAMPLINGS if layout in ("rgb", "rgba") else ("420",)):
                out.append(Case(f"odd {w}x{h} {layout} q85 {s}", f"gen:{w}x{h}:{layout}", 85, s, "odd"))
    w, h = PHOTO
    for s in SUBSAMPLINGS:
        out.append(Case(f"12mp q85 {s}", f"photo:{w}x{h}", 85, s, "12mp"))
    for q in (50, 75, 90, 95):
        out.append(Case(f"12mp q{q} 420", f"photo:{w}x{h}", q, "420", "12mp"))
    return out


def generated(w: int, h: int, layout: str) -> im.Pixels:
    """An image of `w` by `h` in `layout`: smooth ramps, a pattern of x and
    y, and an alpha that isn't constant."""
    ch = im.LAYOUTS[layout][0]
    raw = bytearray()
    for y in range(h):
        for x in range(w):
            for c in range(ch):
                raw.append((x * (40 + 20 * c) // max(w, 1) + y * 150 // max(h, 1) + ((x * 7 + y * 13 + c * 5) % 17) * 5 + 30 * c) % 256)
    return im.from_bytes(w, h, layout, 8, bytes(raw))


@functools.lru_cache(maxsize=None)
def _by_path() -> dict[str, dict]:
    return {e["path"]: e for e in im.entries()}


@functools.lru_cache(maxsize=None)
def pixels_of(source: str) -> im.Pixels | None:
    """The image a case's `source` names (None for the picture, which the
    driver makes)."""
    kind, _, rest = source.partition(":")
    if kind == "corpus":
        return im.expected(_by_path()[rest])
    if kind == "gen":
        size, layout = rest.split(":")
        w, h = (int(v) for v in size.split("x"))
        return generated(w, h, layout)
    return None


def vendored() -> dict:
    with open(VENDORED, encoding="utf-8") as fh:
        return json.load(fh)["cases"]


# -- Pillow (only to vendor, and in the tests that need it) ----------------------

def _pillow_image(source: str):
    from PIL import Image
    kind, _, rest = source.partition(":")
    if kind == "photo":
        sys.path.insert(0, os.path.join(_REPO, "benchmarks"))
        from images_pillow import photo
        w, h = (int(v) for v in rest.split("x"))
        return Image.fromarray(photo(w, h), "RGB")
    p = pixels_of(source)
    mode = {"gray": "L", "gray+alpha": "LA", "rgb": "RGB", "rgba": "RGBA"}[p.layout]
    img = Image.frombytes(mode, (p.width, p.height), bytes(p.samples))
    # JPEG holds no alpha: Pillow refuses LA and RGBA, std.jpeg drops it
    return img.getchannel(0) if mode == "LA" else img.convert("RGB") if mode == "RGBA" else img


def pillow_encode(img, quality: int, sub: str) -> bytes:
    buf = io.BytesIO()
    kw = {"subsampling": PILLOW_SUBSAMPLING[sub]} if img.mode != "L" else {}
    img.save(buf, "JPEG", quality=quality, optimize=False, progressive=False, **kw)
    return buf.getvalue()


def pillow_psnr(img, data: bytes) -> float:
    import numpy as np
    from PIL import Image
    a = np.asarray(img, dtype=np.float64)
    b = np.asarray(Image.open(io.BytesIO(data)), dtype=np.float64)
    mse = float(((a - b) ** 2).mean())
    return float("inf") if mse == 0 else 10 * np.log10(255.0 ** 2 / mse)


def vendor(out: str = VENDORED) -> None:
    from PIL import Image, features
    result = {}
    images = {}
    for c in cases():
        if c.source not in images:
            images = {c.source: _pillow_image(c.source)}     # one at a time: the picture is 36 MB
        img = images[c.source]
        data = pillow_encode(img, c.quality, c.sub)
        entry = [len(data), hashlib.sha256(data).hexdigest()[:SHA_DIGITS]]
        if c.group in ("photo-like", "12mp"):
            v = pillow_psnr(img, data)
            entry.append(None if v == float("inf") else round(v, 3))     # null: the same pixels
        result[c.name] = entry
    about = ("MYLA-963: for each case of tests/burn/test_jpeg_encode.py, the size of the JPEG file Pillow writes "
             f"(optimize off, not progressive), the first {SHA_DIGITS} hex digits of its SHA-256, and its PSNR for "
             "the photo-like ones. Made by `python3 -m tests.burn.test_jpeg_encode --vendor` with Pillow "
             f"{Image.__version__} (libjpeg-turbo {features.version('libjpeg_turbo')}).")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write('{"about": ' + json.dumps(about) + ',\n"cases": {\n')
        fh.write(",\n".join(f"{json.dumps(k)}: {json.dumps(v)}" for k, v in result.items()))
        fh.write("\n}}\n")


# -- the tests ---------------------------------------------------------------------

@dataclass
class Answer:
    size: int
    width: int
    height: int
    layout: str
    decoded: str
    psnr: float
    file: str


def parse(line: str) -> Answer:
    f = line.split()
    if len(f) != 8 or f[0] != "ok":
        raise AssertionError(f"the driver says {line!r}")
    return Answer(int(f[1]), int(f[2]), int(f[3]), f[4], f[5], float(f[6]), f[7])


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Encoder(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.argv = im.build_driver(im.driver_source("jpeg_encode"), cls.tmp.name)
        cls.inputs: dict[str, str] = {}
        cls.want = vendored()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def input_of(self, source: str) -> str:
        if source.startswith("photo:"):
            return source
        if source not in self.inputs:
            path = os.path.join(self.tmp.name, f"in{len(self.inputs)}.pam")
            im.write_pam(path, pixels_of(source))
            self.inputs[source] = path
        return self.inputs[source]

    def run_cases(self, items: list[Case], argv: list[str] | None = None) -> list[tuple[Case, str, Answer]]:
        """Each case through the driver: the file written and the answer,
        checked against the image's size and layout."""
        lines, outs = [], []
        for n, c in enumerate(items):
            out = os.path.join(self.tmp.name, f"out{n}.jpg")
            outs.append(out)
            lines.append(f"{self.input_of(c.source)}\t{out}\t{c.quality}\t{c.sub}\n")
        r = subprocess.run(argv or self.argv, input="".join(lines), capture_output=True, text=True, timeout=1200)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        answers = r.stdout.splitlines()
        self.assertEqual(len(answers), len(items), r.stderr[-2000:])
        result = []
        for c, out, line in zip(items, outs, answers):
            with self.subTest(c.name):
                a = parse(line)
                p = pixels_of(c.source)
                w, h, layout = (p.width, p.height, p.layout) if p else (*PHOTO, "rgb")
                self.assertEqual((a.width, a.height), (w, h))
                self.assertEqual(a.layout, "rgb" if layout in ("rgb", "rgba") else "gray")
                with open(out, "rb") as fh:
                    self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), a.file)
                result.append((c, out, a))
        return result

    def assert_pillow_s(self, c: Case, a: Answer) -> None:
        want = self.want.get(c.name)
        self.assertIsNotNone(want, f"{c.name} isn't vendored: run --vendor")
        self.assertEqual((a.size, a.file[:SHA_DIGITS]), (want[0], want[1]), f"{c.name}: not Pillow's bytes")

    def test_pillow_s_bytes_for_every_image(self) -> None:
        items = [c for c in cases() if c.group != "12mp"]
        self.assertGreater(len(items), 1000)
        for c, _, a in self.run_cases(items):
            with self.subTest(c.name):
                self.assert_pillow_s(c, a)

    def assert_psnr(self, a: Answer, want: list) -> None:
        # a JPEG image encoded again as it was made can give its pixels back
        if want[2] is None:
            self.assertEqual(a.psnr, float("inf"))
        else:
            self.assertGreater(a.psnr, want[2] - 0.5)

    def test_psnr_and_size_beside_pillow_s(self) -> None:
        items = [c for c in cases() if c.group == "photo-like"]
        for c, _, a in self.run_cases(items):
            with self.subTest(c.name):
                want = self.want[c.name]
                self.assert_psnr(a, want)
                self.assertLess(abs(a.size - want[0]), 0.1 * want[0])

    def test_12_megapixels(self) -> None:
        for c, _, a in self.run_cases([c for c in cases() if c.group == "12mp"]):
            with self.subTest(c.name):
                want = self.want[c.name]
                self.assert_pillow_s(c, a)
                self.assert_psnr(a, want)
                print(f"\n{c.name}: {a.size} bytes, {a.psnr} dB (Pillow's {want[0]} bytes, {want[2]} dB)", end="")

    def test_checked(self) -> None:
        argv = im.build_driver(im.driver_source("jpeg_encode"), self.tmp.name, checked=True)
        items = [c for c in cases() if c.group in ("odd", "quality")]
        items += [c for c in cases() if c.group == "corpus"][::7]
        for c, _, a in self.run_cases(items, argv):
            with self.subTest(c.name):
                self.assert_pillow_s(c, a)

    def test_interpreted(self) -> None:
        names = {"odd 1x1 rgb q85 420", "odd 9x9 rgba q85 420", "odd 17x15 gray q85 420", "odd 15x17 rgb q85 422"}
        items = [c for c in cases() if c.name in names]
        self.assertEqual(len(items), len(names))
        for c, _, a in self.run_cases(items, im.interpreter_argv(im.driver_source("jpeg_encode"))):
            with self.subTest(c.name):
                self.assert_pillow_s(c, a)

    @unittest.skipUnless(_has_pillow(), "Pillow or numpy isn't installed")
    def test_pillow_reads_every_file_as_we_do(self) -> None:
        import numpy as np
        from PIL import Image
        items = [c for c in cases() if c.group != "12mp"]
        images = {}
        for c, out, a in self.run_cases(items):
            with self.subTest(c.name):
                with open(out, "rb") as fh:
                    data = fh.read()
                got = Image.open(io.BytesIO(data))
                got.load()
                self.assertEqual(hashlib.sha256(np.asarray(got).tobytes()).hexdigest(), a.decoded)
                if c.source not in images:
                    images = {c.source: _pillow_image(c.source)}
                self.assertEqual(data, pillow_encode(images[c.source], c.quality, c.sub), "not Pillow's bytes")

    @unittest.skipUnless(_has_pillow(), "Pillow or numpy isn't installed")
    def test_random_images_as_pillow_writes_them(self) -> None:
        from PIL import Image
        rng = random.Random(int(os.environ.get("MYLA_FUZZ_SEED", "937")))
        items, sources = [], {}
        for n in range(300):
            w, h = rng.randint(1, 48), rng.randint(1, 48)
            layout = rng.choice(["gray", "gray+alpha", "rgb", "rgba"])
            raw = bytes(rng.getrandbits(8) if rng.random() < 0.3 else (x * 5 + y * 3 + c * 40) % 256
                        for y in range(h) for x in range(w) for c in range(im.LAYOUTS[layout][0]))
            p = im.from_bytes(w, h, layout, 8, raw)
            source = f"random:{n}"
            path = os.path.join(self.tmp.name, f"random{n}.pam")
            im.write_pam(path, p)
            self.inputs[source] = path
            sources[source] = p
            sub = rng.choice(SUBSAMPLINGS) if layout in ("rgb", "rgba") else "420"
            items.append(Case(f"random {n}: {w}x{h} {layout}", source, rng.randint(1, 100), sub, "random"))
        lines, outs = [], []
        for n, c in enumerate(items):
            outs.append(os.path.join(self.tmp.name, f"rout{n}.jpg"))
            lines.append(f"{self.inputs[c.source]}\t{outs[-1]}\t{c.quality}\t{c.sub}\n")
        r = subprocess.run(self.argv, input="".join(lines), capture_output=True, text=True, timeout=600)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        for c, out, line in zip(items, outs, r.stdout.splitlines()):
            with self.subTest(c.name, quality=c.quality, sub=c.sub):
                parse(line)
                p = sources[c.source]
                mode = {"gray": "L", "gray+alpha": "LA", "rgb": "RGB", "rgba": "RGBA"}[p.layout]
                img = Image.frombytes(mode, (p.width, p.height), bytes(p.samples))
                img = img.getchannel(0) if mode == "LA" else img.convert("RGB") if mode == "RGBA" else img
                with open(out, "rb") as fh:
                    self.assertEqual(fh.read(), pillow_encode(img, c.quality, c.sub))


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--vendor":
        vendor()
        print(f"wrote {VENDORED}")
    else:
        unittest.main()
