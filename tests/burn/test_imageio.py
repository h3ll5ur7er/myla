"""Burn tests: `std.imageio` (MYLA-940) over the image corpus (MYLA-945).

Two drivers. `tests/burn/drivers/imageio.my` is `imageio.decode` under the
corpus's harness (`_images.py`): every file of every format, found by its
contents, must decode to the manifest's pixels (a GIF's first frame, a
TIFF's first page) natively, `--checked` and, the smallest of each format, in
the interpreter, and seeded mutations and truncations of files of every
format must give `Ok` or `Err`, never a runtime error, plain and
`--checked` (a mutated header can make `sniff` hand a file to another
codec). `tests/burn/drivers/imageio_check.my` answers requests (its header
says which):

- `imageio.decode` and `imageio.info` of every corpus file, broken ones
  included, are exactly its codec's `decode` and `info`;
- `sniff` names every readable file's format, and `format_of` the format of
  each extension, in any case;
- a file whose name lies about its format (a PNG called `.jpg`, a JPEG
  called `.gif`, and so on, or no extension at all) is read by its contents;
- `load` turns the corpus's EXIF-oriented JPEGs as `jpeg.apply_orientation`
  does, to the pixels Pillow's `ImageOps.exif_transpose` gives (their hashes
  are vendored below: `python3 -m tests.burn.test_imageio --vendor` prints
  them again, with Pillow);
- every readable 8-bit file saved in each format through a temporary
  directory and loaded back is the same image for the lossless ones (PNG,
  TIFF, BMP, PNM, QOI; BMP and QOI make gray RGB), the same size for GIF,
  and the same size for JPEG (std.jpeg's encoder, MYLA-937); every 16-bit file
  through `save16` and `load16` as PNG, TIFF and PNM is the same image;
- with Pillow installed, Pillow reads what `save` wrote as the same pixels;
- a missing file is `ImageError.Io`, a file of no known format
  `BadSignature`.

The drivers run on the self-hosted native build; with MYLA_TEST_TARGET set
(`scripts/test-target.py`) they are built for that target.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests.burn import _images as im
from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON, TEST_TARGET

DECODE_DRIVER = im.driver_source("imageio")
CHECK_DRIVER = im.driver_source("imageio_check")
FORMATS = ["png", "jpeg", "gif", "tiff", "bmp", "pnm", "qoi"]
LOSSLESS = ["png", "tiff", "bmp", "pnm", "qoi"]
EXTENSIONS = {"png": "png", "jpeg": "jpg", "gif": "gif", "tiff": "tif", "bmp": "bmp", "pnm": "pnm", "qoi": "qoi"}

# Pillow 13's `ImageOps.exif_transpose(Image.open(path))`, its samples'
# SHA-256 and size (`--vendor` prints them again).
PILLOW_TRANSPOSED = {
    "jpeg/exif-orientation-3.jpg": (48, 32, "5bda85ad7bb0d0f3b9370b55536be412e783bafe3d24fc35093bff4129eeff89"),
    "jpeg/exif-orientation-6.jpg": (32, 48, "37ce76f1296a13678c1042acff433201ec453e402961c58597702244823fea2e"),
    "jpeg/exif-orientation-8.jpg": (32, 48, "d2fb42c258e07304e1b1948e0c6e7af1ef97f13a69ea58eed2f2f4fc431c0077"),
}

# `format_of`'s table: a file name and the format its extension names.
FORMAT_OF = [
    ("a.png", "png"), ("A.PNG", "png"), ("dir.jpg/a.png", "png"),
    ("a.jpg", "jpeg"), ("a.JPG", "jpeg"), ("a.jpeg", "jpeg"), ("a.Jpeg", "jpeg"), ("a.jpe", "jpeg"),
    ("a.jfif", "jpeg"), ("a.gif", "gif"), ("a.GIF", "gif"), ("a.tif", "tiff"), ("a.tiff", "tiff"),
    ("a.TIFF", "tiff"), ("a.bmp", "bmp"), ("a.dib", "bmp"), ("a.pbm", "pnm"), ("a.pgm", "pnm"),
    ("a.ppm", "pnm"), ("a.pnm", "pnm"), ("a.pam", "pnm"), ("a.PPM", "pnm"), ("a.qoi", "qoi"),
    ("a.QOI", "qoi"), ("C:\\photos\\IMG.JPG", "jpeg"), ("a.tar.png", "png"),
    ("a.webp", "none"), ("a.png.txt", "none"), ("png", "none"), (".png", "none"), ("dir/.png", "none"),
    ("a.png/b", "none"), ("a.", "none"), ("a.jpg ", "none"), ("a.pn", "none"),
]

# Broken files too short for `sniff` to know them, which their codec refuses
# with another error.
SNIFFED_AWAY = {
    "jpeg/soi-only.jpg": "differ errors: not an image of this format / truncated input",   # FF D8 and nothing
}


def _readable(e: dict) -> bool:
    return e["expect"] == "ok"


def _first_frame(e: dict) -> dict | None:
    """The entry as imageio.decode reads it: a GIF's first frame (its hash
    from the expected PAM; None for a GIF without one)."""
    if e["expect"] != "ok" or e.get("frames", 1) == 1:
        return e
    want = im.expected(e)
    if want is None:
        return None
    first = want.frame(0)
    return {**e, "frames": 1, "sha256": first.sha256()}


def _decode_items() -> list[dict]:
    out = []
    for e in im.entries():
        if e.get("bits") == 32:
            continue                         # float32 TIFFs: tiff.decode's 8 bits aren't the manifest's
        f = _first_frame(e)
        if f is not None:
            out.append(f)
    return out


def _pillow() -> bool:
    try:
        from PIL import Image  # noqa: F401
        return True
    except ImportError:
        return False


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class ImageioDecode(unittest.TestCase):
    """`imageio.decode` under the corpus's harness."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.plain = im.build_driver(DECODE_DRIVER, cls.tmp.name)
        cls.checked = im.build_driver(DECODE_DRIVER, cls.tmp.name, checked=True)
        cls.items = _decode_items()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def corpus(self, argv: list[str], items: list[dict]) -> None:
        problems = im.check_corpus(im.Driver(argv), items, self.tmp.name)
        self.assertEqual(problems, [], f"{len(problems)} of {len(items)} files wrong")

    def test_every_format_s_corpus_natively(self) -> None:
        self.assertEqual({e["format"] for e in self.items}, set(FORMATS))
        self.assertGreater(len(self.items), 340)
        self.corpus(self.plain, self.items)

    def test_every_format_s_corpus_checked(self) -> None:
        self.corpus(self.checked, self.items)

    @unittest.skipIf(TEST_TARGET, "the interpreter's runs are the host's")
    def test_the_smallest_file_of_each_format_interpreted(self) -> None:
        small = []
        for fmt in FORMATS:
            ok = sorted((e for e in self.items if e["format"] == fmt and _readable(e)),
                        key=lambda e: os.path.getsize(im.path_of(e)))
            small.append(ok[0])
        self.corpus(im.interpreter_argv(DECODE_DRIVER), small)

    def fuzz(self, argv: list[str]) -> None:
        # the two smallest readable files of each format, truncated at every
        # length and mutated, as a codec's own fuzz runs do (here sniff hands
        # each case to a codec, maybe another than the original's)
        files = []
        for fmt in FORMATS:
            ok = sorted({im.path_of(e) for e in self.items if e["format"] == fmt and _readable(e)},
                        key=os.path.getsize)
            files += ok[:2]
        stats = im.fuzz(im.Driver(argv, max_pixels=1 << 20), files, self.tmp.name,
                        truncate=files[::2])
        self.assertGreater(stats.cases, im.FUZZ_CASES)
        self.assertGreater(stats.err, 0)
        self.assertGreater(stats.ok, 0)

    def test_fuzz_natively(self) -> None:
        self.fuzz(self.plain)

    def test_fuzz_checked(self) -> None:
        self.fuzz(self.checked)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class ImageioCheck(unittest.TestCase):
    """imageio_check.my's requests."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.argv = im.build_driver(CHECK_DRIVER, cls.tmp.name)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def ask(self, requests: list[list[str]]) -> list[str]:
        text = "".join("\t".join(r) + "\n" for r in requests)
        proc = subprocess.run(self.argv, input=text.encode(), capture_output=True, timeout=900)
        lines = proc.stdout.decode("utf-8", "replace").split("\n")[:-1]
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace")[-1500:])
        self.assertEqual(len(lines), len(requests), proc.stderr.decode("utf-8", "replace")[-1500:])
        return lines

    def test_decode_and_info_are_the_codec_s(self) -> None:
        entries = im.entries()
        lines = self.ask([["same", im.path_of(e), e["format"]] for e in entries])
        for e, line in zip(entries, lines):
            with self.subTest(e["path"]):
                if e["path"] in SNIFFED_AWAY:
                    self.assertEqual(line, SNIFFED_AWAY[e["path"]])
                    continue
                self.assertNotRegex(line, "^differ", line)
                if e["expect"] == "ok":
                    self.assertTrue(line.startswith("ok "), line)
                elif e["expect"] == "err":
                    self.assertTrue(line.startswith("err "), line)

    def test_sniff_names_every_readable_file_s_format(self) -> None:
        entries = im.entries(expect="ok")
        lines = self.ask([["sniff", im.path_of(e)] for e in entries])
        for e, line in zip(entries, lines):
            with self.subTest(e["path"]):
                self.assertEqual(line, e["format"])
        # the broken signatures of the corpus are no format at all
        broken = ["jpeg/not-jpeg.jpg", "gif/not-gif.gif", "bmp/not-bmp.bmp", "pnm/not-pnm.ppm", "qoi/not-qoi.qoi"]
        self.assertEqual(self.ask([["sniff", os.path.join(im.DATA, p)] for p in broken]), ["none"] * len(broken))

    def test_format_of_by_the_extension(self) -> None:
        lines = self.ask([["format_of", name] for name, _ in FORMAT_OF])
        self.assertEqual(list(zip([n for n, _ in FORMAT_OF], lines)), FORMAT_OF)

    def test_a_lying_extension_is_read_by_the_contents(self) -> None:
        # the smallest readable file of each format, copied under the next
        # format's extension and without one
        lies = os.path.join(self.tmp.name, "lies")
        os.makedirs(lies, exist_ok=True)
        requests = []
        for i, fmt in enumerate(FORMATS):
            e = min((e for e in im.entries(fmt, "ok") if e.get("bits") != 32),
                    key=lambda e: os.path.getsize(im.path_of(e)))
            wrong = EXTENSIONS[FORMATS[(i + 1) % len(FORMATS)]]
            for name in (f"{fmt}.{wrong}", f"{fmt}-no-extension", f"{fmt}.webp"):
                shutil.copyfile(im.path_of(e), os.path.join(lies, name))
                requests.append(["load", im.path_of(e)])
                requests.append(["load", os.path.join(lies, name)])
        lines = self.ask(requests)
        for i in range(0, len(lines), 2):
            with self.subTest(requests[i + 1][1]):
                self.assertTrue(lines[i].startswith("ok "), lines[i])
                self.assertEqual(lines[i + 1], lines[i])

    def test_load_turns_jpegs_by_their_exif_orientation(self) -> None:
        paths = sorted(PILLOW_TRANSPOSED)
        lines = self.ask([["load", os.path.join(im.DATA, p)] for p in paths])
        for p, line in zip(paths, lines):
            with self.subTest(p):
                w, h, sha = PILLOW_TRANSPOSED[p]
                self.assertEqual(line, f"ok {w} {h} rgb {sha}")
                stored = [e for e in im.entries("jpeg") if e["path"] == p][0]
                self.assertNotEqual(stored["orientation"], 1)
                self.assertNotEqual(stored["sha256"], sha, "as stored isn't as shown")
        # every other JPEG of the corpus has no turn to make: load is decode
        plain = [e for e in im.entries("jpeg", "ok") if e["path"] not in PILLOW_TRANSPOSED]
        lines = self.ask([["load", im.path_of(e)] for e in plain])
        for e, line in zip(plain, lines):
            with self.subTest(e["path"]):
                self.assertEqual(e.get("orientation", 1), 1)
                self.assertEqual(line, f"ok {e['width']} {e['height']} {e['layout']} {e['sha256']}")

    def test_save_and_load_round_trip_every_format(self) -> None:
        items = [e for e in im.entries(expect="ok") if e.get("bits") != 32]
        requests = []
        for i, e in enumerate(items):
            d = os.path.join(self.tmp.name, f"rt{i}")
            os.makedirs(d, exist_ok=True)
            requests.append(["roundtrip", im.path_of(e), d])
        lines = self.ask(requests)
        for e, line in zip(items, lines):
            with self.subTest(e["path"]):
                self.assertEqual(line, "ok png,jpeg,gif,tiff,bmp,pnm,qoi, jpeg=yes")
        sixteen = [e for e in items if e["bits"] == 16]
        self.assertGreater(len(sixteen), 10)
        requests = []
        for i, e in enumerate(sixteen):
            d = os.path.join(self.tmp.name, f"rt16-{i}")
            os.makedirs(d, exist_ok=True)
            requests.append(["roundtrip16", im.path_of(e), d])
        for e, line in zip(sixteen, self.ask(requests)):
            with self.subTest(e["path"], bits=16):
                self.assertEqual(line, "ok")

    @unittest.skipUnless(_pillow(), "Pillow isn't installed")
    def test_pillow_reads_what_save_writes(self) -> None:
        from PIL import Image
        items = [e for e in im.entries(expect="ok") if e["bits"] == 8 and e["pam"] and e["frames"] == 1]
        items = sorted(items, key=lambda e: (e["layout"], os.path.getsize(im.path_of(e))))[::6]
        requests = []
        for i, e in enumerate(items):
            d = os.path.join(self.tmp.name, f"pil{i}")
            os.makedirs(d, exist_ok=True)
            requests.append(["roundtrip", im.path_of(e), d])
        self.ask(requests)
        modes = {"L": "gray", "LA": "gray+alpha", "RGB": "rgb", "RGBA": "rgba"}
        checked = 0
        for (_, _, d), e in zip(requests, items):
            want = im.expected(e)
            for fmt in LOSSLESS:
                saved = os.path.join(d, "rt." + EXTENSIONS[fmt])
                with open(saved, "rb") as fh:
                    if fh.read(2) == b"P7":
                        continue             # a PAM with alpha, which Pillow 13 doesn't read
                with self.subTest(e["path"], fmt=fmt):
                    with Image.open(saved) as pic:
                        pic.load()
                        layout = modes.get(pic.mode)
                        self.assertIsNotNone(layout, pic.mode)
                        got = im.from_bytes(pic.width, pic.height, layout, 8, pic.tobytes())
                    # in the layout written: BMP and QOI hold gray as RGB, PNG
                    # drops an opaque alpha
                    same = im.to_layout(want, got.layout)
                    self.assertIsNotNone(same, f"{e['layout']} came back {got.layout}")
                    self.assertEqual(got.sha256(), same.sha256())
                    checked += 1
        self.assertGreater(checked, 100)

    def test_errors(self) -> None:
        missing = os.path.join(self.tmp.name, "missing.png")
        text = os.path.join(self.tmp.name, "text.png")
        with open(text, "w") as fh:
            fh.write("not an image\n")
        empty = os.path.join(self.tmp.name, "empty.jpg")
        open(empty, "wb").close()
        lines = self.ask([["load", missing], ["load", text], ["load", empty], ["load", self.tmp.name]])
        self.assertEqual(lines, ["err NotFound", "err not an image of this format",
                                 "err not an image of this format", "err IsADirectory"])


def vendor() -> None:
    """Pillow's transposed pixels of the corpus's oriented JPEGs, as
    PILLOW_TRANSPOSED holds them."""
    from PIL import Image, ImageOps
    for e in im.entries("jpeg", "ok"):
        if e.get("orientation", 1) == 1:
            continue
        with Image.open(im.path_of(e)) as pic:
            t = ImageOps.exif_transpose(pic)
            print(f'    "{e["path"]}": ({t.width}, {t.height}, "{hashlib.sha256(t.tobytes()).hexdigest()}"),')


if __name__ == "__main__":
    if sys.argv[1:] == ["--vendor"]:
        vendor()
    else:
        unittest.main()
