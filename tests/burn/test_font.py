"""Burn tests: `std.font` (MYLA-943) against the font corpus of MYLA-945.

The fonts are `tests/burn/data/images/fonts/MylaTestSans.ttf` (a subset of
Liberation Sans: 176 glyphs, 49 of them composite, a format 0 `kern` table
of 104 pairs) and `MylaTestSans.ttc` (Regular and Bold). The driver is
`tests/burn/drivers/font_driver.my`: without arguments it speaks the image
drivers' protocol for the fuzz runs, with `--commands` it answers one
command a line (its header lists them).

- **Parsing**, against a TrueType reader in plain Python here (`Sfnt`): the
  names and metrics of both faces, every glyph's advance and left side
  bearing, every glyph's outline box equal to the box its `glyf` header
  gives (composites included), every character of the (3, 1) format 4
  cmap and some the font lacks, and every kerning pair (and some that
  aren't pairs).
- **Rendering**, against FreeType's unhinted renderings in the manifest
  (`_images.renders("freetype-unhinted")`): the 48 single glyphs (A, g, @
  and the composite é at 12, 24 and 48 px, moved right by 0, 1/4, 1/2 and
  3/4 of a pixel) must have the same bitmap box and differ by at most
  `GLYPH_MAX` levels a pixel, `GLYPH_MEAN` on average; each glyph's advance
  in pixels must be FreeType's. The two strings (laid out unkerned, as
  FreeType gave no kerning for the font's pairs: see the manifest's notes),
  each glyph at its exact pen fraction, within `TEXT_MAX`; drawn through a
  `GlyphCache` (quarter-pixel positions), within `CACHED_MAX`, `CACHED_MEAN`
  on average.
- **Area**: every glyph's mask at 48 px covers the exact area of its
  outline's curves (computed here from the outline the driver prints) to
  within its perimeter times 1/16 px, the most FreeType's way of cutting
  curves into lines can lose.
- **Layout**: positions, widths, heights and line counts against a layout
  computed here by the rules of the module's documentation (advances,
  kerning, breaks at spaces within `max_width`, `\\n`, tabs, alignment,
  line height), on fixed texts and 200 random ones.
- **Fuzzing**: every truncation of both files up to 512 bytes, and every
  17th length after that, and 10,000 seeded mutations of them
  (`_images.fuzz`), natively, plain and `--checked`: each is `ok` or `err`,
  never a runtime error. The fuzz driver parses every face, outlines and
  renders every glyph at 12 px and lays out a text with every feature.
- **Interpreted**: the same answers from the self-hosted interpreter for a
  sample of commands.
"""
from __future__ import annotations

import math
import os
import random
import struct
import subprocess
import tempfile
import unittest

from tests.burn import _images as im
from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON, TEST_TARGET

TTF = os.path.join(im.DATA, "fonts", "MylaTestSans.ttf")
TTC = os.path.join(im.DATA, "fonts", "MylaTestSans.ttc")
DRIVER = im.driver_source("font_driver")

# Tolerances against FreeType (measured 2026-11-25: 5, 0.37; 5; 33, 2.2).
GLYPH_MAX = 6
GLYPH_MEAN = 0.5
TEXT_MAX = 6
CACHED_MAX = 40
CACHED_MEAN = 3.0


# -- a TrueType reader ----------------------------------------------------------

