"""Burn tests: `std.compress`'s compressor and `std.archive` (MYLA-352)
against Python's `zlib`, `gzip`, `tarfile` and `zipfile` and the `gzip`,
`tar` and `zip` commands.

The compressor: a Myla driver compresses inputs of several kinds (text from
the repository, random bytes, long runs, a mix, matches exactly 32 KiB back)
at every level, in each container, with the functions and with a writer
given its input in pieces of 1 to 9973 bytes (and once with a flush in the
middle); Python's `zlib`, `gzip -d` and std.compress's own decompressor must
give the input back, and the output must be about as small as zlib's.

The archives: tar files made by GNU tar (gnu, posix, ustar and v7 formats)
and by Python's `tarfile` (GNU, PAX and USTAR formats), plain and gzipped,
and zip files made by `zipfile` (stored, and deflated at every level) and
`zip`, of a tree with long names, non-ASCII names, empty files and
directories, symbolic and hard links; the driver lists each, and the list
must be Python's. The driver writes tar files, plain and through a gzip
writer, that `tarfile` and `tar -x` must read back. Zip files with a byte of
their data changed must fail as Python fails.

The corpus runs on the self-hosted native build, a small one on the
self-hosted interpreter.
"""
from __future__ import annotations

import calendar
import gzip
import io
import os
import random
import shutil
import struct
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
import zlib

from ._native import CAN_BUILD_NATIVE, SKIP_REASON
from ._tools import STDLIB_ROOT, selfhost_tool

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))

