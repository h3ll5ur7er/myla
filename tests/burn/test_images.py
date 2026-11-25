"""Burn tests: the image and font corpus, and every image codec against it
(MYLA-945, D311).

The corpus (`tests/burn/data/images/`, `LICENSES.md` there) is checked
first, with nothing but Python's own modules: every file is in the manifest
and every entry's file is there, the expected PAM files parse and match
their hashes, every PNG decodes to its expected pixels by `_images`'
reference decoder, the font is a TrueType (glyf) font, and the corpus
covers what the codec tasks need (PngSuite's colour types and depths, JPEG's
samplings, progressive, restart markers and CMYK, animated GIFs with each
disposal, TIFF's compressions, tiles, planes and byte orders, BMP's depths
and RLE, PNM's every kind). With Pillow installed, Pillow decodes every file
it reads to the expected pixels too (skipped without it).

The harness is tested before any codec exists with its own driver
(`tests/burn/drivers/selftest_pam.my`, a reader of 8-bit PAM files):
`SelftestPamDecoder` gives it every test a codec gets, over the corpus's PAM
files (their hashes natively, plain and `--checked`, and interpreted; the
fuzz runs), and `Harness` checks the rest: the PAM it writes, `err` and
`bad`, the comparisons and their tolerances, a driver with a planted bug
caught with its case, seeded mutations, the benchmark's picture.

`CODECS` is where a codec lane plugs in: a driver `tests/burn/drivers/<name>.my`
(the protocol is in `_images.py`) for a module `lib/std/<module>.my`. Each
codec gets a test class that is skipped until both exist: the format's
corpus natively and `--checked`, the smallest files in the interpreter, and
the fuzz runs (truncations up to 512 bytes and 10,000 seeded mutations, plain
and `--checked`; MYLA_FUZZ_SEED and MYLA_FUZZ_CASES change them). With
MYLA_TEST_TARGET set the drivers are built for that target.

`python3 -m tests.burn.test_images --vendor` makes the corpus again
(`_images_vendor.py`; it needs Pillow and numpy).
"""
from __future__ import annotations

import hashlib
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import shutil
from dataclasses import dataclass
from typing import Callable

from tests.burn import _images as im
from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON, TEST_TARGET
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

_REPO = im._REPO
# The corpus's size, at most (2026-11-24: 1.73 MB).
CORPUS_LIMIT = 3_500_000


def _not_float(e: dict) -> bool:
    return e.get("bits") != 32


@dataclass
class Codec:
    """A decoder under test: `driver` names `tests/burn/drivers/<driver>.my`,
    `module` the std module it needs (`lib/std/<module>.my`), `format` the
    manifest's format. `accepts(entry)` picks the entries it reads (a
    decoder of 8 bits reads 16-bit files too, compared rounded to 8);
    `max_abs` and `min_psnr` loosen the comparison (an entry's own
    `tolerance` wins); the fuzz runs truncate the `truncate` smallest files
    at every length up to 512 bytes, mutate them all, and pass
    `--max-pixels max_pixels`; the interpreter decodes the `interpreted`
    smallest files and two broken ones. `entries` replaces the manifest's
    entries of `format` (the harness's own driver reads others)."""
    driver: str
    module: str
    format: str
    accepts: Callable[[dict], bool] = _not_float
    max_abs: float = 0
    min_psnr: float | None = None
    truncate: int = 6
    interpreted: int = 4
    max_pixels: int = 1 << 20
    notes: str = ""
    entries: Callable[[], list[dict]] | None = None

    def items(self) -> list[dict]:
        found = self.entries() if self.entries else im.entries(self.format)
        return [e for e in found if self.accepts(e)]