class Sfnt:
    """The tables of one face that the tests compare with."""

    def __init__(self, data: bytes, face: int = 0):
        self.data = data
        base = 0
        if data[:4] == b"ttcf":
            base = struct.unpack(">I", data[12 + 4 * face:16 + 4 * face])[0]
        n = self.u16(base + 4)
        self.tables = {}
        for i in range(n):
            tag, _, off, ln = struct.unpack(">4sIII", data[base + 12 + 16 * i:base + 28 + 16 * i])
            self.tables[tag.decode("latin-1")] = (off, ln)
        head = self.tables["head"][0]
        self.upem = self.u16(head + 18)
        long_loca = self.i16(head + 50) == 1
        self.glyphs = self.u16(self.tables["maxp"][0] + 4)
        hhea = self.tables["hhea"][0]
        self.ascender, self.descender, self.line_gap = self.i16(hhea + 4), self.i16(hhea + 6), self.i16(hhea + 8)
        nh = self.u16(hhea + 34)
        hmtx = self.tables["hmtx"][0]
        self.advances, self.lsbs = [], []
        for g in range(self.glyphs):
            i = min(g, nh - 1)
            self.advances.append(self.u16(hmtx + 4 * i))
            self.lsbs.append(self.i16(hmtx + 4 * g + 2) if g < nh else self.i16(hmtx + 4 * nh + 2 * (g - nh)))
        self.cmap = self.read_cmap()
        self.kern = self.read_kern()
        loca, glyf = self.tables["loca"][0], self.tables["glyf"][0]
        self.boxes, self.composite = [], []
        for g in range(self.glyphs):
            if long_loca:
                a, z = self.u32(loca + 4 * g), self.u32(loca + 4 * g + 4)
            else:
                a, z = 2 * self.u16(loca + 2 * g), 2 * self.u16(loca + 2 * g + 2)
            if z == a:
                self.boxes.append(None)
                self.composite.append(False)
            else:
                o = glyf + a
                self.boxes.append(tuple(self.i16(o + 2 + 2 * k) for k in range(4)))
                self.composite.append(self.i16(o) < 0)
        self.family, self.style = self.name(1), self.name(2)

    def u16(self, o: int) -> int:
        return struct.unpack(">H", self.data[o:o + 2])[0]

    def i16(self, o: int) -> int:
        return struct.unpack(">h", self.data[o:o + 2])[0]

    def u32(self, o: int) -> int:
        return struct.unpack(">I", self.data[o:o + 4])[0]

    def read_cmap(self) -> dict:
        cmap = self.tables["cmap"][0]
        for i in range(self.u16(cmap + 2)):
            r = cmap + 4 + 8 * i
            if (self.u16(r), self.u16(r + 2)) == (3, 1):
                sub = cmap + self.u32(r + 4)
                assert self.u16(sub) == 4
                segs = self.u16(sub + 6) // 2
                ends, out = sub + 14, {}
                for k in range(segs):
                    end, start = self.u16(ends + 2 * k), self.u16(ends + 2 + 2 * segs + 2 * k)
                    delta = self.u16(ends + 2 + 4 * segs + 2 * k)
                    ro_at = ends + 2 + 6 * segs + 2 * k
                    ro = self.u16(ro_at)
                    for c in range(start, end + 1):
                        if ro == 0:
                            g = (c + delta) & 0xFFFF
                        else:
                            g = self.u16(ro_at + ro + 2 * (c - start))
                            g = (g + delta) & 0xFFFF if g else 0
                        if g and c != 0xFFFF:
                            out[c] = g
                return out
        raise AssertionError("no (3, 1) cmap")

    def read_kern(self) -> dict:
        kern = self.tables["kern"][0]
        sub = kern + 4
        pairs = {}
        for k in range(self.u16(sub + 6)):
            at = sub + 14 + 6 * k
            pairs[(self.u16(at), self.u16(at + 2))] = self.i16(at + 4)
        return pairs

    def name(self, ident: int) -> str:
        name = self.tables["name"][0]
        strings = name + self.u16(name + 4)
        for i in range(self.u16(name + 2)):
            r = name + 6 + 12 * i
            p, e, lang, nid, ln, off = struct.unpack(">6H", self.data[r:r + 12])
            if (p, e, lang, nid) == (3, 1, 0x409, ident):
                return self.data[strings + off:strings + off + ln].decode("utf-16-be")
        return ""

    def glyph(self, c: str) -> int:
        return self.cmap.get(ord(c), 0)


# -- the layout rules, in Python ------------------------------------------------