DRIVER = """import std.compress as compress
import std.archive as archive
import std.encoding as encoding
import std.hash as hash
import std.io as io
import std.num as num
import std.process as process
from std.archive import Entry, EntryKind, ArchiveError
from std.io import Read, Write
from std.fs import IoError

fun bytes_of(s: str) -> [uint8] {
    var out: [uint8] = []
    for i in 0..s.len() { out.push(s[i]) }
    return out
}

fun text(b: [uint8]) -> str {
    var sb = StringBuilder()
    for x in b { sb.append_byte(x) }
    return sb.build()
}

fun put(s: str) {
    match io.write(1, s) {
        Ok(()) => {}
        Err(_) => { process.exit(3) }
    }
}

fun stdin_bytes() -> [uint8] {
    var input = io.stdin()
    return bytes_of(input.read_to_end().unwrap_or(""))
}

fun fail(why: str) {
    io.eprintln(f"error: {why}")
    process.exit(1)
}

fun format_of(name: str) -> int {
    if name == "gzip" { return 1 }
    if name == "zlib" { return 2 }
    return 0
}

// `data` written to `e` in pieces of 1 to 9973 bytes, as bytes and as text
// by turns, flushed once in the middle if `flush`.
fun write_all<W: Write>(e: compress.Encoder<W>, data: [uint8], flush: bool) -> compress.Encoder<W> {
    var w = e
    var p = 0
    var k = 0
    var flushed = !flush
    while p < data.len() {
        k = k * 7 % 9973 + 1
        var end = p + k
        if end > data.len() { end = data.len() }
        if k % 2 == 0 {
            if w.write(data[p:end]).is_err() { process.exit(3) }
        } else {
            if w.write_str(text(data[p:end])).is_err() { process.exit(3) }
        }
        p = end
        if !flushed && p >= data.len() / 2 {
            if w.flush().is_err() { process.exit(3) }
            flushed = true
        }
    }
    return w
}

fun compressed(fmt: int, level: int, how: str, data: [uint8]) -> [uint8] {
    if how == "whole" {
        if fmt == 1 { return compress.gzip(data, level) }
        if fmt == 2 { return compress.zlib_compress(data, level) }
        return compress.deflate(data, level)
    }
    let flush = how == "flush"
    var r: Result<io.MemoryStream, IoError> = Err(IoError.Other(0))
    if fmt == 1 {
        r = write_all(compress.gzip_writer(io.memory_stream(), level), data, flush).finish()
    } else if fmt == 2 {
        r = write_all(compress.zlib_writer(io.memory_stream(), level), data, flush).finish()
    } else {
        r = write_all(compress.deflate_writer(io.memory_stream(), level), data, flush).finish()
    }
    return match r {
        Ok(m) => m.bytes()
        Err(_) => []
    }
}

fun kind_of(k: EntryKind) -> str {
    return match k {
        File => "f"
        Dir => "d"
        Symlink => "l"
        Hardlink => "h"
        Other(c) => f"o{c}"
    }
}

fun show(e: Entry) {
    let h = encoding.hex_encode
    let crc = hash.crc32_bytes(e.data)
    put(f"{kind_of(e.kind)} {h(bytes_of(e.name))} {e.mode} {e.mtime} {e.uid} {e.gid} {h(bytes_of(e.uname))} {h(bytes_of(e.gname))} {h(bytes_of(e.link))} {e.data.len()} {crc}\\n")
}

fun show_all(r: Result<[Entry], ArchiveError>) {
    match r {
        Ok(entries) => { for e in entries { show(e) } }
        Err(e) => fail(e.message())
    }
}

fun show_stream<R: Read>(t: archive.TarReader<R>) {
    var r = t
    while let Some(got) = r.next() {
        match got {
            Ok(e) => show(e)
            Err(e) => fail(e.message())
        }
    }
}

// A manifest line: kind name mode mtime uid gid uname gname link data, the
// texts in hex.
fun entry_of(line: str) -> Entry {
    let f = line.split(" ")
    let unh = (s: str) => encoding.hex_decode(s).unwrap_or([])
    let number = (s: str) => num.parse_int(s).unwrap_or(0)
    var e = archive.file(text(unh(f[1])), unh(f[9]))
    e.kind = match f[0] {
        "d" => EntryKind.Dir
        "l" => EntryKind.Symlink
        "h" => EntryKind.Hardlink
        _ => EntryKind.File
    }
    e.mode = number(f[2]) as int32
    e.mtime = number(f[3])
    e.uid = number(f[4]) as int32
    e.gid = number(f[5]) as int32
    e.uname = text(unh(f[6]))
    e.gname = text(unh(f[7]))
    e.link = text(unh(f[8]))
    return e
}

fun manifest() -> [Entry] {
    var out: [Entry] = []
    for line in text(stdin_bytes()).split("\\n") {
        if line.len() > 0 { out.push(entry_of(line)) }
    }
    return out
}

// compress <fmt> <level> <whole|stream|flush>, inflate <fmt>, tar-list,
// targz-list, zip-list, tar-write, targz-write <level>
fun main() {
    let argv = process.args()
    let mode = argv[1]
    if mode == "compress" {
        let level = num.parse_int(argv[3]).unwrap_or(6) as int
        put(text(compressed(format_of(argv[2]), level, argv[4], stdin_bytes())))
    } else if mode == "inflate" {
        let data = stdin_bytes()
        let fmt = format_of(argv[2])
        var r = compress.inflate(data)
        if fmt == 1 { r = compress.gunzip(data) }
        if fmt == 2 { r = compress.zlib_decompress(data) }
        match r {
            Ok(out) => put(text(out))
            Err(e) => fail(e.message())
        }
    } else if mode == "tar-list" {
        show_all(archive.tar_read(stdin_bytes()))
    } else if mode == "targz-list" {
        show_stream(archive.tar_reader(compress.gzip_reader(io.fd_stream(0))))
    } else if mode == "zip-list" {
        show_all(archive.zip_read(stdin_bytes()))
    } else if mode == "tar-write" {
        match archive.tar_write(manifest()) {
            Ok(b) => put(text(b))
            Err(e) => fail(e.message())
        }
    } else if mode == "targz-write" {
        let level = num.parse_int(argv[2]).unwrap_or(6) as int
        var t = archive.tar_writer(compress.gzip_writer(io.fd_stream(1), level))
        for e in manifest() {
            match t.add(e) {
                Ok(()) => {}
                Err(err) => fail(err.message())
            }
        }
        match t.finish() {
            Ok(gz) => {
                match gz.finish() {
                    Ok(_) => {}
                    Err(_) => fail("finish")
                }
            }
            Err(e) => fail(e.message())
        }
    }
}
"""


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
    noise = rng.randbytes(scale // 4)
    runs = b"".join(bytes([rng.randrange(4)]) * rng.randrange(1, 600) for _ in range(scale // 300))
    mixed = bytearray()
    while len(mixed) < scale:
        kind = rng.randrange(3)
        start = rng.randrange(len(text))
        if kind == 0:
            mixed += text[start:start + rng.randrange(1, 5000)]
        elif kind == 1:
            mixed += rng.randbytes(rng.randrange(1, 300))
        else:
            mixed += bytes([rng.randrange(256)]) * rng.randrange(1, 1000)
    # matches as far back as DEFLATE reaches, and one byte further
    block = rng.randbytes(32768)
    far = block + block[:5000] + rng.randbytes(1) + block[1:6000] + rng.randbytes(32767) + block[:300]
    return {"empty": b"", "byte": b"x", "text": text, "noise": noise, "runs": runs, "mixed": bytes(mixed),
            "far": far}


def _decompress(fmt: str, data: bytes) -> bytes:
    if fmt == "gzip":
        return gzip.decompress(data)
    d = zlib.decompressobj(-15 if fmt == "raw" else 15)
    out = d.decompress(data)
    if not d.eof or d.unused_data:
        raise zlib.error("not one whole stream")
    return out


def _tree(root: str) -> None:
    """A tree of files for the archivers: long and non-ASCII names, sizes
    around a block, an empty directory, links."""
    rng = random.Random(352)
    os.makedirs(os.path.join(root, "sub", "deeper"))
    os.makedirs(os.path.join(root, "empty dir"))
    long_dir = os.path.join(root, "d" * 90, "e" * 90)
    os.makedirs(long_dir)
    files = {
        "a.txt": b"hello\n",
        "empty": b"",
        "sub/block": rng.randbytes(512),
        "sub/block+1": rng.randbytes(513),
        "sub/deeper/text.md": _repo_text(70_000),
        "grüße-日本.txt": "unicode name".encode(),
        os.path.join("d" * 90, "e" * 90, "x" * 120): rng.randbytes(3000),
    }
    for name, data in files.items():
        with open(os.path.join(root, name), "wb") as fh:
            fh.write(data)
    with open(os.path.join(root, "n" * 150), "wb") as fh:
        fh.write(b"a long name\n")
    os.chmod(os.path.join(root, "a.txt"), 0o640)
    os.symlink("a.txt", os.path.join(root, "link"))
    os.symlink("t" * 150, os.path.join(root, "long link"))
    os.link(os.path.join(root, "sub", "block"), os.path.join(root, "hard"))
    for dirpath, dirnames, filenames in os.walk(root):
        for n in dirnames + filenames:
            p = os.path.join(dirpath, n)
            if not os.path.islink(p):
                os.utime(p, (1700000000, 1700000000 + len(n)))


def _short_tree(root: str) -> None:
    """A tree whose names fit ustar's fields, for the old formats."""
    os.makedirs(os.path.join(root, "sub"))
    for name, data in (("a.txt", b"hello\n"), ("sub/b.bin", bytes(range(256)) * 9), ("empty", b"")):
        with open(os.path.join(root, name), "wb") as fh:
            fh.write(data)
        os.utime(os.path.join(root, name), (1600000000, 1600000000))


def _kind(ti: tarfile.TarInfo) -> str:
    if ti.isreg():
        return "f"
    if ti.isdir():
        return "d"
    if ti.issym():
        return "l"
    if ti.islnk():
        return "h"
    return f"o{ord(ti.type)}"


def _enc(s: str) -> bytes:
    return s.encode("utf-8", "surrogateescape")


def _line(kind: str, name: bytes, mode: int, mtime: int, uid: int, gid: int, uname: bytes, gname: bytes,
          link: bytes, data: bytes) -> str:
    return (f"{kind} {name.hex()} {mode} {mtime} {uid} {gid} {uname.hex()} {gname.hex()} {link.hex()} "
            f"{len(data)} {zlib.crc32(data)}")


def _tar_listing(data: bytes) -> list[str]:
    """The driver's listing of a tar archive, as Python's tarfile reads it."""
    out = []
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tf:
        for ti in tf:
            body = tf.extractfile(ti).read() if ti.isreg() else b""
            out.append(_line(_kind(ti), _enc(ti.name), ti.mode & 0o7777, int(ti.mtime), ti.uid, ti.gid,
                             _enc(ti.uname), _enc(ti.gname), _enc(ti.linkname), body))
    return out


def _zip_listing(data: bytes) -> list[str]:
    """The driver's listing of a zip archive, as Python's zipfile reads it,
    with the time of an extended-timestamp field if there is one, else the
    MS-DOS time as UTC. A deflate entry must be one whole DEFLATE stream,
    as std.archive has it: zipfile takes one that stops short of its end or
    ends early, if the CRC-32 of what it gave is right."""
    out = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for zi in zf.infolist():
            body = zf.read(zi)
            if zi.compress_type == zipfile.ZIP_DEFLATED:
                nlen, elen = struct.unpack("<HH", data[zi.header_offset + 26:zi.header_offset + 30])
                start = zi.header_offset + 30 + nlen + elen
                d = zlib.decompressobj(-15)
                d.decompress(data[start:start + zi.compress_size])
                if not d.eof or d.unused_data:
                    raise zlib.error("not one whole DEFLATE stream")
            unix = zi.external_attr >> 16
            kind, mode = "f", 0o644
            if zi.create_system == 3 and unix:
                fmt = unix & 0o170000
                kind = "d" if fmt == 0o040000 else "l" if fmt == 0o120000 else "f"
                mode = unix & 0o7777
            elif zi.filename.endswith("/") or zi.external_attr & 0x10:
                kind, mode = "d", 0o755
            if zi.filename.endswith("/"):
                kind = "d"
            name = zi.filename.rstrip("/") if kind == "d" else zi.filename
            mtime = calendar.timegm(zi.date_time + (0, 0, 0))
            extra = zi.extra
            p = 0
            while p + 4 <= len(extra):
                hid, n = struct.unpack("<HH", extra[p:p + 4])
                if hid == 0x5455 and n >= 5 and extra[p + 4] & 1:
                    mtime = struct.unpack("<i", extra[p + 5:p + 9])[0]
                    break
                p += 4 + n
            link = b""
            if kind == "l":
                link, body = body, b""
            if kind == "d":
                body = b""
            # the name's bytes, as zipfile decoded them
            try:
                raw = name.encode("utf-8" if zi.flag_bits & 0x800 else "cp437")
            except UnicodeEncodeError:
                raw = name.encode("utf-8")
            out.append(_line(kind, raw, mode, mtime, 0, 0, b"", b"", link, body))
    return out


def _manifest(rng: random.Random) -> list[tuple]:
    """Entries for the driver to write: (kind, name, mode, mtime, uid, gid,
    uname, gname, link, data)."""
    return [
        ("f", "a.txt", 0o644, 1700000000, 1000, 100, "ann", "staff", "", b"hello\n"),
        ("d", "dir", 0o755, 1700000001, 0, 0, "root", "root", "", b""),
        ("f", "dir/" + "x" * 120, 0o600, 1700000002, 1, 2, "", "", "", rng.randbytes(1000)),
        ("f", "p/" + "q" * 140 + "/file", 0o644, 5, 0, 0, "", "", "", rng.randbytes(512)),
        ("f", "w/" + "é" * 80, 0o644, 7, 0, 0, "", "", "", b"accents"),
        ("l", "link", 0o777, 9, 0, 0, "", "", "a.txt", b""),
        ("l", "far link", 0o777, 9, 0, 0, "", "", "t/" * 70, b""),
        ("h", "hard", 0o644, 9, 0, 0, "", "", "a.txt", b""),
        ("f", "big ids", 0o644, 9, 3000000, 4000000, "u" * 40, "g" * 33, "", b"!"),
        ("f", "old", 0o644, -100, 0, 0, "", "", "", b""),
        ("f", "text.md", 0o644, 9, 0, 0, "", "", "", _repo_text(100_000)),
        ("f", "empty", 0o644, 9, 0, 0, "", "", "", b""),
    ]


def _manifest_text(entries: list[tuple]) -> bytes:
    lines = []
    for kind, name, mode, mtime, uid, gid, uname, gname, link, data in entries:
        lines.append(f"{kind} {name.encode().hex()} {mode} {mtime} {uid} {gid} {uname.encode().hex()} "
                     f"{gname.encode().hex()} {link.encode().hex()} {data.hex()}")
    return ("\n".join(lines) + "\n").encode()


def _manifest_listing(entries: list[tuple]) -> list[str]:
    out = []
    for kind, name, mode, mtime, uid, gid, uname, gname, link, data in entries:
        out.append(_line(kind, name.encode(), mode, mtime, uid, gid, uname.encode(), gname.encode(),
                         link.encode(), data))
    return out


class ArchiveTest(unittest.TestCase):
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

    def run_driver(self, native: bool, args: list[str], data: bytes) -> bytes:
        if native:
            argv = [self.native, *args]
        else:
            argv = [selfhost_tool("main"), "run", self.path, *args, "--stdlib", STDLIB_ROOT]
        proc = subprocess.run(argv, input=data, capture_output=True, timeout=600)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode(errors="replace"))
        return proc.stdout

    def listing(self, native: bool, mode: str, data: bytes) -> list[str]:
        return self.run_driver(native, [mode], data).decode().splitlines()

    # --- the compressor -----------------------------------------------------

    def check_compressor(self, native: bool, inputs: dict[str, bytes], levels, hows) -> None:
        for kind, data in inputs.items():
            for level in levels:
                for fmt in ("raw", "zlib", "gzip"):
                    for how in hows:
                        with self.subTest(input=kind, level=level, format=fmt, how=how):
                            out = self.run_driver(native, ["compress", fmt, str(level), how], data)
                            self.assertTrue(_decompress(fmt, out) == data, "Python's zlib gives another output")
                            back = self.run_driver(native, ["inflate", fmt], out)
                            self.assertTrue(back == data, "std.compress gives another output")
                            if fmt == "gzip" and shutil.which("gzip"):
                                proc = subprocess.run(["gzip", "-dc"], input=out, capture_output=True)
                                self.assertEqual(proc.returncode, 0, proc.stderr)
                                self.assertTrue(proc.stdout == data, "gzip -d gives another output")
                            if how == "whole" and fmt == "raw" and level > 0 and len(data) > 10000:
                                c = zlib.compressobj(level, zlib.DEFLATED, -15)
                                theirs = len(c.compress(data) + c.flush())
                                self.assertLessEqual(len(out), theirs * 1.02 + 16, "much bigger than zlib's")

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_compressor_natively(self) -> None:
        inputs = _inputs(random.Random(352), 200_000)
        self.check_compressor(True, inputs, range(10), ("whole", "stream"))
        self.check_compressor(True, {k: inputs[k] for k in ("mixed", "far")}, (0, 1, 6, 9), ("flush",))

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_compressor_large_natively(self) -> None:
        # long enough for the writer to slide its window down, and for many blocks
        text = _repo_text(3_000_000)
        self.check_compressor(True, {"3 MB": text}, (1, 6, 9), ("whole", "stream"))

    # --- tar and zip --------------------------------------------------------

    def tar_cases(self) -> list[tuple[str, bytes]]:
        """(name, archive) for tar files made by GNU tar and Python."""
        tree = os.path.join(self.tmp, "tree")
        short = os.path.join(self.tmp, "short")
        if not os.path.exists(tree):
            _tree(tree)
            _short_tree(short)
        cases = []
        for fmt in ("gnu", "posix", "ustar", "v7"):
            src = tree if fmt in ("gnu", "posix") else short
            for z in ("", "z"):
                proc = subprocess.run(["tar", f"--format={fmt}", f"-c{z}f", "-", "-C", src, "."],
                                      capture_output=True, check=True)
                cases.append((f"tar --format={fmt} {z}", proc.stdout))
        for fmt, src in ((tarfile.GNU_FORMAT, tree), (tarfile.PAX_FORMAT, tree), (tarfile.USTAR_FORMAT, short)):
            for comp in ("", "gz"):
                buf = io.BytesIO()
                with tarfile.open(fileobj=buf, mode=f"w:{comp}", format=fmt) as tf:
                    tf.add(src, arcname="top")
                cases.append((f"tarfile {fmt} {comp}", buf.getvalue()))
        return cases

    def zip_cases(self) -> list[tuple[str, bytes]]:
        """(name, archive) for zip files made by zipfile and `zip`."""
        tree = os.path.join(self.tmp, "tree")
        if not os.path.exists(tree):
            _tree(tree)
            _short_tree(os.path.join(self.tmp, "short"))
        cases = []
        for method, levels in ((zipfile.ZIP_STORED, (None,)), (zipfile.ZIP_DEFLATED, range(10))):
            for level in levels:
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", method, compresslevel=level) as zf:
                    for dirpath, dirnames, filenames in sorted(os.walk(tree)):
                        for n in sorted(dirnames) + sorted(filenames):
                            p = os.path.join(dirpath, n)
                            if not os.path.islink(p):
                                zf.write(p, os.path.relpath(p, tree))
                    zf.writestr("streamed.bin", random.Random(level or 0).randbytes(70_000))
                cases.append((f"zipfile {method} {level}", buf.getvalue()))
        if shutil.which("zip"):
            for flags in ("-0", "-6", "-9"):
                out = os.path.join(self.tmp, f"z{flags}.zip")
                if os.path.exists(out):
                    os.remove(out)
                subprocess.run(["zip", "-q", "-r", "-y", flags, out, "."], cwd=tree, check=True)
                with open(out, "rb") as fh:
                    cases.append((f"zip {flags}", fh.read()))
        return cases

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_tar_read_natively(self) -> None:
        for name, data in self.tar_cases():
            with self.subTest(case=name):
                want = _tar_listing(data)
                self.assertGreater(len(want), 3)
                if data[:2] == b"\x1f\x8b":
                    self.assertEqual(self.listing(True, "targz-list", data), want)
                    data = gzip.decompress(data)
                self.assertEqual(self.listing(True, "tar-list", data), want)

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_zip_read_natively(self) -> None:
        for name, data in self.zip_cases():
            with self.subTest(case=name):
                want = _zip_listing(data)
                self.assertGreater(len(want), 3)
                self.assertEqual(self.listing(True, "zip-list", data), want)

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_zip_corrupted_natively(self) -> None:
        rng = random.Random(1352)
        cases = self.zip_cases()
        for i in range(60):
            name, data = rng.choice(cases)
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                infos = [zi for zi in zf.infolist() if zi.compress_size > 0]
            zi = rng.choice(infos)
            nlen, elen = struct.unpack("<HH", data[zi.header_offset + 26:zi.header_offset + 30])
            start = zi.header_offset + 30 + nlen + elen
            b = bytearray(data)
            b[start + rng.randrange(zi.compress_size)] ^= 1 << rng.randrange(8)
            try:
                want = _zip_listing(bytes(b))
            except (zipfile.BadZipFile, zlib.error, EOFError):
                want = None
            with self.subTest(case=f"{name}, {zi.filename} broken"):
                proc = subprocess.run([self.native, "zip-list"], input=bytes(b), capture_output=True, timeout=60)
                if want is None:
                    self.assertEqual(proc.returncode, 1, proc.stderr)
                    self.assertTrue(proc.stderr.startswith(b"error: "), proc.stderr)
                else:
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    self.assertEqual(proc.stdout.decode().splitlines(), want)

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_tar_write_natively(self) -> None:
        entries = _manifest(random.Random(2352))
        want = _manifest_listing(entries)
        tar = self.run_driver(True, ["tar-write"], _manifest_text(entries))
        self.assertEqual(len(tar) % 512, 0)
        self.assertEqual(_tar_listing(tar), want)
        self.assertEqual(self.listing(True, "tar-list", tar), want)
        for level in (0, 1, 6, 9):
            with self.subTest(level=level):
                tgz = self.run_driver(True, ["targz-write", str(level)], _manifest_text(entries))
                self.assertEqual(_tar_listing(tgz), want)
                self.assertTrue(gzip.decompress(tgz) == tar, "the same tar, gzipped")
        # GNU tar lists it and extracts it
        out = os.path.join(self.tmp, "extracted")
        os.makedirs(out, exist_ok=True)
        proc = subprocess.run(["tar", "-xf", "-", "-C", out], input=tar, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        # but that a time before 1970 is "implausibly old"
        self.assertEqual([x for x in proc.stderr.splitlines() if b"implausibly old" not in x], [])
        for kind, name, mode, mtime, uid, gid, uname, gname, link, data in entries:
            p = os.path.join(out, name)
            if kind == "f":
                with open(p, "rb") as fh:
                    self.assertTrue(fh.read() == data, name)
                self.assertEqual(os.stat(p).st_mtime, mtime)
            elif kind == "l":
                self.assertEqual(os.readlink(p), link)
            elif kind == "d":
                self.assertTrue(os.path.isdir(p))
        proc = subprocess.run(["tar", "-tvf", "-"], input=tar, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(proc.stdout.splitlines()), len(entries))

    def test_interpreted(self) -> None:
        inputs = _inputs(random.Random(3352), 5_000)
        small = {k: inputs[k] for k in ("empty", "text", "mixed")}
        self.check_compressor(False, small, (0, 1, 6), ("whole",))
        self.check_compressor(False, {"text": inputs["text"]}, (6,), ("stream",))
        entries = _manifest(random.Random(4352))[:9]
        tar = self.run_driver(False, ["tar-write"], _manifest_text(entries))
        self.assertEqual(_tar_listing(tar), _manifest_listing(entries))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("a.txt", b"hello " * 100)
            zf.writestr("d/", b"")
        self.assertEqual(self.listing(False, "zip-list", buf.getvalue()), _zip_listing(buf.getvalue()))


if __name__ == "__main__":
    unittest.main()
