"""Burn tests: `std.compress` (MYLA-344) against Python's `zlib` and `gzip`
and the `gzip` command.

Python and gzip compress inputs of several kinds (text from the repository,
random bytes, long runs, a mix of the three) at every level: `gzip -1` to
`-9`, `zlib.compress` at levels 0 to 9, raw DEFLATE (`wbits=-15`) at every
level and with each of zlib's strategies, smaller windows and memory levels,
and gzip files of several members. A Myla driver decompresses each one in
three ways: with the functions (`gunzip`, `zlib_decompress`, `inflate`), with
a stream over its standard input, and with a stream over an inner stream
that gives 1 to 13 bytes a read, read in pieces of 1 to 997 bytes; the output
must be Python's input. Corrupted data (a byte changed, the data cut short)
must fail where Python's zlib fails and give its output where it doesn't,
and never crash or hang.

The big corpus runs on the self-hosted native build, a small one on the
self-hosted interpreter.
"""
from __future__ import annotations

import gzip
import os
import random
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib

from ._native import CAN_BUILD_NATIVE, SKIP_REASON
from ._tools import STDLIB_ROOT, selfhost_tool

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))

DRIVER = """import std.compress as compress
import std.io as io
import std.process as process
from std.io import Read
from std.fs import IoError

// The bytes of the input in pieces of 1 to 13 bytes.
struct Trickle {
    data: [uint8],
    pos: int,
    step: int,
}

impl Read for Trickle {
    fun read(var self, n: int) -> Result<[uint8], IoError> {
        self.step = self.step % 13 + 1
        var end = self.pos + self.step
        if end > self.pos + n { end = self.pos + n }
        if end > self.data.len() { end = self.data.len() }
        let out = self.data[self.pos:end]
        self.pos = end
        return Ok(out)
    }

    fun read_str(var self, n: int) -> Result<str, IoError> {
        return Ok(text(self.read(n)?))
    }
}

fun text(b: [uint8]) -> str {
    var sb = StringBuilder()
    for x in b { sb.append_byte(x) }
    return sb.build()
}

fun bytes_of(s: str) -> [uint8] {
    var out: [uint8] = []
    for i in 0..s.len() { out.push(s[i]) }
    return out
}

fun put(s: str) {
    match io.write(1, s) {
        Ok(()) => {}
        Err(_) => { process.exit(3) }
    }
}

fun fail(e: compress.CompressError) {
    io.eprintln(f"error: {e}")
    process.exit(1)
}

// Everything `d` gives, written out: in reads of 64 KiB, or of 1 to 997
// bytes (`pieces`).
fun drain<R: Read>(d: compress.Decoder<R>, pieces: bool) {
    var r = d
    var k = 0
    while true {
        var n = 65536
        if pieces {
            k = k % 997 + 1
            n = k
        }
        match r.read_str(n) {
            Ok(s) => {
                if s.len() == 0 { return }
                if s.len() > n { process.exit(4) }
                put(s)
            }
            Err(_) => { fail(r.error().expect("a corrupt stream says why")) }
        }
    }
}

// `<format> <mode>`: gzip, zlib or raw; whole, stream or trickle.
fun main() {
    let argv = process.args()
    let format = argv[1]
    let mode = argv[2]
    if mode == "whole" {
        var input = io.stdin()
        let data = bytes_of(input.read_to_end().unwrap_or(""))
        var r = compress.inflate(data)
        if format == "gzip" { r = compress.gunzip(data) }
        if format == "zlib" { r = compress.zlib_decompress(data) }
        match r {
            Ok(out) => put(text(out))
            Err(e) => fail(e)
        }
    } else if mode == "stream" {
        let src = io.fd_stream(0)
        if format == "gzip" {
            drain(compress.gzip_reader(src), false)
        } else if format == "zlib" {
            drain(compress.zlib_reader(src), false)
        } else {
            drain(compress.inflate_reader(src), false)
        }
    } else {
        var input = io.stdin()
        let src = Trickle { data: bytes_of(input.read_to_end().unwrap_or("")), pos: 0, step: 0 }
        if format == "gzip" {
            drain(compress.gzip_reader(src), true)
        } else if format == "zlib" {
            drain(compress.zlib_reader(src), true)
        } else {
            drain(compress.inflate_reader(src), true)
        }
    }
}
"""

MODES = ("whole", "stream", "trickle")


def _repo_text(limit: int) -> bytes:
    """Text from the repository's sources and pages, `limit` bytes of it."""
    out = bytearray()
    for folder, suffix in (("selfhost", ".my"), ("docs/Language", ".md"), ("lib/std", ".my")):
        for name in sorted(os.listdir(os.path.join(_REPO, folder))):
            if name.endswith(suffix):
                with open(os.path.join(_REPO, folder, name), "rb") as fh:
                    out += fh.read()
            if len(out) >= limit:
                return bytes(out[:limit])
    return bytes(out[:limit])