def py_layout(f: Sfnt, text: str, px: float, max_width: float = 0.0, align: str = "left",
              line_height: float = 1.0, tab: int = 4):
    """(glyphs as (glyph, x, y), width, height, lines), as the module's
    documentation describes its layout."""
    s = px / f.upem
    space = f.glyph(" ")
    tab_w = tab * f.advances[space] * s
    lines = []                        # (glyphs as (glyph, x), width)
    cur, pen, prev, line_end, has_word = [], 0.0, -1, 0.0, False

    def kern(a: int, b: int) -> float:
        return f.kern.get((a, b), 0) * s if a >= 0 else 0.0

    def place(gs, pen, prev):
        xs = []
        for g in gs:
            pen += kern(prev, g)
            xs.append(pen)
            pen += f.advances[g] * s
            prev = g
        return pen, xs

    for para_i, para in enumerate(text.split("\n")):
        if para_i > 0:
            lines.append((cur, line_end))
            cur, pen, prev, line_end, has_word = [], 0.0, -1, 0.0, False
        i = 0
        while i < len(para):
            while i < len(para) and para[i] in " \t":
                if para[i] == "\t":
                    if tab_w > 0:
                        pen = (math.floor(pen / tab_w) + 1) * tab_w
                    prev = -1
                else:
                    pen += kern(prev, space) + f.advances[space] * s
                    prev = space
                i += 1
            word = []
            while i < len(para) and para[i] not in " \t":
                if ord(para[i]) >= 0x20:
                    word.append(f.glyph(para[i]))
                i += 1
            if not word:
                continue
            end, xs = place(word, pen, prev)
            if max_width > 0 and has_word and end > max_width:
                lines.append((cur, line_end))
                cur = []
                end, xs = place(word, 0.0, -1)
            cur += list(zip(word, xs))
            pen = line_end = end
            prev = word[-1]
            has_word = True
    if text:
        lines.append((cur, line_end))
    widest = max((w for _, w in lines), default=0.0)
    box = max_width if max_width > 0 else widest
    asc, desc = f.ascender * s, f.descender * s
    line_px = (f.ascender - f.descender + f.line_gap) * s * line_height
    out = []
    for k, (gs, w) in enumerate(lines):
        off = {"left": 0.0, "center": (box - w) / 2, "right": box - w}[align]
        out += [(g, x + off, asc + k * line_px) for g, x in gs]
    height = asc - desc + (len(lines) - 1) * line_px if lines else 0.0
    return out, widest, height, len(lines)


def outline_area(line: str) -> tuple[float, float]:
    """The exact area inside a printed outline (font units, non-zero rule
    assumed not to overlap) and its control polygon's length."""
    t = line.split(" ")
    area, length, i = 0.0, 0.0, 0
    cur = start = (0.0, 0.0)

    def cross(a, b):
        return a[0] * b[1] - a[1] * b[0]

    def dist(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1])

    while i < len(t):
        op = t[i]
        if op == "M":
            cur = start = (float(t[i + 1]), float(t[i + 2]))
            i += 3
        elif op == "L":
            p = (float(t[i + 1]), float(t[i + 2]))
            area += cross(cur, p) / 2
            length += dist(cur, p)
            cur = p
            i += 3
        elif op == "Q":
            c, p = (float(t[i + 1]), float(t[i + 2])), (float(t[i + 3]), float(t[i + 4]))
            area += cross(cur, p) / 2 + cross((c[0] - cur[0], c[1] - cur[1]), (p[0] - cur[0], p[1] - cur[1])) / 3
            length += dist(cur, c) + dist(c, p)
            cur = p
            i += 5
        elif op == "Z":
            area += cross(cur, start) / 2
            length += dist(cur, start)
            cur = start
            i += 1
        else:
            raise AssertionError(f"unexpected {op!r} in an outline")
    return abs(area), length


def _hex(s: str) -> str:
    return s.encode("utf-8").hex()


