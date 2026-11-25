"""Burn tests: std.png's encoders (MYLA-935). Its decoders are tested over
the image corpus by test_images.py (`PngDecoder`, `Png16Decoder`).

A driver (`tests/burn/drivers/png_roundtrip.my`) decodes every PNG of the
corpus that decodes, encodes it again (`encode` at 8 bits, `encode16` for
the 16-bit files, `encode_indexed` of `image.quantize` for the palette
files) and checks that its own decoder gives the same pixels back. The
files it writes are then read by `_images.png_decode`, a decoder of
Python's own (zlib alone), which must give the corpus's expected pixels
(the layout may be smaller: gray for gray RGB, no alpha for an opaque one),
and with Pillow installed by Pillow as well. Each fixed filter is tried on
a few files, and levels 0 and 9. At level 6 the files must be no bigger in
all than Pillow's (`optimize=False`, `compress_level=6`) of the same
pixels, give or take a tenth (skipped without Pillow).
"""
from __future__ import annotations

import io
import os
import subprocess
import tempfile
import unittest

from tests.burn import _images as im
from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON


def _has_pillow() -> bool:
    try:
        import numpy  # noqa: F401
        from PIL import Image  # noqa: F401
        return True
    except ImportError:
        return False


def _ok_pngs() -> list[dict]:
    return [e for e in im.entries("png", "ok") if e["pam"]]


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Encoders(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.argv = im.build_driver(im.driver_source("png_roundtrip"), cls.tmp.name)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def run_driver(self, cases: list[tuple[str, str, str]], *flags: str) -> list[str]:
        text = "".join(f"{i}\t{o}\t{m}\n" for i, o, m in cases)
        r = subprocess.run(self.argv + list(flags), input=text, capture_output=True, text=True, timeout=600)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        lines = r.stdout.splitlines()
        self.assertEqual(len(lines), len(cases), r.stderr[-2000:])
        return lines

    def round_trip(self, items: list[dict], mode_of, *flags: str) -> dict[str, bytes]:
        """Each item encoded by the driver: the files written, by path. The
        driver's own check, then Python's decoder against the expected
        pixels."""
        cases = []
        for n, e in enumerate(items):
            cases.append((im.path_of(e), os.path.join(self.tmp.name, f"rt{n}.png"), mode_of(e)))
        out = {}
        for e, (_, path, mode), line in zip(items, cases, self.run_driver(cases, *flags)):
            with self.subTest(e["path"], mode=mode, flags=flags):
                self.assertTrue(line.startswith("ok "), line)
                with open(path, "rb") as fh:
                    data = fh.read()
                self.assertEqual(int(line.split()[1]), len(data))
                want = im.expected(e)
                if mode == "8" and want.bits == 16:
                    want = im.to_bits(want, 8)
                got = im.png_decode(data)
                self.assertIsNone(im.compare(got, want), f"Python's decoder of our file ({line})")
                out[e["path"]] = data
        return out

    @staticmethod
    def mode(e: dict) -> str:
        if e["bits"] == 16:
            return "16"
        return "indexed" if "palette" in e["features"] else "8"

    def test_every_file_round_trips(self) -> None:
        items = _ok_pngs()
        self.assertGreater(len(items), 160)
        written = self.round_trip(items, self.mode)
        if _has_pillow():
            from tests.burn import _images_vendor as v
            for e in items:
                with self.subTest(e["path"], pillow=True):
                    data = written[e["path"]]
                    how = v.same_as_pillow(data, im.png_decode(data), e["path"])
                    self.assertNotEqual(how, "Pillow can't read it")

    def test_8_bits_of_every_file(self) -> None:
        # 16-bit files rounded to 8, palette files as RGB or RGBA
        self.round_trip(_ok_pngs(), lambda e: "8")

    def test_each_filter_and_level(self) -> None:
        items = [e for e in _ok_pngs() if e["path"].startswith("png/gen/")]
        items += [e for e in _ok_pngs() if os.path.basename(e["path"]) in ("basn2c16.png", "basi6a08.png", "basn0g01.png")]
        for flags in (["--filter", "0"], ["--filter", "1"], ["--filter", "2"], ["--filter", "3"], ["--filter", "4"],
                      ["--level", "0"], ["--level", "9"]):
            self.round_trip(items, self.mode, *flags)

    @unittest.skipUnless(_has_pillow(), "Pillow or numpy isn't installed")
    def test_as_small_as_pillow_s(self) -> None:
        from PIL import Image
        items = [e for e in _ok_pngs() if e["bits"] == 8 and "palette" not in e["features"]]
        written = self.round_trip(items, lambda e: "8")
        modes = {"gray": "L", "gray+alpha": "LA", "rgb": "RGB", "rgba": "RGBA"}
        ours = pillow = 0
        for e in items:
            want = im.expected(e)
            pic = Image.frombytes(modes[want.layout], (want.width, want.height), bytes(want.samples))
            buf = io.BytesIO()
            pic.save(buf, "PNG", optimize=False, compress_level=6)
            ours += len(written[e["path"]])
            pillow += len(buf.getvalue())
        print(f"\nstd.png at level 6: {ours} bytes for {len(items)} files, Pillow's {pillow} ({ours / pillow:.3f})")
        self.assertLess(ours, pillow * 1.1)


if __name__ == "__main__":
    unittest.main()
