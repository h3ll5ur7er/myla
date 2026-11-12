"""Burn tests: `std.yaml` (MYLA-349) against the YAML test suite.

The suite (https://github.com/yaml/yaml-test-suite, its data release) has a
directory per case: the YAML text (`in.yaml`), the parse events a conforming
parser reports (`test.event`) and, for a text that isn't YAML, a file
`error`. The events say what each case holds, so the cases split into:

- **in the subset**: no anchors, aliases, tags, directives, collections as
  keys or second documents. The value the events describe, with the plain
  scalars resolved by the YAML 1.2 core schema (below), must be what
  `std.yaml` parses, compared as `std.json` writes it (through `to_json`).
  A mapping that repeats a key must be refused (`DuplicateKey`), and an
  explicit key (`? a`), which the events don't show, may be.
- **left out**: a case that uses a feature the subset leaves out must be
  refused with the error that names one of its features, never read as
  something else.
- **not YAML**: the case must be refused, with any error.

What `std.yaml` reads, `to_string` writes and `parse` reads back must be the
same value. A Myla driver reads length-framed texts from stdin and prints, for
each, `ok <round trip> <json>` or `err <line> <col> <kind>`; it runs natively,
and a few cases run on the self-hosted interpreter too. The broken texts and
the numbers run through the driver built `--checked` as well, which must
answer as the plain build does: an integer overflow is an error there (D184,
MYLA-550: `0xFFFFFFFFFFFFFFFF` trapped).

The suite is data, not code: the test only reads its files. It looks for the
data release in `$MYLA_YAML_TEST_SUITE`, else clones its `data-2022-01-17`
tag into `build/yaml-test-suite` once, and is skipped when neither works.

The writer against a YAML 1.1 reader (MYLA-424): strings made of the pieces
of YAML 1.1's numbers, booleans, timestamps and keys are written by
`to_string`, as an item and as a key, and PyYAML (which reads YAML 1.1, as
most readers in use do) must read them back as the same strings. Skipped
without PyYAML.
"""
from __future__ import annotations

import json
import math
import os
import random
import re
import subprocess
import sys
import tempfile
import unittest

from ._native import CAN_BUILD_NATIVE, SKIP_REASON
from ._tools import STDLIB_ROOT, selfhost_tool

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_URL = "https://github.com/yaml/yaml-test-suite"
_TAG = "data-2022-01-17"

DRIVER = """from std.io import stdin, println, Reader
import std.yaml as yaml
import std.json as json
from std.num import parse_int

struct Input { r: Reader }

impl Input {
    // The next text: a line with its length in bytes, then the text.
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

fun kind_name(e: yaml.YamlError) -> str {
    return match e.kind {
        Anchor => "Anchor"
        Alias => "Alias"
        Tag => "Tag"
        Directive => "Directive"
        MultipleDocuments => "MultipleDocuments"
        ExplicitKey => "ExplicitKey"
        ComplexKey => "ComplexKey"
        DuplicateKey => "DuplicateKey"
        OutOfRange => "OutOfRange"
        _ => "other"
    }
}

fun main() {
    var input = Input { r: stdin() }
    while let Some(text) = input.next() {
        match yaml.parse(text) {
            Ok(v) => {
                let j = json.to_string(yaml.to_json(v))
                let back = match yaml.parse(yaml.to_string(v)) {
                    Ok(w) => json.to_string(yaml.to_json(w)) == j
                    Err(_) => false
                }
                println(if back { "ok = " + j } else { "ok ! " + j })
            }
            Err(e) => println(format("err {} {} {}", e.line, e.col, kind_name(e)))
        }
    }
}
"""

# the error kinds that name a feature the subset leaves out
_FEATURE_KINDS = {
    "alias": "Alias", "anchor": "Anchor", "tag": "Tag", "directive": "Directive",
    "documents": "MultipleDocuments", "complex key": "ComplexKey", "explicit key": "ExplicitKey",
}


def _build_checked(path: str, out: str) -> list[str]:
    """The driver at `path` built `--checked` at `out`, as its argv."""
    subprocess.run([selfhost_tool("main"), "build", path, "-o", out, "--stdlib", STDLIB_ROOT, "--checked"],
                   capture_output=True, check=True)
    return [out]


