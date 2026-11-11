"""Burn tests: `std.xml` (MYLA-348) against Python's expat and the W3C
conformance suite.

A Myla driver reads length-framed documents from stdin and writes, for each,
James Clark's canonical XML of it (`ok <canonical>`) or the error
(`err <line> <col> <message>`), each answer framed by its length. It reads
every document three ways, by the pull reader, by the tree (`parse_document`,
whose `to_string` must read back as the same tree) and by the stream reader
fed in pieces of 1 to 7 bytes, and answers `mismatch` when they disagree.

- Generated documents: seeded random documents (elements, attributes, text
  with the five entities and character references, CR and CRLF line ends,
  CDATA, comments, processing instructions, the declaration, a DOCTYPE) must
  give the canonical form Python's expat gives; broken ones (characters
  deleted, inserted, duplicated, bytes that aren't UTF-8, the text cut short)
  must fail where expat fails and read the same where it doesn't.
- The W3C XML conformance suite's xmltest cases by James Clark
  (`xmlconf/xmltest/`): the standalone not-well-formed ones (`not-wf/sa`)
  must fail and the standalone valid ones (`valid/sa`) must give the
  canonical form in `valid/sa/out/`, for every case inside the module's
  subset: a not-wf case without a DOCTYPE, a valid case whose internal subset
  declares no entities and no attributes (the module skips a DTD). The cases
  outside it are run and counted too. The suite is fetched as the YAML
  suite is, not vendored as toml-test is: James Clark's licence lets the
  cases be passed on only as the unmodified archive (MYLA-424). The test
  looks for it in `$MYLA_XMLTS` (the folder holding `xmlconf/`), else
  downloads https://www.w3.org/XML/Test/xmlts20130923.tar.gz once, checks
  its SHA-256 and extracts it into `build/xmlts/`; without either it is
  skipped.

The corpora run on the self-hosted native build, a small one on the
self-hosted interpreter.
"""
from __future__ import annotations

import hashlib
import os
import random
import re
import subprocess
import sys
import tarfile
import tempfile
import unittest
import xml.parsers.expat

from ._native import CAN_BUILD_NATIVE, SKIP_REASON
from ._tools import STDLIB_ROOT, selfhost_tool

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))