# The codec lanes add or change their rows here (MYLA-934 to MYLA-939): a
# driver per decoder function (std.png's `decode` and `decode16`, TIFF's
# `decode_f32` would be a third with `serve_f32`), each skipped until its
# module and its driver exist.
CODECS: list[Codec] = [
    Codec("pnm", "pnm", "pnm"),
    Codec("pnm16", "pnm", "pnm", notes="(decode16)"),
    Codec("bmp", "bmp", "bmp"),
    Codec("qoi", "qoi", "qoi"),
    Codec("png", "png", "png"),
    Codec("png16", "png", "png", accepts=lambda e: e.get("bits") == 16 or e["expect"] != "ok"),
    Codec("jpeg", "jpeg", "jpeg"),
    Codec("gif", "gif", "gif", notes="(decode_all + composite: every frame as shown)"),
    Codec("tiff", "tiff", "tiff"),
    Codec("tiff16_last_page", "tiff", "tiff", entries=lambda: _tiff_last_pages(),
          notes="(decode16 of the last page pages() finds)"),
    Codec("tiff_f32", "tiff", "tiff", accepts=lambda e: e.get("bits") == 32 or e["expect"] != "ok"),
]


def _tiff_last_pages() -> list[dict]:
    """The TIFF entries, a file of several pages expected as its last."""
    out = []
    for e in im.entries("tiff"):
        if e.get("pages"):
            e = {**e, **e["pages"][-1], "frames": 1}
            del e["pages"]
        out.append(e)
    return out


def _missing(codec: Codec) -> str | None:
    if not os.path.exists(os.path.join(STDLIB_ROOT, "std", codec.module + ".my")):
        return f"lib/std/{codec.module}.my doesn't exist yet"
    if not os.path.exists(im.driver_source(codec.driver)):
        return f"tests/burn/drivers/{codec.driver}.my doesn't exist yet"
    return None


def _has_pillow() -> bool:
    """Whether Pillow and numpy are there (the vendor module's readers need both)."""
    try:
        import numpy  # noqa: F401
        from PIL import Image  # noqa: F401
        return True
    except ImportError:
        return False


def _corpus_files() -> set[str]:
    out = set()
    for root, _, files in os.walk(im.DATA):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), im.DATA)
            if not rel.startswith("expected/"):
                out.add(rel)
    return out


def _sfnt_tables(data: bytes, offset: int = 0) -> list[str]:
    n = struct.unpack(">H", data[offset + 4:offset + 6])[0]
    return [data[offset + 12 + 16 * i:offset + 16 + 16 * i].decode("latin-1") for i in range(n)]