def _inputs(rng: random.Random, scale: int) -> dict[str, bytes]:
    """Inputs of each kind, about `scale` bytes each."""
    text = _repo_text(scale)
    noise = bytes(rng.getrandbits(8) for _ in range(scale // 4))
    runs = b"".join(bytes([rng.randrange(4)]) * rng.randrange(1, 600) for _ in range(scale // 300))
    mixed = bytearray()
    while len(mixed) < scale:
        kind = rng.randrange(3)
        start = rng.randrange(len(text))
        if kind == 0:
            mixed += text[start:start + rng.randrange(1, 5000)]
        elif kind == 1:
            mixed += bytes(rng.getrandbits(8) for _ in range(rng.randrange(1, 300)))
        else:
            mixed += bytes([rng.randrange(256)]) * rng.randrange(1, 1000)
    return {"empty": b"", "byte": b"x", "text": text, "noise": noise, "runs": runs, "mixed": bytes(mixed)}


def _raw(data: bytes, level: int, wbits: int = -15, mem: int = 8, strategy: int = zlib.Z_DEFAULT_STRATEGY) -> bytes:
    c = zlib.compressobj(level, zlib.DEFLATED, wbits, mem, strategy)
    return c.compress(data) + c.flush()


def _gzip_cli(data: bytes, level: int, tmp: str, name: bool) -> bytes:
    """`gzip -<level>` of `data` from a file, with its name in the header
    (FNAME) or without it (`-n`)."""
    path = os.path.join(tmp, "input.txt")
    with open(path, "wb") as fh:
        fh.write(data)
    os.utime(path, (1700000000, 1700000000))
    flags = [f"-{level}", "-c"] + ([] if name else ["-n"])
    return subprocess.run(["gzip", *flags, path], capture_output=True, check=True).stdout


def _gzip_fields(data: bytes, level: int) -> bytes:
    """A gzip member with every optional header field: FEXTRA, FNAME,
    FCOMMENT and FHCRC (which the gzip command doesn't write)."""
    header = b"\x1f\x8b\x08" + bytes([2 | 4 | 8 | 16]) + struct.pack("<I", 1700000000) + b"\x02\x03"
    header += struct.pack("<H", 6) + b"AB\x02\x00hi" + b"name.txt\0" + b"a comment\0"
    header += struct.pack("<H", zlib.crc32(header) & 0xFFFF)
    return header + _raw(data, level) + struct.pack("<II", zlib.crc32(data), len(data) & 0xFFFFFFFF)


def _cases(inputs: dict[str, bytes], tmp: str, every: bool) -> list[tuple[str, str, bytes, bytes]]:
    """(name, format, compressed, original) for each input: every level and
    variant, or (`every` False) a few."""
    levels = range(10) if every else (0, 1, 6, 9)
    cases = []
    for kind, data in inputs.items():
        for level in levels:
            cases.append((f"{kind} zlib {level}", "zlib", zlib.compress(data, level), data))
            cases.append((f"{kind} raw {level}", "raw", _raw(data, level), data))
            if level > 0 and shutil.which("gzip"):
                cases.append((f"{kind} gzip -{level}", "gzip", _gzip_cli(data, level, tmp, level % 2 == 0), data))
        if not every:
            continue
        for strategy in ("Z_FILTERED", "Z_HUFFMAN_ONLY", "Z_RLE", "Z_FIXED"):
            cases.append((f"{kind} raw {strategy}", "raw", _raw(data, 6, strategy=getattr(zlib, strategy)), data))
        for wbits in (9, 12):
            cases.append((f"{kind} zlib wbits {wbits}", "zlib", _raw(data, 9, wbits=wbits), data))
        cases.append((f"{kind} zlib memlevel 1", "zlib", _raw(data, 9, wbits=15, mem=1), data))
        cases.append((f"{kind} gzip mtime", "gzip", gzip.compress(data, 9, mtime=1700000000), data))
        cases.append((f"{kind} gzip header fields", "gzip", _gzip_fields(data, 6), data))
        half = len(data) // 2
        two = gzip.compress(data[:half], 1) + gzip.compress(data[half:], 9)
        cases.append((f"{kind} gzip two members", "gzip", two, data))
    return cases


def _python(fmt: str, data: bytes, stream: bool) -> bytes | None:
    """What Python's `zlib` makes of `data`, as std.compress reads it: None
    for an error. Bytes after the end of a raw or zlib stream are an error
    for the functions; a stream ends before them. gzip data is members, each
    perhaps followed by zero bytes of padding, up to the end. (Python's
    `gzip` module would do, but it ignores the header's CRC and reserved
    flags, which zlib, the gzip command and std.compress check.)"""
    try:
        if fmt == "gzip":
            if not data:
                return None
            out = b""
            while data:
                d = zlib.decompressobj(31)
                out += d.decompress(data)
                if not d.eof:
                    return None
                data = d.unused_data.lstrip(b"\0")
            return out
        d = zlib.decompressobj(-15 if fmt == "raw" else 15)
        out = d.decompress(data)
        if not d.eof or (d.unused_data and not stream):
            return None
        return out
    except zlib.error:
        return None


def _corrupted(rng: random.Random, cases: list[tuple[str, str, bytes, bytes]], count: int):
    """`count` broken versions of the cases' data: a byte changed or added,
    or the data cut short."""
    out = []
    for i in range(count):
        name, fmt, data, _ = rng.choice(cases)
        if not data:
            continue
        b = bytearray(data)
        how = rng.randrange(4)
        if how == 0:
            b[rng.randrange(len(b))] ^= 1 << rng.randrange(8)
        elif how == 1:
            b[rng.randrange(len(b))] = rng.randrange(256)
        elif how == 2:
            del b[rng.randrange(len(b)):]
        else:
            b.insert(rng.randrange(len(b) + 1), rng.randrange(256))
        out.append((f"{name}, broken ({how})", fmt, bytes(b)))
    return out


class CompressTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.mkdtemp()
        path = os.path.join(cls.tmp, "driver.my")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(DRIVER)
        cls.path = path
        cls.native = None
        if CAN_BUILD_NATIVE:
            asm = subprocess.run([selfhost_tool("gen_main"), path, STDLIB_ROOT], capture_output=True, text=True,
                                 check=True)
            exe = os.path.join(cls.tmp, "driver")
            with open(exe + ".s", "w", encoding="utf-8") as fh:
                fh.write(asm.stdout)
            subprocess.run(["as", "--64", "-o", exe + ".o", exe + ".s"], check=True)
            subprocess.run(["ld", "-o", exe, exe + ".o"], check=True)
            cls.native = exe

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_driver(self, native: bool, fmt: str, mode: str, data: bytes) -> subprocess.CompletedProcess:
        if native:
            argv = [self.native, fmt, mode]
        else:
            argv = [selfhost_tool("main"), "run", self.path, fmt, mode, "--stdlib", STDLIB_ROOT]
        return subprocess.run(argv, input=data, capture_output=True, timeout=300)

    def check_cases(self, native: bool, cases, modes=MODES) -> None:
        for name, fmt, data, want in cases:
            for mode in modes:
                with self.subTest(case=name, mode=mode):
                    proc = self.run_driver(native, fmt, mode, data)
                    self.assertEqual(proc.returncode, 0, proc.stderr.decode(errors="replace"))
                    self.assertEqual(len(proc.stdout), len(want))
                    self.assertTrue(proc.stdout == want, "the output differs")

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_every_level_natively(self) -> None:
        rng = random.Random(344)
        cases = _cases(_inputs(rng, 300_000), self.tmp, every=True)
        self.check_cases(True, cases)

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_large_natively(self) -> None:
        text = _repo_text(4_000_000)
        cases = [("4 MB gzip -6", "gzip", _gzip_cli(text, 6, self.tmp, True), text),
                 ("4 MB zlib 9", "zlib", zlib.compress(text, 9), text)]
        self.check_cases(True, cases)

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_corrupted_natively(self) -> None:
        rng = random.Random(1344)
        cases = _cases(_inputs(rng, 20_000), self.tmp, every=False)
        for name, fmt, data in _corrupted(rng, cases, 400):
            for mode in MODES:
                want = _python(fmt, data, mode != "whole")
                with self.subTest(case=name, mode=mode):
                    proc = self.run_driver(True, fmt, mode, data)
                    if want is None:
                        self.assertEqual(proc.returncode, 1, proc.stderr.decode(errors="replace"))
                        self.assertTrue(proc.stderr.startswith(b"error: "), proc.stderr)
                    else:
                        self.assertEqual(proc.returncode, 0, proc.stderr.decode(errors="replace"))
                        self.assertTrue(proc.stdout == want, "the output differs")

    def test_interpreted(self) -> None:
        rng = random.Random(2344)
        inputs = _inputs(rng, 6_000)
        cases = [c for c in _cases(inputs, self.tmp, every=False) if c[0].split()[0] in ("text", "mixed", "empty")]
        self.check_cases(False, cases[::3])
        for name, fmt, data in _corrupted(rng, cases, 6):
            want = _python(fmt, data, False)
            with self.subTest(case=name):
                proc = self.run_driver(False, fmt, "whole", data)
                self.assertEqual(proc.returncode, 1 if want is None else 0, proc.stderr.decode(errors="replace"))
                if want is not None:
                    self.assertTrue(proc.stdout == want, "the output differs")


if __name__ == "__main__":
    unittest.main()