DRIVER = r'''from std.io import stdin, write, Reader, Read
from std.fs import IoError
from std.num import parse_int
import std.xml as xml
from std.xml import Event, Element, Node, XmlError

struct Input { r: Reader }

impl Input {
    // The next document: a line with its length in bytes, then the bytes.
    fun next(var self) -> Option<str> {
        let header = match self.r.read_line() {
            Ok(Some(line)) => line
            _ => ""
        }
        let n = match parse_int(header) {
            Some(v) => v as int32
            None => -1
        }
        if n < 0 { return None }
        return match self.r.read_exact(n) {
            Ok(Some(t)) => Some(t)
            _ => None
        }
    }
}

// A stream giving its bytes in pieces of 1 to 7 bytes.
struct Pieces { data: str, pos: int, step: int }

impl Read for Pieces {
    fun read(var self, n: int) -> Result<[uint8], IoError> {
        self.step = self.step % 7 + 1
        var end = self.pos + self.step
        if end > self.pos + n { end = self.pos + n }
        if end > self.data.len() { end = self.data.len() }
        var out: [uint8] = []
        for k in self.pos..end { out.push(self.data[k]) }
        self.pos = end
        return Ok(out)
    }
}

// James Clark's canonical XML.
struct Canon { sb: StringBuilder }

impl Canon {
    fun data(var self, s: str) {
        for k in 0..s.len() {
            let c = s[k]
            if c == '&' { self.sb.append("&amp;") }
            else if c == '<' { self.sb.append("&lt;") }
            else if c == '>' { self.sb.append("&gt;") }
            else if c == '"' { self.sb.append("&quot;") }
            else if c == '\t' { self.sb.append("&#9;") }
            else if c == '\n' { self.sb.append("&#10;") }
            else if c == '\r' { self.sb.append("&#13;") }
            else { self.sb.append_byte(c) }
        }
    }

    fun start(var self, name: str, attrs: [(str, str)]) {
        self.sb.append("<")
        self.sb.append(name)
        for a in attrs.sorted_by((x, y) => x.0 < y.0) {
            self.sb.append(" ")
            self.sb.append(a.0)
            self.sb.append("=\"")
            self.data(a.1)
            self.sb.append("\"")
        }
        self.sb.append(">")
    }

    fun pi(var self, target: str, d: str) {
        self.sb.append("<?")
        self.sb.append(target)
        self.sb.append(" ")
        self.sb.append(d)
        self.sb.append("?>")
    }

    fun event(var self, ev: Event) {
        match ev {
            Start(name, attrs) => self.start(name, attrs)
            End(name) => {
                self.sb.append("</")
                self.sb.append(name)
                self.sb.append(">")
            }
            Text(t) => self.data(t)
            CData(t) => self.data(t)
            Pi(t, d) => self.pi(t, d)
            _ => {}
        }
    }

    fun node(var self, n: Node) {
        match n {
            Element(e) => self.element(e)
            Text(t) => self.data(t)
            Pi(t, d) => self.pi(t, d)
            Comment(_) => {}
        }
    }

    fun element(var self, e: Element) {
        self.start(e.name, e.attrs)
        for c in e.children { self.node(c) }
        self.sb.append("</")
        self.sb.append(e.name)
        self.sb.append(">")
    }
}

fun err_line(e: XmlError) -> str {
    return f"err {e.line} {e.col} {e.message()}"
}

// The canonical form by the pull reader, or the error.
fun by_events(text: str) -> str {
    var c = Canon { sb: StringBuilder() }
    var r = xml.reader(text)
    while true {
        match r.read_event() {
            Ok(Eof) => { return "ok " + c.sb.build() }
            Ok(ev) => c.event(ev)
            Err(e) => { return err_line(e) }
        }
    }
    unreachable()
}

// The same by the stream reader, in pieces.
fun by_stream(text: str) -> str {
    var c = Canon { sb: StringBuilder() }
    var r = xml.stream_reader(Pieces { data: text, pos: 0, step: 0 })
    while true {
        match r.read_event() {
            Ok(Eof) => { return "ok " + c.sb.build() }
            Ok(ev) => c.event(ev)
            Err(e) => { return err_line(e) }
        }
    }
    unreachable()
}

// The same by the tree, whose `to_string` must read back as the same tree.
fun by_tree(text: str) -> str {
    match xml.parse_document(text) {
        Ok(d) => {
            var c = Canon { sb: StringBuilder() }
            for n in d.prolog { c.node(n) }
            c.element(d.root)
            for n in d.epilog { c.node(n) }
            match xml.parse(xml.to_string(d.root)) {
                Ok(back) => { if back != d.root { return "writer: a different tree" } }
                Err(e) => { return "writer: " + err_line(e) }
            }
            return "ok " + c.sb.build()
        }
        Err(e) => { return err_line(e) }
    }
}

fun main() {
    var input = Input { r: stdin() }
    while true {
        match input.next() {
            Some(text) => {
                let a = by_events(text)
                let b = by_tree(text)
                let c = by_stream(text)
                var out = a
                if b != a { out = "mismatch tree: " + b + " / events: " + a }
                else if c != a { out = "mismatch stream: " + c + " / events: " + a }
                let w = write(1, f"{out.len()}\n{out}\n")
            }
            None => { return }
        }
    }
}
'''


# --- The reference: expat --------------------------------------------------------------

def _escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
            .replace("\t", "&#9;").replace("\n", "&#10;").replace("\r", "&#13;"))


def _expat_canonical(data: bytes) -> str | None:
    """The canonical form of `data` by expat, or None if expat refuses it."""
    p = xml.parsers.expat.ParserCreate()
    p.ordered_attributes = True
    out: list[str] = []

    def start(name, attrs):
        pairs = sorted(zip(attrs[0::2], attrs[1::2]))
        out.append("<" + name + "".join(f' {k}="{_escape(v)}"' for k, v in pairs) + ">")

    p.StartElementHandler = start
    p.EndElementHandler = lambda name: out.append(f"</{name}>")
    p.CharacterDataHandler = lambda d: out.append(_escape(d))
    p.ProcessingInstructionHandler = lambda t, d: out.append(f"<?{t} {d}?>")
    try:
        p.Parse(data, True)
    except (xml.parsers.expat.ExpatError, LookupError):   # LookupError: an unknown encoding
        return None
    return "".join(out)


# --- Generated documents ---------------------------------------------------------------