def _suite_dir() -> str | None:
    """The data release's directory, cloned once if need be; None without one."""
    given = os.environ.get("MYLA_YAML_TEST_SUITE")
    if given:
        return given if os.path.isdir(given) else None
    path = os.path.join(_REPO, "build", "yaml-test-suite")
    if not os.path.isdir(os.path.join(path, "229Q")):
        try:
            subprocess.run(["git", "clone", "--quiet", "--depth", "1", "--branch", _TAG, _URL, path],
                           capture_output=True, timeout=300, check=True,
                           env={**os.environ, "GIT_LFS_SKIP_SMUDGE": "1", "GIT_TERMINAL_PROMPT": "0"})
        except (OSError, subprocess.SubprocessError):
            return None
    return path if os.path.isdir(os.path.join(path, "229Q")) else None


def _cases(root: str) -> list[tuple[str, str]]:
    """(id, directory) of every case, `ID` or `ID/NN` for a case with several."""
    found = []
    for name in sorted(os.listdir(root)):
        d = os.path.join(root, name)
        if not re.fullmatch(r"[0-9A-Z]{4}", name) or not os.path.isdir(d):
            continue
        if os.path.exists(os.path.join(d, "in.yaml")):
            found.append((name, d))
        else:
            for sub in sorted(os.listdir(d)):
                if os.path.exists(os.path.join(d, sub, "in.yaml")):
                    found.append((f"{name}/{sub}", os.path.join(d, sub)))
    return found


# --- The core schema, as the YAML 1.2 specification gives it -------------------

def _resolve(text: str):
    if text in ("", "~", "null", "Null", "NULL"):
        return None
    if text in ("true", "True", "TRUE"):
        return True
    if text in ("false", "False", "FALSE"):
        return False
    if re.fullmatch(r"[-+]?[0-9]+", text):
        return _int(int(text), text)
    if re.fullmatch(r"0o[0-7]+", text):
        return _int(int(text[2:], 8), text)
    if re.fullmatch(r"0x[0-9a-fA-F]+", text):
        return _int(int(text[2:], 16), text)
    if re.fullmatch(r"[-+]?(\.[0-9]+|[0-9]+(\.[0-9]*)?)([eE][-+]?[0-9]+)?", text):
        return float(text)
    if re.fullmatch(r"[-+]?\.(inf|Inf|INF)", text):
        return -math.inf if text[0] == "-" else math.inf
    if re.fullmatch(r"\.(nan|NaN|NAN)", text):
        return math.nan
    return text


def _int(n: int, text: str):
    """An integer outside int64 is a float, as in std.json."""
    return n if -(2 ** 63) <= n < 2 ** 63 else float(n)


# --- The events -------------------------------------------------------------------

class _Scalar:
    def __init__(self, style: str, text: str) -> None:
        self.style, self.text = style, text


_ESCAPES = {"\\": "\\", "b": "\b", "n": "\n", "r": "\r", "t": "\t", "0": "\0"}


def _unescape(s: str) -> str:
    return re.sub(r"\\(.)", lambda m: _ESCAPES.get(m.group(1), m.group(1)), s)


