"""Burn test: the format parsers' drivers built `--checked` (MYLA-555).

Only `test_archive` built its driver `--checked` as well as plain; the other
parsers' burn tests build theirs plain, where an integer overflow wraps, so
a parser that overflows on a document passes there (std.yaml's B5, a hex
scalar past 64 bits: `integer overflow` interpreted and checked, a float in
a plain build, MYLA-550). Here the drivers of `test_json`, `test_toml`,
`test_xml` and `test_yaml`, and two small ones for `std.ini` and
`std.csv`, are built plain and `--checked` and given their tests' corpora
and documents with numbers at and past every limit. Both builds must give
the same answers, and neither may end in a runtime error (D184: a parser
reports what it can't take as its error).

The corpora are the burn tests' own generators (and the YAML test suite's
texts when they are there, as `test_yaml` finds them), `CORPUS` documents
of each kind; MYLA_GENERATED=full gives ten times as many. With
MYLA_TEST_TARGET set the drivers are the target's.
"""
from __future__ import annotations

import os
import random
import subprocess
import tempfile
import unittest

from . import test_json, test_toml, test_xml, test_yaml
from ._differential import FULL, known_here
from ._native import CAN_BUILD_NATIVE, SKIP_REASON, Program, native_build, run_argv, write_program

CORPUS = 10000 if FULL else 1000

FRAMED_INPUT = """struct Input { r: Reader }

impl Input {
    // The next document: a line with its length in bytes, then the text.
    fun next(var self) -> Option<str> {
        let header = match self.r.read_line() {
            Ok(Some(line)) => line,
            _ => "",
        }
        let n = match parse_int(header) {
            Some(v) => v as int32,
            None => -1,
        }
        if n < 0 { return None }
        return match self.r.read_exact(n) {
            Ok(Some(t)) => Some(t),
            _ => None,
        }
    }
}

fun line(s: str) -> str { return s.replace("\\\\", "\\\\\\\\").replace("\\n", "\\\\n").replace("\\r", "\\\\r") }
"""

INI_DRIVER = """from std.io import stdin, println, Reader
from std.num import parse_int
import std.ini as ini

""" + FRAMED_INPUT + """
// each document read and written back, or its error
fun main() {
    var input = Input { r: stdin() }
    while let Some(text) = input.next() {
        match ini.parse(text) {
            Ok(doc) => {
                let w = ini.write(doc)
                let same = match ini.parse(w) {
                    Ok(back) => ini.write(back) == w,
                    Err(e) => false,
                }
                println(f"ok {same} " + line(w))
            }
            Err(e) => println(f"err {e}")
        }
    }
}
"""

CSV_DRIVER = """from std.io import stdin, println, Reader
from std.num import parse_int
import std.csv as csv

""" + FRAMED_INPUT + """
// each document's rows, written back, and its records, or its errors
fun main() {
    var input = Input { r: stdin() }
    while let Some(text) = input.next() {
        let rows = match csv.parse(text) {
            Ok(rows) => f"ok {rows.len()} " + line(csv.write(rows)),
            Err(e) => f"err {e}",
        }
        let semi = match csv.parse_with(text, ';') {
            Ok(rows) => f"ok {rows.len()}",
            Err(e) => f"err {e}",
        }
        let records = match csv.parse_records(text) {
            Ok(rs) => f"ok {rs.len()}",
            Err(e) => f"err {e}",
        }
        println(rows + " / " + semi + " / " + records)
    }
}
"""


# -- documents with numbers at and past the limits ----------------------------------

_BIG = ["9223372036854775807", "9223372036854775808", "18446744073709551615", "18446744073709551616",
        "99999999999999999999999999999999999999", "2147483647", "2147483648", "4294967296"]

JSON_EXTREMES = ([f"[{n}]" for n in _BIG] + [f"[-{n}]" for n in _BIG] +
                 [f"[1e{e}]" for e in ["308", "309", "400", "2147483647", "2147483648", "9223372036854775808",
                                        "-324", "-400", "-2147483648", "-2147483649", "99999999999999999999"]] +
                 ["[0.0000000000000000000000000000000000000001e-2147483647]", "[123456789e2147483640]",
                  '["\\uFFFF\\uD800\\uDFFF"]', "[" * 2000 + "]" * 2000, '{"a":' * 1000 + "1" + "}" * 1000])

TOML_EXTREMES = ([f"a = {n}\n" for n in _BIG] + [f"a = -{n}\n" for n in _BIG] +
                 [f"a = {p}{d}\n" for p, d in [("0x", "7FFFFFFFFFFFFFFF"), ("0x", "8000000000000000"),
                                                ("0x", "FFFFFFFFFFFFFFFF"), ("0x", "1_0000_0000_0000_0000"),
                                                ("0o", "777777777777777777777"), ("0o", "1777777777777777777777"),
                                                ("0o", "2000000000000000000000"), ("0b", "1" * 63), ("0b", "1" * 64),
                                                ("0b", "1" + "0" * 64)]] +
                 [f"a = 1e{e}\n" for e in ["308", "309", "400", "2147483648", "-400", "-2147483649"]] +
                 ["a = 9999-12-31T23:59:59.99999999999999999999Z\n", "a = 0000-01-01T00:00:00-23:59\n",
                  "a = 1979-05-27T07:32:00+99:99\n", "a = 2147483648-01-01\n", "a = 24:00:00\n",
                  "a = 1979-05-27T07:32:00.123456789123456789\n", "a = " + "[" * 1000 + "]" * 1000 + "\n"])