_NAMES = ["a", "b", "doc", "x:y", "_n", "é", "λx", "a-b.c", "n1", "Ω", "ns:é"]
_TEXT = ["t", "word", " ", "\n", "\r\n", "\r", "\t", "&amp;", "&lt;", "&gt;", "&quot;", "&apos;",
         "&#65;", "&#x20AC;", "&#10;", "&#13;", "&#x9;", "é", "😀", ">", "]", "]]", "'", '"', "€", " "]


def _text(rng: random.Random, n: int) -> str:
    return "".join(rng.choice(_TEXT) for _ in range(rng.randrange(n)))


def _attr_value(rng: random.Random, quote: str) -> str:
    pieces = [p for p in _TEXT if p != quote and p != "]]"] + ["<".replace("<", "&lt;")]
    return "".join(rng.choice(pieces) for _ in range(rng.randrange(5)))


def _misc(rng: random.Random) -> str:
    k = rng.randrange(3)
    if k == 0:
        return "<!--" + rng.choice(["", " c ", "a-b", "é\r\nx", "<&>"]) + "-->"
    if k == 1:
        return "<?" + rng.choice(["pi", "x-y", "target"]) + rng.choice(["", " ", " data", " a?b", " \r\nz"]) + "?>"
    return rng.choice([" ", "\n", "\r\n", "\t"])


def _element(rng: random.Random, depth: int) -> str:
    name = rng.choice(_NAMES)
    attrs = []
    for an in rng.sample(_NAMES, rng.randrange(4)):
        q = rng.choice(['"', "'"])
        attrs.append(rng.choice([" ", "\n", "  ", "\t"]) + an + rng.choice(["=", " = "]) + q + _attr_value(rng, q) + q)
    head = "<" + name + "".join(attrs) + rng.choice(["", " ", "\n"])
    if rng.random() < 0.2:
        return head + "/>"
    parts = []
    for _ in range(rng.randrange(5)):
        k = rng.randrange(6)
        if k <= 1:
            parts.append(_text(rng, 6))
        elif k == 2 and depth < 5:
            parts.append(_element(rng, depth + 1))
        elif k == 3:
            parts.append("<![CDATA[" + rng.choice(["", "x", "<&>", "]]", "] ]>", "\r\na"]) + "]]>")
        else:
            parts.append(_misc(rng))
    return head + ">" + _content(parts) + "</" + name + rng.choice(["", " ", "\n"]) + ">"


def _content(parts: list[str]) -> str:
    """The parts joined, with a `]]>` that the text between markup makes
    (not well-formed) written `]]&gt;`."""
    out, run = [], ""
    for p in parts:
        if p.startswith("<"):
            out += [run.replace("]]>", "]]&gt;"), p]
            run = ""
        else:
            run += p
    return "".join(out) + run.replace("]]>", "]]&gt;")


def _document(rng: random.Random, doctype: bool) -> str:
    out = ""
    if rng.random() < 0.4:
        out += rng.choice(['<?xml version="1.0"?>', "<?xml version='1.0' encoding='UTF-8'?>",
                           '<?xml version="1.0" encoding="utf-8" standalone="yes"?>', '<?xml version="1.0" standalone=\'no\' ?>'])
    for _ in range(rng.randrange(3)):
        out += _misc(rng)
    if doctype and rng.random() < 0.3:
        out += rng.choice(["<!DOCTYPE doc>", "<!DOCTYPE doc [<!ELEMENT doc ANY>]>",
                           '<!DOCTYPE doc SYSTEM "doc.dtd">', "<!DOCTYPE doc [\n<!-- ] -->\n<!ELEMENT doc ANY>\n]>"])
        for _ in range(rng.randrange(2)):
            out += _misc(rng)
    out += _element(rng, 0)
    for _ in range(rng.randrange(3)):
        out += _misc(rng)
    return out


def _wellformed(seed: int, count: int) -> list[bytes]:
    rng = random.Random(seed)
    return [_document(rng, True).encode("utf-8") for _ in range(count)]


