"""Burn tests: std.pnm, std.bmp and std.qoi's encoders (MYLA-934).

Their decoders are tests.burn.test_images's `PnmDecoder`, `Pnm16Decoder`,
`BmpDecoder` and `QoiDecoder` (the corpus, natively and `--checked`, the
interpreter, the fuzz runs). Here every `ok` file of the three formats in the
corpus goes through `tests/burn/drivers/simple_roundtrip.my`, natively: it is
decoded, written again by every encoder (BMP, QOI, PNM in each kind and
form, 8 and 16 bits) and decoded again, which must give what the encoder
keeps of the image. The QOI files Pillow wrote come back byte for byte but
for the colour space (Pillow writes 1, qoi.h and std.qoi 0), which shows the
encoder makes the reference encoder's choices. With Pillow installed, Pillow
reads every file the encoders wrote (but PAM, which it can't) to the pixels
our decoder reads from it (skipped without Pillow).
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest

from tests.burn import _images as im
from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON

FORMATS = ("pnm", "bmp", "qoi")


def _has_pillow() -> bool:
    try:
        import numpy  # noqa: F401
        from PIL import Image  # noqa: F401
        return True
    except ImportError:
        return False


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class SimpleRoundTrips(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.driver = im.Driver(im.build_driver(im.driver_source("simple_roundtrip"), cls.tmp.name))
        cls.items = [e for f in FORMATS for e in im.entries(f, "ok")]
        cases = [(im.path_of(e), os.path.join(cls.tmp.name, f"case{i}")) for i, e in enumerate(cls.items)]
        text = "".join(f"{a}\t{b}\n" for a, b in cases)
        proc = subprocess.run(cls.driver.argv, input=text.encode(), capture_output=True, timeout=600)
        cls.lines = proc.stdout.decode("utf-8", "replace").split("\n")[:-1]
        cls.stderr = proc.stderr.decode("utf-8", "replace")
        cls.returncode = proc.returncode

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def outputs(self) -> list[tuple[dict, str, str]]:
        """(entry, output name, its path) for every file the encoders wrote."""
        out = []
        for i, (e, line) in enumerate(zip(self.items, self.lines)):
            for name in line.split(" ")[1:]:
                out.append((e, name, os.path.join(self.tmp.name, f"case{i}.{name}")))
        return out

    def test_every_encoder_round_trips(self) -> None:
        self.assertEqual(self.returncode, 0, self.stderr[-2000:])
        self.assertEqual(len(self.lines), len(self.items))
        for e, line in zip(self.items, self.lines):
            with self.subTest(e["path"]):
                self.assertTrue(line.startswith("ok "), line)
                names = line.split(" ")[1:]
                self.assertEqual(len(names), 18 if e["format"] == "pnm" else 10)
        self.assertGreater(len(self.outputs()), 300)

    def test_qoi_writes_what_the_reference_encoder_writes(self) -> None:
        checked = 0
        for i, e in enumerate(self.items):
            if e["format"] != "qoi":
                continue
            with self.subTest(e["path"]):
                with open(im.path_of(e), "rb") as fh:
                    want = bytearray(fh.read())
                with open(os.path.join(self.tmp.name, f"case{i}.qoi"), "rb") as fh:
                    got = fh.read()
                self.assertEqual(want[13], 1)                 # Pillow's colour space
                want[13] = 0
                self.assertEqual(got, bytes(want))
                checked += 1
        self.assertEqual(checked, 4)

    @unittest.skipUnless(_has_pillow(), "Pillow or numpy isn't installed")
    def test_pillow_reads_what_the_encoders_write(self) -> None:
        from tests.burn import _images_vendor as v
        checked = 0
        for e, name, path in self.outputs():
            with open(path, "rb") as fh:
                data = fh.read()
            if data[:2] == b"P7":
                continue                                  # Pillow can't read PAM
            with self.subTest(e["path"], output=name):
                got = v.pillow_reads(data)
                self.assertIsNotNone(got, "Pillow can't read it")
                ours = im.read_pam_file(path + ".pam")
                # Pillow reads 16-bit PPM at 8 bits: compared rounded
                self.assertIsNone(im.compare(got, ours))
                checked += 1
        self.assertGreater(checked, 250)


if __name__ == "__main__":
    unittest.main()
