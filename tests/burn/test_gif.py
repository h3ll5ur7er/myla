"""Burn tests: std.gif's encoder (MYLA-964).

`tests/burn/drivers/gif_encode.my` encodes, natively, every GIF of the
corpus again (`decode_all`, then `encode_all`) and two animations it makes
itself (few colours, kept exactly; many, quantised and dithered; both with a
moving square and a moving transparent hole, so frames are written as their
changed rectangles and some need the `Background` disposal). Each output
decodes again to the frames the input shows (exactly, alpha all or nothing),
but the quantised one. With Pillow installed, Pillow reads every output to
the same frames as std.gif does, with the same delays and loop count, the
quantised animation at a PSNR above 30 dB against its source. The decoder's own tests are
test_images.py's `GifDecoder` (the corpus and the fuzz runs).
"""
from __future__ import annotations

import math
import os
import subprocess
import tempfile
import unittest

from tests.burn import _images as im
from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON

SYNTH = {"few.gif": "synth:64:48:6:few", "many.gif": "synth:64:48:6:many"}


def _has_pillow() -> bool:
    try:
        from PIL import Image  # noqa: F401
        return True
    except ImportError:
        return False


def _pillow_frames(path: str) -> tuple[list[bytes], list[int], int | None, tuple[int, int]]:
    """Pillow's frames of a GIF as RGBA bytes, their durations and the loop count."""
    from PIL import Image
    with Image.open(path) as img:
        frames, delays = [], []
        for i in range(getattr(img, "n_frames", 1)):
            img.seek(i)
            frames.append(img.convert("RGBA").tobytes())
            delays.append(img.info.get("duration", 0))
        return frames, delays, img.info.get("loop"), img.size


def _same_shown(a: bytes, b: bytes) -> bool:
    """RGBA samples equal, the colour of transparent pixels aside."""
    if len(a) != len(b):
        return False
    for i in range(0, len(a), 4):
        if a[i + 3] != b[i + 3] or (a[i + 3] and a[i:i + 3] != b[i:i + 3]):
            return False
    return True


def _rectangles(data: bytes) -> tuple[list[int], list[int]]:
    """The pixels of each frame's rectangle in a GIF, and the disposals."""
    sizes, disposals = [], []
    pos = 13 + (3 * (2 << (data[10] & 7)) if data[10] & 0x80 else 0)
    while data[pos] != 0x3B:
        if data[pos] == 0x21:
            if data[pos + 1] == 0xF9:
                disposals.append((data[pos + 3] >> 2) & 7)
            pos += 2
        else:
            w = int.from_bytes(data[pos + 5:pos + 7], "little")
            h = int.from_bytes(data[pos + 7:pos + 9], "little")
            sizes.append(w * h)
            flags = data[pos + 9]
            pos += 10 + (3 * (2 << (flags & 7)) if flags & 0x80 else 0) + 1
        while data[pos]:
            pos += data[pos] + 1
        pos += 1
    return sizes, disposals


def _psnr(a: bytes, b: bytes) -> float:
    err = sum((x - y) ** 2 for x, y in zip(a, b)) / len(a)
    return math.inf if err == 0 else 10 * math.log10(255 * 255 / err)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class GifEncoder(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        argv = im.build_driver(im.driver_source("gif_encode"), cls.tmp.name)
        cls.inputs = {os.path.basename(e["path"]): im.path_of(e) for e in im.entries("gif", "ok")}
        cls.inputs.update(SYNTH)
        cases = [(src, os.path.join(cls.tmp.name, name)) for name, src in cls.inputs.items()]
        lines = "".join(f"{src}\t{out}\n" for src, out in cases)
        # (as bytes: a text-mode pipe ends each line with CRLF on Windows, and
        # the driver would write to an output path ending in `\r`, MYLA-926)
        r = subprocess.run(argv, input=lines.encode(), capture_output=True, timeout=600)
        assert r.returncode == 0, r.stderr.decode(errors="replace")
        cls.results = dict(zip(cls.inputs, r.stdout.decode().splitlines()))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def out(self, name: str) -> str:
        return os.path.join(self.tmp.name, name)

    def test_outputs_decode_to_what_the_inputs_show(self) -> None:
        self.assertEqual(len(self.results), len(self.inputs))
        for name, line in self.results.items():
            with self.subTest(name):
                frames = 6 if name in SYNTH else next(e for e in im.entries("gif", "ok")
                                                      if e["path"].endswith("/" + name))["frames"]
                exact = "false" if name == "many.gif" else "true"
                self.assertEqual(line, f"ok {frames} {exact}")

    def test_changed_rectangles_and_transparency(self) -> None:
        # the made animations: frames after the first are written smaller than
        # the canvas, and the hole that moves needs a Background disposal
        for name in SYNTH:
            with self.subTest(name):
                with open(self.out(name), "rb") as fh:
                    data = fh.read()
                sizes, disposals = _rectangles(data)
                self.assertEqual(len(sizes), 6)
                self.assertEqual(sizes[0], 64 * 48)
                self.assertTrue(all(s < 64 * 48 for s in sizes[1:]), sizes)
                self.assertIn(2, disposals)
                self.assertEqual(data[:6], b"GIF89a")

    @unittest.skipUnless(_has_pillow(), "Pillow isn't installed")
    def test_pillow_reads_the_same_frames_delays_and_loops(self) -> None:
        for name, src in self.inputs.items():
            with self.subTest(name):
                frames, delays, loop, size = _pillow_frames(self.out(name))
                ours = im.read_pam_file(self.out(name) + ".pam")
                self.assertEqual(size, (ours.width, ours.height))
                self.assertEqual(len(frames), ours.frames)
                raw = ours.raw()
                n = ours.width * ours.height * 4
                for i, f in enumerate(frames):
                    self.assertTrue(_same_shown(f, raw[i * n:(i + 1) * n]), f"frame {i}")
                if name in SYNTH:
                    self.assertEqual(delays, [30 + 10 * i for i in range(6)])
                    self.assertEqual(loop, 0)
                    src_raw = im.read_pam_file(self.out(name) + ".src.pam").raw()
                    if name == "few.gif":
                        self.assertTrue(_same_shown(src_raw, raw))
                    else:
                        self.assertGreater(_psnr(src_raw, raw), 30)
                else:
                    want, want_delays, want_loop, _ = _pillow_frames(src)
                    self.assertEqual(delays, want_delays)
                    self.assertEqual(loop, want_loop)
                    for i, f in enumerate(frames):
                        self.assertTrue(_same_shown(f, want[i]), f"frame {i} against the original")


if __name__ == "__main__":
    unittest.main()