def _broken(seed: int, count: int) -> list[bytes]:
    rng = random.Random(seed)
    noise = [b"<", b">", b"&", b";", b"/", b"=", b'"', b"'", b"!", b"?", b"-", b"[", b"]", b" ", b"#",
             b"x", b"\x01", b"\x0c", "é".encode(), "￾".encode(), b"\xff", b"\xc3", b"\r"]
    out = []
    while len(out) < count:
        data = _document(rng, False).encode("utf-8")
        i = rng.randrange(len(data) + 1)
        how = rng.randrange(4)
        if how == 0 and i < len(data):
            data = data[:i] + data[i + 1:]
        elif how == 1:
            data = data[:i] + rng.choice(noise) + data[i:]
        elif how == 2 and i < len(data):
            data = data[:i] + data[i:i + 1] + data[i:]
        else:
            data = data[:i]
        out.append(data)
    return out


# --- Running the driver -------------------------------------------------------------------

def _framed(docs: list[bytes]) -> bytes:
    return b"".join(str(len(d)).encode() + b"\n" + d for d in docs)


def _answers(out: bytes) -> list[str]:
    answers = []
    i = 0
    while i < len(out):
        nl = out.index(b"\n", i)
        n = int(out[i:nl])
        answers.append(out[nl + 1:nl + 1 + n].decode("utf-8", "replace"))
        i = nl + 1 + n + 1
    return answers


def _bad_version(doc: bytes) -> bool:
    """Whether `doc` starts with a declaration whose version isn't `1.` and
    digits (XML 1.0, 2.8), which expat takes."""
    m = re.match(rb"<\?xml\s+version\s*=\s*([\"'])(.*?)\1", doc)
    return m is not None and re.fullmatch(rb"1\.[0-9]+", m.group(2)) is None


