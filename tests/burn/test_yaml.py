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
and a few cases run on the self-hosted interpreter too.

The suite is data, not code: the test only reads its files. It looks for the
data release in `$MYLA_YAML_TEST_SUITE`, else clones its `data-2022-01-17`
tag into `build/yaml-test-suite` once, and is skipped when neither works.
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
        bad = [f"{t!r}: {line[:200]}" for t, line in zip(texts, lines) if line.startswith("ok !")]
        self.assertEqual(bad[:5], [], f"{len(bad)} of {len(texts)} don't read back as written")
        read = sum(1 for line in lines if line.startswith("ok"))
        print(f"\nbroken texts: {read} of {len(texts)} read, the rest refused", file=sys.stderr)

    def test_interpreter(self) -> None:
        sample = [c for c in self.cases if not c[2] and not c[3] and c[4] not in ("", "duplicate")][:25]
        texts = [c[1] for c in sample]
        self.assertEqual(self.run_driver(self.interpreter, texts), self.run_driver(self.native, texts))


if __name__ == "__main__":
    unittest.main()