YAML_EXTREMES = ([f"a: {n}\n" for n in _BIG] + [f"a: -{n}\n" for n in _BIG] +
                 [f"mask: {p}{d}\n" for p, d in [("0x", "7FFFFFFFFFFFFFFF"), ("0x", "8000000000000000"),
                                                   ("0x", "FFFFFFFFFFFFFFFF"), ("0x", "10000000000000000"),
                                                   ("0o", "777777777777777777777"), ("0o", "1777777777777777777777"),
                                                   ("0o", "2000000000000000000000")]] +
                 [f"a: 1e{e}\n" for e in ["308", "309", "400", "2147483648", "-400", "-2147483649"]] +
                 ["a: [" + "[" * 500 + "]" * 500 + "]\n", "a: .inf\nb: -.Inf\nc: .NaN\n", "a: 0x\nb: 0o\nc: 0b1\n"])

# (1000 deep at most: the driver walks the tree, and `==` compares it, by
# recursion, which 3000 levels overflow on wasm32)
XML_EXTREMES = ([f"<a>&#{n};</a>".encode() for n in ["0", "9", "1114111", "1114112", "2147483647", "2147483648",
                                                     "4294967296", "9223372036854775808", "99999999999999999999"]] +
                [f"<a>&#x{n};</a>".encode() for n in ["10FFFF", "110000", "7FFFFFFF", "80000000", "FFFFFFFF",
                                                      "100000000", "FFFFFFFFFFFFFFFF", "10000000000000000"]] +
                [b"<a>" * 1000 + b"</a>" * 1000, b'<a b="' + b"&#65;" * 5000 + b'"/>'])

INI_EXTREMES = ["[" + "s" * 70000 + "]\n", "k=" + "v" * 70000 + "\n", "\n" * 70000 + "x\n", "=\n", "[]\n", "[a\n"]

CSV_EXTREMES = ["a" * 70000 + "\n", ",".join(["x"] * 20000) + "\n", "\n" * 70000, '"' + '""' * 30000 + '"\n',
                "a,b\n" + "1\n" * 1000, '"\n' * 1000]


# -- the corpora ---------------------------------------------------------------------

def _mutated(sources: list[bytes], seed: int, count: int) -> list[bytes]:
    """`sources` with a byte deleted, inserted or doubled, or cut short."""
    rng = random.Random(seed)
    noise = [b" ", b"\t", b"\n", b"\r\n", b"-", b":", b"#", b"'", b'"', b"\\", b"[", b"]", b"{", b"}", b",", b"=",
             b";", b"|", b">", b"?", b"&", b"*", b"!", b"%", b"0", b"9", b"x", b"e", b"\xc3\xa9"]
    out = []
    for _ in range(count):
        t = rng.choice(sources)
        i = rng.randrange(len(t) + 1)
        how = rng.randrange(4)
        if how == 0 and i < len(t):
            t = t[:i] + t[i + 1:]
        elif how == 1:
            t = t[:i] + rng.choice(noise) + t[i:]
        elif how == 2 and i < len(t):
            t = t[:i] + t[i:i + 1] + t[i:]
        else:
            t = t[:i]
        out.append(t)
    return out


def _ini_documents(seed: int, count: int) -> list[bytes]:
    rng = random.Random(seed)
    words = ["a", "key", "x.y", "Name", "ä", "1", "", " ", "=", ":", ";c", "#c", "[s]", "[", "]", "v=w", "\t"]
    docs = []
    for _ in range(count):
        lines = []
        for _ in range(rng.randrange(1, 12)):
            kind = rng.randrange(6)
            if kind == 0:
                lines.append("[" + "".join(rng.choice(words) for _ in range(rng.randrange(1, 3))) + "]")
            elif kind == 1:
                lines.append(rng.choice(["; ", "# ", ""]) + rng.choice(words))
            else:
                k = "".join(rng.choice(words) for _ in range(rng.randrange(0, 3)))
                v = "".join(rng.choice(words) for _ in range(rng.randrange(0, 4)))
                lines.append(f"{k}{rng.choice(['=', ':', ' = ', ''])}{v}")
        docs.append(rng.choice(["\n", "\r\n"]).join(lines).encode())
    return docs + _mutated(docs, seed + 1, count)


def _csv_documents(seed: int, count: int) -> list[bytes]:
    rng = random.Random(seed)
    fields = ["a", "1", "", "x y", '"q"', '"a,b"', '"line\nbreak"', '"""', '""', "é", "a\"b", ";", " "]
    docs = []
    for _ in range(count):
        width = rng.randrange(1, 5)
        rows = [",".join(rng.choice(fields) for _ in range(width if rng.random() < 0.9 else rng.randrange(1, 6)))
                for _ in range(rng.randrange(0, 6))]
        docs.append((rng.choice(["\n", "\r\n"]).join(rows) + rng.choice(["", "\n", "\r\n"])).encode())
    return docs + _mutated(docs, seed + 1, count)