class Corpus(unittest.TestCase):
    """The corpus and its manifest, with Python alone."""

    def test_every_file_is_listed_and_every_entry_there(self) -> None:
        m = im.manifest()
        listed = {e["path"] for e in m["images"]} | {f["path"] for f in m["fonts"]}
        others = {"LICENSES.md", "manifest.json", "png/pngsuite/PngSuite.LICENSE", "fonts/OFL.txt", "fonts/info.json"}
        files = _corpus_files()
        self.assertEqual(sorted(files - listed - others), [], "files the manifest doesn't list")
        self.assertEqual(sorted(listed - files), [], "entries without their file")
        self.assertEqual(len(listed), len(m["images"]) + len(m["fonts"]), "an entry listed twice")
        self.assertEqual(sorted(others - files), [], "files the corpus should have")

    def test_entries_are_well_formed(self) -> None:
        for e in im.entries():
            with self.subTest(e["path"]):
                self.assertEqual(e["path"].split("/")[0], e["format"])
                self.assertIn(e["expect"], ("ok", "err", "any"))
                self.assertTrue(e["notes"])
                if e["expect"] != "ok":
                    self.assertNotIn("sha256", e)
                    continue
                self.assertIn(e["layout"], im.LAYOUTS)
                self.assertIn(e["bits"], (8, 16, 32))
                self.assertGreaterEqual(e["frames"], 1)
                self.assertRegex(e["sha256"], "^[0-9a-f]{64}$")
                n = e["width"] * e["height"] * im.LAYOUTS[e["layout"]][0] * e["frames"] * e["bits"] // 8
                if e["pam"] is None:
                    self.assertTrue(e["bits"] == 32 or n > 64 * 1024, "a small image without its PAM")

    def test_expected_pixels_match_their_hashes(self) -> None:
        count = 0
        for e in im.entries(expect="ok"):
            items = [e] + e.get("pages", [])
            for item in items:
                if not item.get("pam"):
                    continue
                with self.subTest(e["path"], pam=item["pam"]):
                    p = im.read_pam_file(os.path.join(im.DATA, item["pam"]))
                    self.assertEqual((p.width, p.height, p.layout, p.bits), (
                        item["width"], item["height"], item["layout"], item["bits"]))
                    self.assertEqual(p.frames, item.get("frames", 1))
                    self.assertEqual(p.sha256(), item["sha256"])
                    count += 1
        self.assertGreater(count, 250)

    def test_pngs_decode_to_the_expected_pixels(self) -> None:
        # the reference decoder of _images (zlib alone) against the PAM files
        # Pillow checked when they were made; every broken PNG is refused
        for e in im.entries("png"):
            with self.subTest(e["path"]):
                with open(im.path_of(e), "rb") as fh:
                    data = fh.read()
                if e["expect"] == "err":
                    with self.assertRaises(Exception):
                        im.png_decode(data)
                elif e["expect"] == "ok":
                    self.assertEqual(im.png_decode(data).sha256(), e["sha256"])

    def test_what_the_codecs_need_is_there(self) -> None:
        need = {
            "png": {"gray", "rgb", "palette", "gray+alpha", "rgba", "bits1", "bits2", "bits4", "bits8", "bits16",
                    "interlaced", "trns", "filter", "broken"},
            "jpeg": {"baseline", "progressive", "gray", "s444", "s422", "s420", "s440", "s411", "restart", "cmyk",
                     "adobe", "exif", "broken"},
            "gif": {"GIF89a", "animated", "interlaced", "transparent", "local-palette", "disposal0", "disposal1",
                    "disposal2", "disposal3", "broken"},
            "tiff": {"none", "lzw", "deflate", "deflate-old", "packbits", "strips", "tiles", "planar2", "big-endian",
                     "little-endian", "bits1", "bits4", "bits8", "bits16", "bits32", "float", "palette", "rgba",
                     "multipage", "predictor2", "predictor3", "broken"},
            "bmp": {"bits1", "bits4", "bits8", "bits16", "bits24", "bits32", "rle8", "rle4", "top-down", "bitfields",
                    "broken"},
            "pnm": {"pbm", "pgm", "ppm", "pam", "ascii", "binary", "bits16", "maxval", "broken"},
            "qoi": {"rgb", "rgba", "broken"},
        }
        for fmt, words in need.items():
            with self.subTest(fmt):
                have = set()
                for e in im.entries(fmt):
                    have.update(e["features"])
                self.assertEqual(sorted(words - have), [])
                self.assertTrue(im.entries(fmt, "ok") and im.entries(fmt, "err"))
        suite = [e for e in im.entries("png") if e["source"] == "pngsuite"]
        self.assertEqual(len(suite), 176)                      # with PngSuite.png itself
        self.assertEqual(len([e for e in suite if e["expect"] == "err"]), 14)

    def test_the_corpus_is_small(self) -> None:
        total = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(im.DATA) for f in fs)
        self.assertLess(total, CORPUS_LIMIT)

    def test_the_font_is_truetype_with_kerning(self) -> None:
        fonts = {f["path"]: f for f in im.manifest()["fonts"]}
        ttf = fonts["fonts/MylaTestSans.ttf"]
        with open(os.path.join(im.DATA, ttf["path"]), "rb") as fh:
            data = fh.read()
        self.assertEqual(data[:4], b"\x00\x01\x00\x00")       # TrueType outlines, not CFF's 'OTTO'
        tables = _sfnt_tables(data)
        for t in ("cmap", "glyf", "loca", "head", "hhea", "hmtx", "maxp", "name", "kern", "OS/2"):
            self.assertIn(t, tables)
        self.assertNotIn("CFF ", tables)
        self.assertLess(len(data), 100_000)
        self.assertEqual(hashlib.sha256(data).hexdigest(), ttf["sha256"])
        self.assertGreater(ttf["kern_pairs"], 100)
        ttc = fonts["fonts/MylaTestSans.ttc"]
        with open(os.path.join(im.DATA, ttc["path"]), "rb") as fh:
            coll = fh.read()
        self.assertEqual(coll[:4], b"ttcf")
        n = struct.unpack(">I", coll[8:12])[0]
        self.assertEqual(n, 2)
        for i in range(n):
            off = struct.unpack(">I", coll[12 + 4 * i:16 + 4 * i])[0]
            self.assertIn("glyf", _sfnt_tables(coll, off))
        renders = im.manifest()["renders"]
        engines = [r["engine"] for r in renders]
        self.assertGreaterEqual(engines.count("pillow"), 5)
        self.assertGreaterEqual(engines.count("freetype-unhinted"), 40)
        for r in renders:
            with self.subTest(r["text"], px=r["px"], dx=r.get("dx")):
                p = im.read_pam_file(os.path.join(im.DATA, r["pam"]))
                self.assertEqual((p.width, p.height, p.layout), (r["width"], r["height"], "gray"))
                self.assertEqual(p.sha256(), r["sha256"])
                self.assertGreater(max(p.samples), 200)       # something was drawn

    @unittest.skipUnless(_has_pillow(), "Pillow or numpy isn't installed")
    def test_pillow_decodes_to_the_expected_pixels(self) -> None:
        # as `--vendor` checked them: Pillow's 8 bits of a 16-bit file its
        # high bytes or rounded, PNG's gray or RGB tRNS kept aside by Pillow
        from tests.burn import _images_vendor as v
        checked = 0
        for e in im.entries(expect="ok"):
            if "Pillow can't read" in e["notes"] or "Pillow misreads" in e["notes"] or "cmyk_sha256" in e:
                continue                       # PAM files, a big-endian float predictor, CMYK made RGB here
            with self.subTest(e["path"]):
                with open(im.path_of(e), "rb") as fh:
                    data = fh.read()
                if e["format"] == "gif":
                    self.assertEqual(v.gif_frames(data).sha256(), e["sha256"])
                elif e["pam"]:
                    self.assertNotEqual(v.same_as_pillow(data, im.expected(e), e["path"]), "Pillow can't read it")
                else:
                    self.assertEqual(v.pillow_reads(data).sha256(), e["sha256"])
                checked += 1
        self.assertGreater(checked, 250)