def _expected(events: list[str]) -> tuple[set[str], str]:
    """The features a valid case uses that the subset leaves out, and the
    JSON text of its value ("" if it has a feature, "duplicate" if a mapping
    repeats a key)."""
    features: set[str] = set()
    docs = sum(1 for e in events if e.startswith("+DOC"))
    if docs > 1:
        features.add("documents")
    stack: list = [[]]
    for line in events:
        parts = line.split(" ")
        head = parts[0]
        props = parts[1:]
        if head == "=ALI":
            features.add("alias")
            stack[-1].append(_Scalar(":", ""))
            continue
        if head in ("+MAP", "+SEQ", "=VAL"):
            rest = line[len(head) + 1:] if len(line) > len(head) else ""
            while rest.startswith(("&", "<", "{}", "[]")):
                word, _, rest = rest.partition(" ")
                if word.startswith("&"):
                    features.add("anchor")
                elif word.startswith("<"):
                    features.add("tag")
            if head == "=VAL":
                stack[-1].append(_Scalar(rest[:1], _unescape(rest[1:])))
            else:
                stack.append([])
                stack[-1].append(head)
        elif head in ("-MAP", "-SEQ"):
            items = stack.pop()
            stack[-1].append((items[0], items[1:]))
    if features:
        return features, ""
    top = stack[0]
    if not top:
        return features, "null"
    duplicate = []

    def dump(node) -> str:
        if isinstance(node, _Scalar):
            v = _resolve(node.text) if node.style == ":" else node.text
            if isinstance(v, float) and not math.isfinite(v):
                return "null"                   # as std.json writes NaN and the infinities
            return json.dumps(v, ensure_ascii=False, separators=(",", ":"))
        kind, items = node
        if kind == "+SEQ":
            return "[" + ",".join(dump(x) for x in items) + "]"
        keys = items[0::2]
        if any(not isinstance(k, _Scalar) for k in keys):
            features.add("complex key")
            return ""
        texts = [k.text for k in keys]
        if len(set(texts)) != len(texts):
            duplicate.append(True)
        return "{" + ",".join(json.dumps(k.text, ensure_ascii=False) + ":" + dump(v)
                              for k, v in zip(keys, items[1::2])) + "}"

    text = dump(top[0])
    if features:
        return features, ""
    return features, "duplicate" if duplicate else text


def _directive(text: str) -> bool:
    for line in text.split("\n"):
        if line.startswith("%"):
            return True
        if line.startswith("---"):
            return False
    return False


def _framed(texts: list[bytes]) -> bytes:
    out = bytearray()
    for t in texts:
        out += str(len(t)).encode() + b"\n" + t
    return bytes(out)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class YamlTestSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        suite = _suite_dir()
        if suite is None:
            raise unittest.SkipTest("the YAML test suite's data isn't available (set MYLA_YAML_TEST_SUITE)")
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
        cls.checked = _build_checked(path, os.path.join(cls.tmp.name, "checked"))
        cls.interpreter = [selfhost_tool("interp_main"), path, STDLIB_ROOT]
        cls.cases = []
        for cid, d in _cases(suite):
            with open(os.path.join(d, "in.yaml"), "rb") as fh:
                text = fh.read()
            with open(os.path.join(d, "test.event"), encoding="utf-8") as fh:
                events = fh.read().split("\n")
            invalid = os.path.exists(os.path.join(d, "error"))
            features, expected = (set(), "") if invalid else _expected(events)
            if not invalid and _directive(text.decode("utf-8", "replace")):
                features.add("directive")
            if re.search(rb"(^|[ \t\[{,])\?([ \t\r\n]|$)", text, re.M):
                features.add("explicit key?")      # the events don't show it: a guess
            cls.cases.append((cid, text, invalid, features, expected))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def run_driver(self, argv: list[str], texts: list[bytes]) -> list[str]:
        proc = subprocess.run(argv, input=_framed(texts), capture_output=True, timeout=600)
        self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
        lines = proc.stdout.decode("utf-8", "surrogateescape").split("\n")[:-1]
        self.assertEqual(len(lines), len(texts))
        return lines

    def test_suite(self) -> None:
        got = self.run_driver(self.native, [c[1] for c in self.cases])
        counts = {k: 0 for k in ("same value", "duplicate refused", "explicit key refused",
                                 "feature named", "invalid refused")}
        wrong = []
        for (cid, text, invalid, features, expected), line in zip(self.cases, got):
            kind = line.split(" ")[3] if line.startswith("err") else ""
            hard = features - {"explicit key?"}
            if invalid:
                if line.startswith("err"):
                    counts["invalid refused"] += 1
                else:
                    wrong.append(f"{cid}: not YAML, read as {line[5:200]}")
            elif hard:
                allowed = {_FEATURE_KINDS[f] for f in hard}
                if "explicit key?" in features:
                    allowed.add("ExplicitKey")
                if kind in allowed:
                    counts["feature named"] += 1
                else:
                    wrong.append(f"{cid}: uses {sorted(hard)}, got {line[:200]}")
            elif expected == "duplicate":
                if kind == "DuplicateKey":
                    counts["duplicate refused"] += 1
                else:
                    wrong.append(f"{cid}: repeats a key, got {line[:200]}")
            elif kind == "ExplicitKey" and "explicit key?" in features:
                counts["explicit key refused"] += 1
            elif line == "ok = " + expected:
                counts["same value"] += 1
            elif line == "ok ! " + expected:
                wrong.append(f"{cid}: read right, but written it reads back differently")
            else:
                wrong.append(f"{cid}: {text[:120]!r}\n  expected {expected[:200]}\n  got      {line[:200]}")
        print(f"\nYAML test suite: {len(self.cases)} cases: " +
              ", ".join(f"{v} {k}" for k, v in counts.items()) + f", {len(wrong)} wrong", file=sys.stderr)
        self.assertEqual(wrong, [], f"{len(wrong)} of {len(self.cases)} cases")
        self.assertGreater(counts["same value"], 150)

    def test_broken_texts(self) -> None:
        """The suite's texts with a character deleted, inserted or doubled,
        or cut short: each is read or refused (no crash), and what is read
        is written back the same."""
        rng = random.Random(1)
        noise = [b" ", b"\t", b"\n", b"\r\n", b"-", b":", b"#", b"'", b'"', b"\\", b"[", b"]", b"{", b"}",
                 b",", b"|", b">", b"?", b"&", b"*", b"!", b"%", b"0", b"x", b"\xc3\xa9"]
        texts = []
        sources = [c[1] for c in self.cases if c[1]]
        for _ in range(4000):
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
            texts.append(t)
        lines = self.run_driver(self.native, texts)
        self.assertEqual(self.run_driver(self.checked, texts), lines, "the plain and the checked build differ")
        bad = [f"{t!r}: {line[:200]}" for t, line in zip(texts, lines) if line.startswith("ok !")]
        self.assertEqual(bad[:5], [], f"{len(bad)} of {len(texts)} don't read back as written")
        read = sum(1 for line in lines if line.startswith("ok"))
        print(f"\nbroken texts: {read} of {len(texts)} read, the rest refused", file=sys.stderr)

    def test_interpreter(self) -> None:
        sample = [c for c in self.cases if not c[2] and not c[3] and c[4] not in ("", "duplicate")][:25]
        texts = [c[1] for c in sample]
        self.assertEqual(self.run_driver(self.interpreter, texts), self.run_driver(self.native, texts))