def _read(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


_XMLTS_URL = "https://www.w3.org/XML/Test/xmlts20130923.tar.gz"
_XMLTS_SHA256 = "9b61db9f5dbffa545f4b8d78422167083a8568c59bd1129f94138f936cf6fc1f"


def _xmltest_in(root: str) -> str | None:
    for cand in (os.path.join(root, "xmlconf", "xmltest"), os.path.join(root, "xmltest"), root):
        if os.path.isdir(os.path.join(cand, "not-wf", "sa")):
            return cand
    return None


def _fetch_xmlts(root: str) -> None:
    """The suite's archive downloaded (by curl, which takes the proxy and
    its certificates from the environment), checked and extracted into
    `root`: the archive is data, its members only files and folders."""
    os.makedirs(os.path.dirname(root), exist_ok=True)
    with tempfile.TemporaryDirectory(dir=os.path.dirname(root)) as tmp:
        archive = os.path.join(tmp, "xmlts.tar.gz")
        subprocess.run(["curl", "-sSfL", "--max-time", "300", "-o", archive, _XMLTS_URL],
                       capture_output=True, timeout=330, check=True)
        with open(archive, "rb") as fh:
            if hashlib.sha256(fh.read()).hexdigest() != _XMLTS_SHA256:
                return
        out = os.path.join(tmp, "out")
        with tarfile.open(archive) as tar:
            tar.extractall(out, filter="data")
        os.replace(out, root)


def _xmlts() -> str | None:
    """The suite's `xmltest` folder: `$MYLA_XMLTS`'s, else `build/xmlts/`'s,
    downloaded once; None without one."""
    given = os.environ.get("MYLA_XMLTS")
    if given:
        return _xmltest_in(given)
    root = os.path.join(_REPO, "build", "xmlts")
    if _xmltest_in(root) is None and not os.path.exists(root):
        try:
            _fetch_xmlts(root)
        except (OSError, subprocess.SubprocessError, tarfile.TarError, TypeError):
            return None
    return _xmltest_in(root)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class XmlAgainstReferences(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        path = os.path.join(cls.tmp.name, "main.my")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(DRIVER)
        gen = selfhost_tool("gen_main")
        asm = subprocess.run([gen, path, STDLIB_ROOT], capture_output=True, text=True, check=True)
        native = os.path.join(cls.tmp.name, "native")
        with open(native + ".s", "w", encoding="utf-8") as fh:
            fh.write(asm.stdout)
        subprocess.run(["as", "--64", "-o", native + ".o", native + ".s"], check=True)
        subprocess.run(["ld", "-o", native, native + ".o"], check=True)
        cls.native = [native]
        cls.interpreter = [selfhost_tool("interp_main"), path, STDLIB_ROOT]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    lax_versions = 0

    def run_driver(self, argv: list[str], docs: list[bytes]) -> list[str]:
        proc = subprocess.run(argv, input=_framed(docs), capture_output=True, timeout=600)
        self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
        answers = _answers(proc.stdout)
        self.assertEqual(len(answers), len(docs))
        return answers

    def check_against_expat(self, argv: list[str], docs: list[bytes]) -> tuple[int, int]:
        """Each answer against expat's; the numbers of documents expat reads
        and refuses."""
        answers = self.run_driver(argv, docs)
        wrong = []
        read = refused = 0
        for doc, got in zip(docs, answers):
            want = _expat_canonical(doc)
            if want is not None and _bad_version(doc):
                want = None     # expat doesn't check the version number
                self.lax_versions += 1
            if want is None:
                refused += 1
                ok = got.startswith("err ")
            else:
                read += 1
                ok = got == "ok " + want
            if not ok:
                wrong.append(f"{doc!r}\n  expat: {want!r}\n  myla:  {got[:300]!r}")
        self.assertEqual(wrong[:5], [], f"{len(wrong)} of {len(docs)} differ")
        return read, refused

    def test_wellformed(self) -> None:
        read, refused = self.check_against_expat(self.native, _wellformed(1, 2000))
        self.assertEqual(refused, 0)
        print(f"\nstd.xml: {read} generated documents read as expat reads them", file=sys.stderr)

    def test_broken(self) -> None:
        read, refused = self.check_against_expat(self.native, _broken(2, 4000))
        self.assertGreater(refused, 2000)
        print(f"\nstd.xml: {refused} broken documents refused and {read} read, as expat does "
              f"({self.lax_versions} of the refused for a version number expat doesn't check)", file=sys.stderr)

    def test_interpreted(self) -> None:
        self.check_against_expat(self.interpreter, _wellformed(3, 40) + _broken(4, 60))

    def test_w3c_xmltest(self) -> None:
        root = _xmlts()
        if root is None:
            self.skipTest("the W3C suite couldn't be fetched into build/xmlts/ (set MYLA_XMLTS)")
        # not well-formed: every case without a DOCTYPE must fail
        nwf = sorted(f for f in os.listdir(os.path.join(root, "not-wf", "sa")) if f.endswith(".xml"))
        docs = [_read(os.path.join(root, "not-wf", "sa", f)) for f in nwf]
        answers = self.run_driver(self.native, docs)
        inside = [(f, a) for f, d, a in zip(nwf, docs, answers) if b"<!DOCTYPE" not in d]
        outside = [(f, a) for f, d, a in zip(nwf, docs, answers) if b"<!DOCTYPE" in d]
        accepted = [f for f, a in inside if not a.startswith("err ")]
        self.assertEqual(accepted, [], "not-wf cases read as well-formed")
        out_refused = sum(1 for _, a in outside if a.startswith("err "))
        # valid: the canonical form, for every case whose subset declares no
        # entities and no attributes
        vdir = os.path.join(root, "valid", "sa")
        valid = sorted(f for f in os.listdir(vdir) if f.endswith(".xml"))
        vdocs = [_read(os.path.join(vdir, f)) for f in valid]
        vanswers = self.run_driver(self.native, vdocs)
        v_in = v_in_ok = v_out = v_out_ok = 0
        wrong = []
        for f, d, a in zip(valid, vdocs, vanswers):
            want = "ok " + _read(os.path.join(vdir, "out", f)).decode("utf-8")
            subset = re.search(rb"<!DOCTYPE[^\[>]*\[(.*?)\]\s*>", d, re.S)
            # (an expected form that starts with a DOCTYPE lists notations)
            in_subset = not d.startswith((b"\xfe\xff", b"\xff\xfe")) and not want.startswith("ok <!DOCTYPE") and (
                subset is None or (b"<!ENTITY" not in subset.group(1) and b"<!ATTLIST" not in subset.group(1)))
            if in_subset:
                v_in += 1
                if a == want:
                    v_in_ok += 1
                else:
                    wrong.append(f"{f}: {a[:200]!r}, want {want[:200]!r}")
            else:
                v_out += 1
                v_out_ok += a == want
        self.assertEqual(wrong, [], "valid cases read wrongly")
        print(f"\nstd.xml, xmltest: not-wf/sa {len(inside)}/{len(inside)} refused without a DOCTYPE, "
              f"{out_refused}/{len(outside)} with one; valid/sa {v_in_ok}/{v_in} canonical inside the subset, "
              f"{v_out_ok}/{v_out} outside it", file=sys.stderr)


if __name__ == "__main__":
    unittest.main()