def _unhex(h: str) -> bytes:
    return b"" if h == "-" else bytes.fromhex(h)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class FontTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.plain = im.build_driver(DRIVER, cls.tmp.name)
        cls.checked = im.build_driver(DRIVER, cls.tmp.name, checked=True)
        with open(TTF, "rb") as fh:
            cls.sfnt = Sfnt(fh.read())
        with open(TTC, "rb") as fh:
            ttc = fh.read()
        cls.bold = Sfnt(ttc, 1)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def commands(self, lines: list[str], argv: list[str] | None = None) -> list[str]:
        argv = list(argv or self.plain) + ["--commands"]
        proc = subprocess.run(argv, input="\n".join(lines) + "\n", capture_output=True, text=True, timeout=900)
        self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
        out = proc.stdout.split("\n")[:-1]
        self.assertEqual(len(out), len(lines), proc.stderr[-2000:])
        return out

    # -- parsing --------------------------------------------------------------

    def test_names_and_metrics(self) -> None:
        info = {f["path"]: f for f in im.manifest()["fonts"]}["fonts/MylaTestSans.ttf"]
        out = self.commands([f"metrics {TTF} 0", f"metrics {TTC} 0", f"metrics {TTC} 1", f"metrics {TTC} 2",
                             f"metrics {TTF} 1"])
        f = self.sfnt
        want = f"Myla Test Sans|Regular|{info['units_per_em']}|{info['ascender']}|{info['descender']}|" \
               f"{info['line_gap']}|{info['glyphs']}"
        self.assertEqual(out[0], want)
        self.assertEqual(out[0], f"{f.family}|{f.style}|{f.upem}|{f.ascender}|{f.descender}|{f.line_gap}|{f.glyphs}")
        self.assertEqual(out[1], want)
        b = self.bold
        self.assertEqual(out[2], f"{b.family}|{b.style}|{b.upem}|{b.ascender}|{b.descender}|{b.line_gap}|{b.glyphs}")
        self.assertEqual(b.style, "Bold")
        self.assertEqual(out[3], "err no face 2 in the file")
        self.assertEqual(out[4], "err no face 1 in the file")

    def test_advances_bearings_and_boxes(self) -> None:
        with open(TTC, "rb") as fh:
            regular = Sfnt(fh.read(), 0)
        for path, f in ((TTF, self.sfnt), (TTC, regular)):
            (line,) = self.commands([f"glyphs {path}"])
            got = line.split(";")
            self.assertEqual(len(got), f.glyphs)
            composites = 0
            for g, item in enumerate(got):
                adv, lsb, *box = item.split(",")
                with self.subTest(path=path, glyph=g):
                    self.assertEqual((int(adv), int(lsb)), (f.advances[g], f.lsbs[g]))
                    want = f.boxes[g]
                    self.assertEqual(None if box == ["-"] else tuple(int(v) for v in box), want)
                composites += f.composite[g]
            self.assertEqual(composites, 49)
        info = {f["path"]: f for f in im.manifest()["fonts"]}["fonts/MylaTestSans.ttf"]
        for ch, adv in info["advances"].items():
            self.assertEqual(self.sfnt.advances[self.sfnt.glyph(ch)], adv)

    def test_cmap(self) -> None:
        f = self.sfnt
        cps = sorted(f.cmap) + [0x41F, 0x2603, 0xFFFF, 0x1F600, 0x10FFFF, 0x7F, 0x0]
        (line,) = self.commands([f"cmap {TTF} {','.join(map(str, cps))}"])
        got = [int(v) for v in line.split(",")]
        self.assertEqual(got, [f.cmap.get(c, 0) for c in cps])
        self.assertGreater(len(f.cmap), 150)

    def test_kerning(self) -> None:
        f = self.sfnt
        pairs = sorted(f.kern) + [(a, b) for (b, a) in sorted(f.kern) if (a, b) not in f.kern][:50] + [(0, 0), (175, 175)]
        (line,) = self.commands([f"kern {TTF} {','.join(f'{a}.{b}' for a, b in pairs)}"])
        got = [int(v) for v in line.split(",")]
        self.assertEqual(got, [f.kern.get(p, 0) for p in pairs])
        self.assertEqual(len(f.kern), 104)
        info = {e["path"]: e for e in im.manifest()["fonts"]}["fonts/MylaTestSans.ttf"]
        for pair, k in info["kern_sample"].items():
            self.assertEqual(f.kern[(f.glyph(pair[0]), f.glyph(pair[1]))], k)

    # -- rendering ------------------------------------------------------------

    def glyph_differences(self, argv: list[str]):
        rs = [r for r in im.renders("freetype-unhinted") if "dx" in r]
        out = self.commands([f"glyph {TTF} {ord(r['text'])} {r['px']} {r['dx']}" for r in rs], argv)
        rows = []
        for r, line in zip(rs, out):
            x, y, w, h, data = line.split(" ")
            x, y, w, h = int(x), int(y), int(w), int(h)
            got = _unhex(data)
            want = im.read_pam_file(os.path.join(im.DATA, r["pam"]))
            diffs = [abs(got[i] - want.samples[i]) for i in range(len(got))] if (w, h) == (want.width, want.height) else []
            rows.append((r, (x, y, w, h), (r["left"], -r["top"], want.width, want.height), diffs))
        return rows

    def test_glyphs_match_freetype(self) -> None:
        worst, total, n = 0, 0, 0
        for r, got_box, want_box, diffs in self.glyph_differences(self.plain):
            with self.subTest(r["text"], px=r["px"], dx=r["dx"]):
                self.assertEqual(got_box, want_box)
                self.assertLessEqual(max(diffs), GLYPH_MAX)
                self.assertLessEqual(sum(diffs) / len(diffs), GLYPH_MEAN)
            if diffs:
                worst, total, n = max(worst, max(diffs)), total + sum(diffs), n + len(diffs)
        self.assertGreater(n, 10000)
        self.assertLessEqual(worst, GLYPH_MAX)

    def test_glyphs_checked_are_the_same(self) -> None:
        rs = [r for r in im.renders("freetype-unhinted") if "dx" in r][:12]
        cmds = [f"glyph {TTF} {ord(r['text'])} {r['px']} {r['dx']}" for r in rs]
        self.assertEqual(self.commands(cmds, self.checked), self.commands(cmds, self.plain))

    def test_advances_match_freetype(self) -> None:
        f = self.sfnt
        for r in im.renders("freetype-unhinted"):
            if "advance" in r:
                adv = f.advances[f.glyph(r["text"])] * r["px"] / f.upem
                self.assertAlmostEqual(adv, r["advance"], delta=1 / 65536)

    def text_differences(self, how: str):
        rows = []
        for r in im.renders("freetype-unhinted"):
            if "dx" in r:
                continue
            x0, y0 = r["origin"]
            (line,) = self.commands([f"text {TTF} {r['px']} {x0} {y0} {r['width']} {r['height']} {how} "
                                     f"{_hex(r['text'])}"])
            got = _unhex(line)
            want = im.read_pam_file(os.path.join(im.DATA, r["pam"])).samples
            rows.append((r, [abs(a - b) for a, b in zip(got, want)]))
        return rows

    def test_strings_match_freetype(self) -> None:
        rows = self.text_differences("exact")
        self.assertEqual(len(rows), 2)
        for r, diffs in rows:
            with self.subTest(r["text"]):
                self.assertEqual(len(diffs), r["width"] * r["height"])
                self.assertLessEqual(max(diffs), TEXT_MAX)
        for r, diffs in self.text_differences("cached"):
            with self.subTest(r["text"], how="cached"):
                self.assertLessEqual(max(diffs), CACHED_MAX)
                self.assertLessEqual(sum(diffs) / len(diffs), CACHED_MEAN)

    def test_masks_cover_the_outlines_exact_area(self) -> None:
        f = self.sfnt
        gs = [g for g in range(f.glyphs) if f.boxes[g] is not None]
        chars = {g: c for c, g in f.cmap.items()}
        gs = [g for g in gs if g in chars]
        outlines = self.commands([f"outline {TTF} {g}" for g in gs])
        px = 48
        masks = self.commands([f"glyph {TTF} {chars[g]} {px} 0.0" for g in gs])
        s = px / f.upem
        checked = 0
        for g, o, m in zip(gs, outlines, masks):
            if o == "-":
                continue
            area, length = outline_area(o)
            covered = sum(_unhex(m.split(" ")[4])) / 255
            with self.subTest(glyph=g, char=chr(chars[g])):
                self.assertLessEqual(abs(covered - area * s * s), length * s / 16 + 0.5)
            checked += 1
        self.assertGreater(checked, 150)

    # -- layout ---------------------------------------------------------------

    def check_layouts(self, cases) -> None:
        f = self.sfnt
        lines = [f"layout {TTF} {px} {mw} {al} {lh} {_hex(t)}" for t, px, mw, al, lh in cases]
        for (t, px, mw, al, lh), line in zip(cases, self.commands(lines)):
            words = line.split(" ")
            width, height, count = float(words[0]), float(words[1]), int(words[2])
            got = [(int(g), float(x), float(y)) for g, x, y in (w.split(":") for w in words[3:])]
            want, w_width, w_height, w_count = py_layout(f, t, px, mw, al, lh)
            with self.subTest(text=t, px=px, max_width=mw, align=al):
                self.assertEqual(count, w_count)
                self.assertAlmostEqual(width, w_width, delta=1e-3)
                self.assertAlmostEqual(height, w_height, delta=1e-3)
                self.assertEqual([g for g, _, _ in got], [g for g, _, _ in want])
                for (_, x, y), (_, wx, wy) in zip(got, want):
                    self.assertAlmostEqual(x, wx, delta=1e-3)
                    self.assertAlmostEqual(y, wy, delta=1e-3)

    def test_layout(self) -> None:
        self.check_layouts([
            ("AVATAR To Yo", 24, 0, "left", 1),
            ("Hello, World!", 16, 0, "left", 1),
            ("", 16, 0, "left", 1),
            ("one\ntwo\n", 16, 0, "left", 1),
            ("  indented, then   wide   gaps  ", 13, 0, "left", 1),
            ("a\tb\t\tc", 20, 0, "left", 1),
            ("The quick brown fox jumps over the lazy dog", 16, 120, "left", 1),
            ("The quick brown fox jumps over the lazy dog", 16, 120, "center", 1.5),
            ("The quick brown fox jumps over the lazy dog", 16, 120, "right", 0.8),
            ("Unbreakablewordlongerthanthewidth and more", 16, 50, "left", 1),
            ("Ångström façade naïve", 20, 0, "center", 1),
            ("Ligne un\n\nligne trois", 11, 0, "right", 2),
        ])

    def test_random_layouts(self) -> None:
        rng = random.Random(943)
        alphabet = "abcdefghijklmnopqrstuvwxyzAVTYoé,.!?"
        cases = []
        for _ in range(200):
            words = ["".join(rng.choice(alphabet) for _ in range(rng.randrange(1, 9))) for _ in range(rng.randrange(1, 20))]
            text = ""
            for w in words:
                text += w + rng.choice([" ", " ", " ", "  ", "\n", "\t"])
            cases.append((text, rng.choice([9, 12, 16, 23.5]), rng.choice([0, 40, 80, 150.5]),
                          rng.choice(["left", "center", "right"]), rng.choice([1, 1.25])))
        self.check_layouts(cases)

    # -- fuzzing --------------------------------------------------------------

    def fuzz(self, argv: list[str]) -> None:
        files = [TTF, TTC]
        stats = im.fuzz(im.Driver(argv), files, self.tmp.name, truncate=files)
        self.assertGreater(stats.cases, im.FUZZ_CASES)
        self.assertGreater(stats.err, 0)
        self.assertGreater(stats.ok, 0)
        # and the rest of the lengths, a 17th of them
        cases = []
        for path in files:
            with open(path, "rb") as fh:
                data = fh.read()
            for n in range(513, len(data), 17):
                name = os.path.join(self.tmp.name, f"cut{len(cases)}")
                with open(name, "wb") as fh:
                    fh.write(data[:n])
                cases.append((name, None))
        results = im.Driver(argv).run(cases)
        bad = [(c, r.line) for c, r in zip(cases, results) if r.kind not in ("ok", "err")]
        self.assertEqual(bad, [])

    def test_fuzz_natively(self) -> None:
        self.fuzz(self.plain)

    def test_fuzz_checked(self) -> None:
        self.fuzz(self.checked)

    # -- the interpreter ------------------------------------------------------

    @unittest.skipIf(TEST_TARGET, "the interpreter's runs are the host's")
    def test_interpreted_answers_are_the_same(self) -> None:
        cmds = [f"metrics {TTC} 1", f"cmap {TTF} 65,233,8364,128512", f"kern {TTF} 34.53,53.80",
                f"glyph {TTF} 233 12 0.25", f"layout {TTF} 12 40 center 1 {_hex('Ta Yo, AV!')}"]
        self.assertEqual(self.commands(cmds, im.interpreter_argv(DRIVER)), self.commands(cmds))
        with open(TTF, "rb") as fh:
            data = fh.read()
        cases = []
        for n in (0, 11, 300, 4000):
            name = os.path.join(self.tmp.name, f"interp{n}")
            with open(name, "wb") as fh:
                fh.write(data[:n])
            cases.append((name, None))
        got = [r.kind for r in im.Driver(im.interpreter_argv(DRIVER)).run(cases + [(TTF, None)])]
        self.assertEqual(got, [r.kind for r in im.Driver(self.plain).run(cases + [(TTF, None)])])
        self.assertEqual(got[-1], "ok")


if __name__ == "__main__":
    unittest.main()