WRITER = """from std.io import stdin, println, Reader
import std.yaml as yaml
from std.yaml import Yaml
from std.num import parse_int

struct Input { r: Reader }

impl Input {
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

fun main() {
    var input = Input { r: stdin() }
    while let Some(s) = input.next() {
        let out = yaml.to_string(Yaml.Map([("item", Yaml.List([Yaml.Str(s)])), ("key", Yaml.Map([(s, Yaml.Null)]))]))
        println(f"{out.len()}")
        print(out)                              // and a line break
    }
}
"""

def _numbers(seed: int, count: int) -> list[str]:
    """Integers in bases 10, 8 and 16 around int64's limits and past them,
    signed and with leading zeros, and a few random ones of any length."""
    rng = random.Random(seed)
    values = [0, 1, 2**31 - 1, 2**31, 2**32, 2**53 + 1, 2**63 - 2, 2**63 - 1, 2**63, 2**63 + 1, 2**64 - 1,
              2**64, 2**64 + 1, 2**65, 10**19, 10**20, 10**30]
    out = []
    for v in values + [rng.randrange(2 ** rng.randrange(1, 90)) for _ in range(count)]:
        out += [str(v), "-" + str(v), "+" + str(v), "00" + str(v), f"0x{v:x}", f"0x{v:X}", f"0x000{v:x}",
                f"0o{v:o}", f"0o00{v:o}"]
    return out


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class YamlNumbers(unittest.TestCase):
    """A plain integer scalar is an `Int` within int64; outside it a decimal
    one is a `Float`, as in `std.json`, and one in base 8 or 16 is
    `OutOfRange` (D184): built plain and checked, the driver gives the same."""

    def test_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "main.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(DRIVER)
            plain = os.path.join(tmp, "plain")
            subprocess.run([selfhost_tool("main"), "build", path, "-o", plain, "--stdlib", STDLIB_ROOT],
                           capture_output=True, check=True)
            checked = _build_checked(path, os.path.join(tmp, "checked"))
            numbers = _numbers(7, 200)
            texts = [f"v: {n}\n".encode() for n in numbers]
            answers = []
            for argv in ([plain], checked):
                proc = subprocess.run(argv, input=_framed(texts), capture_output=True, timeout=600)
                self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
                answers.append(proc.stdout.decode().split("\n")[:-1])
        self.assertEqual(answers[0], answers[1], "the plain and the checked build differ")
        wrong = []
        for n, got in zip(numbers, answers[0]):
            radix = n[:2] in ("0x", "0o")
            v = int(n[2:], 16 if n[1] == "x" else 8) if radix else int(n)
            if -2**63 <= v < 2**63:
                ok = got == "ok = " + json.dumps({"v": v}, separators=(",", ":"))
            elif radix:
                ok = got == "err 1 4 OutOfRange"
            else:
                ok = got.startswith("ok = ") and json.loads(got[5:])["v"] == float(v)
            if not ok:
                wrong.append(f"{n}: {got}")
        self.assertEqual(len(answers[0]), len(numbers))
        self.assertEqual(wrong[:5], [], f"{len(wrong)} of {len(numbers)}")