# -- the codecs ----------------------------------------------------------------------

class _CodecTests:
    """The tests every codec gets (a subclass per row of CODECS)."""
    codec: Codec

    @classmethod
    def setUpClass(cls) -> None:
        if not CAN_BUILD_NATIVE:
            raise unittest.SkipTest(SKIP_REASON)
        why = _missing(cls.codec)
        if why:
            raise unittest.SkipTest(why)
        cls.tmp = tempfile.TemporaryDirectory()
        src = im.driver_source(cls.codec.driver)
        cls.plain_argv = im.build_driver(src, cls.tmp.name)
        cls.checked_argv = im.build_driver(src, cls.tmp.name, checked=True)
        cls.items = cls.codec.items()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def corpus(self, argv: list[str], items: list[dict]) -> None:
        problems = im.check_corpus(im.Driver(argv), items, self.tmp.name, self.codec.max_abs, self.codec.min_psnr)
        self.assertEqual(problems, [], f"{len(problems)} of {len(items)} files wrong")

    def test_corpus_natively(self) -> None:
        self.assertTrue(self.items)
        self.corpus(self.plain_argv, self.items)

    def test_corpus_checked(self) -> None:
        self.corpus(self.checked_argv, self.items)

    @unittest.skipIf(TEST_TARGET, "the interpreter's runs are the host's")
    def test_smallest_files_interpreted(self) -> None:
        by_size = sorted(self.items, key=lambda e: os.path.getsize(im.path_of(e)))
        small = [e for e in by_size if e["expect"] == "ok"][:self.codec.interpreted]
        small += [e for e in by_size if e["expect"] == "err"][:2]
        self.corpus(im.interpreter_argv(im.driver_source(self.codec.driver)), small)

    def fuzz(self, argv: list[str]) -> None:
        files = sorted({im.path_of(e) for e in self.items if e["expect"] == "ok"}, key=os.path.getsize)
        stats = im.fuzz(im.Driver(argv, max_pixels=self.codec.max_pixels), files, self.tmp.name,
                        truncate=files[:self.codec.truncate])
        self.assertGreater(stats.cases, im.FUZZ_CASES)
        self.assertGreater(stats.err, 0)

    def test_fuzz_natively(self) -> None:
        self.fuzz(self.plain_argv)

    def test_fuzz_checked(self) -> None:
        self.fuzz(self.checked_argv)