def _yaml_documents(seed: int, count: int) -> list[bytes]:
    """Maps and lists of YAML 1.1's implicit types' pieces (`test_yaml`'s
    writer test's), and the YAML test suite's texts where `test_yaml` has
    them (not cloned here), each also mutated."""
    rng = random.Random(seed)
    docs = []
    for _ in range(count):
        lines = []
        for i in range(rng.randrange(1, 6)):
            scalar = "".join(rng.choice(test_yaml._PIECES) for _ in range(rng.randrange(1, 4)))
            lines.append(rng.choice([f"k{i}: {scalar}", f"- {scalar}", f"k{i}: [{scalar}, {scalar}]",
                                     f"k{i}:\n  - {scalar}", f'k{i}: "{scalar}"']))
        docs.append(("\n".join(lines) + "\n").encode())
    given = os.environ.get("MYLA_YAML_TEST_SUITE") or os.path.join(test_yaml._REPO, "build", "yaml-test-suite")
    if os.path.isdir(os.path.join(given, "229Q")):
        for _, d in test_yaml._cases(given):
            with open(os.path.join(d, "in.yaml"), "rb") as fh:
                docs.append(fh.read())
    return docs + _mutated([d for d in docs if d], seed + 1, count)


def _enc(docs) -> list[bytes]:
    return [d.encode() if isinstance(d, str) else d for d in docs]


def _framed(docs: list[bytes]) -> bytes:
    return b"".join(str(len(d)).encode() + b"\n" + d for d in docs)


# name: (driver, the corpus, the documents at the limits)
FORMATS = {
    "json": (test_json.DRIVER, lambda: _enc(test_json._valid_texts(31, CORPUS) + test_json._broken_texts(32, CORPUS)),
             JSON_EXTREMES),
    "toml": (test_toml.DRIVER,
             lambda: _enc(test_toml._valid_documents(33, CORPUS) + test_toml._broken_documents(34, CORPUS)),
             TOML_EXTREMES),
    "xml": (test_xml.DRIVER, lambda: test_xml._wellformed(35, CORPUS) + test_xml._broken(36, CORPUS), XML_EXTREMES),
    "yaml": (test_yaml.DRIVER, lambda: _yaml_documents(37, CORPUS), YAML_EXTREMES),
    "ini": (INI_DRIVER, lambda: _ini_documents(38, CORPUS), INI_EXTREMES),
    "csv": (CSV_DRIVER, lambda: _csv_documents(39, CORPUS), CSV_EXTREMES),
}

# documents that fail today, per format, with the task that fixes them
KNOWN: dict[str, dict] = {}


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class FormatsChecked(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def builds(self, name: str, source: str) -> dict[str, str]:
        path = write_program(self.tmp.name, source, f"{name}.my")
        out = {}
        for kind in ("plain", "checked"):
            out[kind] = os.path.join(self.tmp.name, f"{name}.{kind}")
            native_build(Program(path), out[kind], checked=kind == "checked")
        return out

    def run_driver(self, binary: str, docs: list[bytes]) -> tuple[int, bytes, bytes]:
        argv, exe = run_argv(binary)
        proc = subprocess.run(argv, executable=exe, input=_framed(docs), capture_output=True, timeout=600)
        return proc.returncode, proc.stdout, proc.stderr

    def failing(self, builds: dict[str, str], docs: list[bytes]) -> dict[bytes, str]:
        """The documents of `docs` the two builds answer differently or end
        with a runtime error on, each with what each build gave."""
        got = {k: self.run_driver(b, docs) for k, b in builds.items()}
        if got["plain"] == got["checked"] and got["plain"][0] == 0:
            return {}
        if len(docs) > 1:      # which documents: each half on its own
            half = len(docs) // 2
            return {**self.failing(builds, docs[:half]), **self.failing(builds, docs[half:])}
        return {docs[0]: "; ".join(f"{k}: exit {c}, {out[:120]!r} {err[:200]!r}" for k, (c, out, err) in got.items())}

    def check_format(self, name: str) -> None:
        source, corpus, extremes = FORMATS[name]
        known = {d.encode() if isinstance(d, str) else d: t for d, t in known_here(KNOWN.get(name, {})).items()}
        builds = self.builds(name, source)
        docs = corpus() + _enc(extremes)
        bad = self.failing(builds, docs)
        new = {d: why for d, why in bad.items() if d not in known}
        fixed = [d for d in known if d in docs and d not in bad]
        self.assertEqual(list(new.items())[:5], [], f"{len(new)} of {len(docs)} documents")
        self.assertEqual(fixed, [], "known failures that pass now: remove them from KNOWN")


def _make(name: str):
    def test(self):
        self.check_format(name)
    test.__name__ = f"test_{name}"
    return test


for _name in FORMATS:
    setattr(FormatsChecked, f"test_{_name}", _make(_name))


if __name__ == "__main__":
    unittest.main()