# the pieces of YAML 1.1's implicit types: a string of a few of them is often
# one of its numbers, booleans or timestamps
_PIECES = ["0", "1", "7", "9", "12", "60", "_", ":", ".", "-", "+", "e", "E", "x", "b", "o", "T", "t",
           " ", "Z", "0b", "0x", "0o", "2001-12-14", "2001-1-4", "21:59:43", ".10", "-05:00", "y", "n",
           "yes", "No", "on", "OFF", "true", "null", "~", "<<", "=", ".inf", ".NaN", "a", "1_000"]


def _writer_strings(seed: int, count: int) -> list[str]:
    rng = random.Random(seed)
    seen, out = set(), []
    while len(out) < count:
        s = "".join(rng.choice(_PIECES) for _ in range(rng.randrange(1, 5)))
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class YamlWriterForYaml11(unittest.TestCase):
    def test_pyyaml_reads_strings(self) -> None:
        try:
            import yaml as pyyaml
        except ImportError:
            self.skipTest("PyYAML isn't installed")
        strings = _writer_strings(7, 6000)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "main.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(WRITER)
            asm = subprocess.run([selfhost_tool("gen_main"), path, STDLIB_ROOT], capture_output=True, text=True, check=True)
            native = os.path.join(tmp, "native")
            with open(native + ".s", "w", encoding="utf-8") as fh:
                fh.write(asm.stdout)
            subprocess.run(["as", "--64", "-o", native + ".o", native + ".s"], check=True)
            subprocess.run(["ld", "-o", native, native + ".o"], check=True)
            proc = subprocess.run([native], input=_framed([t.encode() for t in strings]), capture_output=True, timeout=600)
        self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
        out, docs = proc.stdout, []
        while out:
            head, _, out = out.partition(b"\n")
            n = int(head)
            docs.append(out[:n].decode("utf-8"))
            out = out[n + 1:]
        self.assertEqual(len(docs), len(strings))
        wrong = []
        for s, doc in zip(strings, docs):
            try:
                back = pyyaml.safe_load(doc)
            except Exception as err:                # PyYAML fails on some: `0x_`
                wrong.append(f"{s!r}: {doc!r} isn't read: {str(err)[:80]}")
                continue
            if back != {"item": [s], "key": {s: None}}:
                wrong.append(f"{s!r}: {doc!r} reads as {back!r}")
        quoted = sum(1 for doc in docs if doc.startswith('item:\n  - "'))
        print(f"\nwriter against PyYAML: {len(strings)} strings, {quoted} quoted, {len(wrong)} wrong", file=sys.stderr)
        self.assertEqual(wrong[:10], [], f"{len(wrong)} of {len(strings)}")


if __name__ == "__main__":
    unittest.main()