def _pam_items() -> list[dict]:
    """The corpus's expected 8-bit PAM files as entries selftest_pam reads,
    and the 16-bit ones as entries it refuses."""
    out = []
    for e in im.entries(expect="ok"):
        if e["pam"] and e["bits"] == 8:
            out.append({**e, "path": e["pam"], "format": "pam"})
        elif e["pam"]:
            out.append({"path": e["pam"], "format": "pam", "expect": "err", "notes": "16 bits: Unsupported here"})
    return out


# The harness's own driver goes through every test a codec gets.
SELFTEST = Codec("selftest_pam", "image", "pam", entries=_pam_items, interpreted=3, notes="(the harness itself)")


for _c in [SELFTEST, *CODECS]:
    _name = "".join(w.capitalize() for w in _c.driver.split("_")) + "Decoder"
    _doc = f"std.{_c.module} through tests/burn/drivers/{_c.driver}.my {_c.notes}".strip()
    globals()[_name] = type(_name, (_CodecTests, unittest.TestCase), {"codec": _c, "__doc__": _doc})
del _c, _name, _doc


# -- the harness's own checks ---------------------------------------------------------

_BUGGY = """// image_driver's protocol over a decoder that fails on purpose
import std.image as image
from std.image import Image, Image8, ImageError
import image_driver as driver

fun decode(b: [uint8], max: int64) -> Result<Image8, ImageError> {
    if b.len() == 7 && b[0] == 'X' {
        let empty: [int] = []
        return Err(ImageError.Corrupt(f"{empty[b.len()]}"))
    }
    if b.len() == 9 {
        return Ok(Image { width: 2, height: 2, layout: image.Layout.Gray, data: [1u8] })
    }
    return Err(ImageError.Truncated)
}

fun main() {
    driver.serve8(decode)
}
"""


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Harness(unittest.TestCase):
    """What `_images` and `image_driver.my` do beyond a codec's tests."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.plain = im.Driver(im.build_driver(im.driver_source("selftest_pam"), cls.tmp.name))
        cls.items = [e for e in _pam_items() if e["expect"] == "ok"]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    @unittest.skipIf(TEST_TARGET, "the interpreter's runs are the host's")
    def test_the_driver_module_s_cases(self) -> None:
        r = subprocess.run([selfhost_tool("main"), "test", im.driver_source("image_driver"), "--stdlib", STDLIB_ROOT],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_the_pam_written_and_the_hash_are_python_s(self) -> None:
        e = next(x for x in self.items if x["frames"] > 1)
        out = os.path.join(self.tmp.name, "frames.pam")
        r = self.plain.decode(im.path_of(e), out)
        self.assertEqual((r.kind, r.width, r.height, r.layout, r.bits, r.frames, r.sha256),
                         ("ok", e["width"], e["height"], e["layout"], 8, e["frames"], e["sha256"]))
        with open(out, "rb") as a, open(im.path_of(e), "rb") as b:
            self.assertEqual(a.read(), b.read())

    def test_errors_and_a_missing_file(self) -> None:
        e16 = next(e for e in im.entries(expect="ok") if e["pam"] and e["bits"] == 16)
        r = self.plain.decode(os.path.join(im.DATA, e16["pam"]))
        self.assertEqual((r.kind, r.message), ("err", "unsupported: MAXVAL 65535"))
        self.assertEqual(self.plain.decode(os.path.join(self.tmp.name, "nothing")).kind, "bad")
        big = next(x for x in self.items if x["width"] * x["height"] > 100)
        r = im.Driver(self.plain.argv, max_pixels=100).decode(im.path_of(big))
        self.assertEqual(r.line, f"err image too large: {big['width'] * big['height']} pixels")

    def test_comparisons(self) -> None:
        e = next(x for x in self.items if x["layout"] == "rgb" and x["width"] * x["height"] > 100)
        want = im.expected(e)
        got = im.Pixels(want.width, want.height, want.layout, 8, want.samples[:], 1)
        got.samples[5] += 3 if got.samples[5] < 250 else -3
        self.assertIn("1 of", im.compare(got, want))
        self.assertIsNone(im.compare(got, want, max_abs=3))
        self.assertIsNone(im.compare(got, want, max_abs=255, min_psnr=30))
        self.assertIsNotNone(im.compare(got, want, max_abs=255, min_psnr=200))
        self.assertIsNone(im.compare(want, im.to_bits(want, 16)))            # 16 bits rounded to 8
        self.assertEqual(im.to_bits(im.to_bits(want, 16), 8).samples, want.samples)
        rgba = im.to_layout(want, "rgba")
        self.assertIsNone(im.compare(rgba, want))                            # an opaque alpha added
        self.assertIsNone(im.compare(want, rgba))                            # and dropped
        self.assertIsNone(im.to_layout(want, "gray"))                        # colours aren't gray
        self.assertIn("shape", im.compare(want.frame(0), im.to_layout(want, "rgba"), convert=False))

    def test_a_crash_and_a_bad_image_are_reported_with_their_case(self) -> None:
        d = os.path.join(self.tmp.name, "buggy")
        os.makedirs(d)
        with open(os.path.join(d, "buggy.my"), "w", encoding="utf-8") as fh:
            fh.write(_BUGGY)
        shutil.copyfile(im.driver_source("image_driver"), os.path.join(d, "image_driver.my"))
        driver = im.Driver(im.build_driver(os.path.join(d, "buggy.my"), d))
        files = [os.path.join(d, "xs")]
        with open(files[0], "wb") as fh:
            fh.write(b"X" * 30)
        with self.assertRaises(AssertionError) as caught:
            im.fuzz(driver, files, self.tmp.name, count=10, truncate=files, limit=20)
        text = str(caught.exception)
        self.assertIn("fuzz case 7 (MYLA_FUZZ_SEED=", text)
        self.assertIn("truncated to 7 bytes: runtime error: list index 7 out of bounds", text)
        kept = text.split("the case: ")[1].split("\n")[0]
        self.assertEqual(os.path.getsize(kept), 7)
        # a decoder's image whose samples don't fill it (`bad`) fails a fuzz run too
        nine = os.path.join(d, "nine")
        with open(nine, "wb") as fh:
            fh.write(b"123456789")
        self.assertEqual(driver.decode(nine).line, "bad 2x2 gray with 1 samples")
        with self.assertRaises(AssertionError) as caught:
            im.fuzz(driver, [nine], self.tmp.name, count=50, truncate=[])
        self.assertIn(": bad 2x2 gray with 1 samples", str(caught.exception))
        self.assertIn("mutation", str(caught.exception))

    @unittest.skipIf(TEST_TARGET, "the benchmark runs on the host")
    def test_the_benchmark_s_picture_and_a_small_run(self) -> None:
        # benchmarks/images_std.my's #test cases check its picture against
        # images_pillow.py's formula; a small picture runs natively
        bench = os.path.join(_REPO, "benchmarks", "images_std.my")
        r = subprocess.run([selfhost_tool("main"), "test", bench, "--stdlib", STDLIB_ROOT], capture_output=True,
                           text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        binary = os.path.join(self.tmp.name, "images_std")
        im.native_build(im.check_file(bench), binary)
        r = subprocess.run([binary, "40", "30"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("40x30 RGB, 3600 samples", r.stdout)

    def test_mutations_are_seeded(self) -> None:
        data = bytes(range(200))
        a = [m for m in im.mutations(data, im.random.Random(5), 300)]
        b = [m for m in im.mutations(data, im.random.Random(5), 300)]
        self.assertEqual(a, b)
        words = ["flipped", "set to", "overwritten", "repeated", "deleted", "inserted", "field"]
        kinds = {w for what, _ in a for w in words if w in what}
        self.assertEqual(kinds, set(words))
        self.assertEqual([len(t) for _, t in im.truncations(data, 512)], list(range(200)))


if __name__ == "__main__":
    if sys.argv[1:] == ["--vendor"]:
        from tests.burn._images_vendor import vendor
        vendor()
    else:
        unittest.main()
