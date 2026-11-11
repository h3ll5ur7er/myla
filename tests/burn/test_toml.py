"""Burn tests: `std.toml` (MYLA-89, MYLA-402, MYLA-407) against Python's
`tomllib` and the toml-test suite.

The driver (`DRIVER`) reads length-framed documents from stdin and prints,
for each, `ok <value as toml-test's tagged JSON>\\t<what std.toml writes>` or
`err <line> <col> <message>`. Python generates TOML 1.0 documents from a seed
(tables, dotted and quoted headers, arrays of tables, dotted keys, bare,
quoted and literal keys, basic, literal and multi-line strings with escapes
and non-ASCII characters, integers in four bases with `_` and signs, int64
limits, floats with exponents, `inf` and `nan`, offset and local date-times,
dates and times, booleans, arrays of any values over several lines with
comments and trailing commas, nested inline tables with dotted keys,
comments, CRLF, random spacing), and broken ones by deleting, inserting or
duplicating a character or cutting the text short. For each:

- when `tomllib` rejects it, `std.toml` must reject it too;
- when `tomllib` accepts it, `std.toml` must give the same value, keys in
  order, or reject an integer beyond int64 ("integer out of range", as TOML
  asks of a parser that can't hold it); generated documents that `tomllib`
  accepts must be accepted (a few repeat a key or a table by chance, and
  both reject those).

The writer (MYLA-402): every document `std.toml` reads, it writes with
`to_string`; the driver checks that `parse` reads that back as the same value,
and `tomllib` must read it as the original's value, keys in order. Random
values (arrays of tables, arrays of any values, floats, dates) are written and
read by `tomllib` too.

The toml-test suite (https://github.com/toml-lang/toml-test): its TOML 1.0
files are vendored in `tests/burn/data/toml_test_1.0.json` (MIT, the commit
named there; `python3 -m tests.burn.test_toml --vendor <checkout>` makes the
file again). Every valid file must read as its JSON says and be written back,
every invalid one be refused. MYLA_TOML_TEST naming a checkout runs that one
instead.

The big corpus runs on the self-hosted native build, a small one in the
self-hosted interpreter. With MYLA_TEST_TARGET set (`scripts/test-target.py`)
the drivers are built for that target and run under qemu-aarch64 or Node,
so the toml-test suite runs on every runner (MYLA-424).
"""
from __future__ import annotations

import datetime
import json
import math
import os
import random
import re
import subprocess
import sys
import tempfile
import tomllib
import unittest

from ._native import CAN_BUILD_NATIVE, SKIP_REASON, TEST_TARGET, check_file, native_build, run_argv
from ._tools import STDLIB_ROOT, selfhost_tool

VENDORED = os.path.join(os.path.dirname(__file__), "data", "toml_test_1.0.json")

DRIVER = """from std.io import stdin, println, Reader
from std.toml import parse, Toml, TomlError
import std.toml as toml
from std.json import Json, to_string
from std.num import parse_int

struct Input { r: Reader }

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

// A scalar as toml-test writes it: its type and its text.
fun tagged(kind: str, value: str) -> Json {
    return Json.Object([("type", Json.Str(kind)), ("value", Json.Str(value))])
}

fun to_json(t: Toml) -> Json {
    return match t {
        Toml.Str(s) => tagged("string", s)
        Toml.Int(n) => tagged("integer", f"{n}")
        Toml.Float(f) => tagged("float", toml.inline_string(t))
        Toml.Bool(b) => tagged("bool", toml.inline_string(t))
        Toml.DateTime(d) => match d.offset {
            Some(o) => tagged("datetime", toml.inline_string(t))
            None => tagged("datetime-local", toml.inline_string(t))
        }
        Toml.Date(d) => tagged("date-local", toml.inline_string(t))
        Toml.Time(x) => tagged("time-local", toml.inline_string(t))
        Toml.Array(items) => {
            var out: [Json] = []
            for x in items { out.push(to_json(x)) }
            Json.Array(out)
        }
        Toml.Table(members) => {
            var out: [(str, Json)] = []
            for m in members { out.push((m.0, to_json(m.1))) }
            Json.Object(out)
        }
    }
}

fun main() {
    var input = Input { r: stdin() }
    var more = true
    while more {
        match input.next() {
            Some(text) => {
                match parse(text) {
                    // the value, a tab, the text `std.toml` writes, if it
                    // reads back as the value (MYLA-402)
                    Ok(v) => {
                        let written = toml.to_string(v)
                        let back = match parse(written) {
                            Ok(w) => w == v,
                            Err(e) => false,
                        }
                        let tail = match back { true => "\\t", false => "\\tnot read back as itself: " }
                        println("ok " + to_string(to_json(v)) + tail + to_string(Json.Str(written)))
                    },
                    Err(e) => { println(f"err {e.line} {e.col} {e.msg}") },
                }
            },
            None => { more = false },
        }
    }
}
"""


def framed(texts: list[str | bytes]) -> bytes:
    out = bytearray()
    for t in texts:
        data = t.encode("utf-8") if isinstance(t, str) else t
        out += str(len(data)).encode() + b"\n" + data
    return bytes(out)


INT64_MIN, INT64_MAX = -(2 ** 63), 2 ** 63 - 1

# --- Values in toml-test's tagged form, normalised ---------------------------------

_SCALAR_TYPES = {"string", "integer", "float", "bool", "datetime", "datetime-local", "date-local", "time-local"}
_DATETIME = re.compile(r"^(\d{4}-\d{2}-\d{2})?[Tt ]?(\d{2}:\d{2}(?::\d{2})?)?(?:\.(\d+))?([Zz]|[+-]\d{2}:\d{2})?$")


def _tagged(value):
    """A value `tomllib` reads, in toml-test's tagged form, keys in order."""
    if isinstance(value, dict):
        return {k: _tagged(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_tagged(v) for v in value]
    if isinstance(value, bool):
        return {"type": "bool", "value": "true" if value else "false"}
    if isinstance(value, str):
        return {"type": "string", "value": value}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": repr(value)}
    if isinstance(value, datetime.datetime):
        return {"type": "datetime" if value.tzinfo else "datetime-local", "value": value.isoformat()}
    if isinstance(value, datetime.date):
        return {"type": "date-local", "value": value.isoformat()}
    if isinstance(value, datetime.time):
        return {"type": "time-local", "value": value.isoformat()}
    raise TypeError(value)


def _norm_scalar(kind: str, text: str):
    if kind == "integer":
        return kind, int(text)
    if kind == "float":
        f = float(text)
        return kind, "nan" if math.isnan(f) else repr(f)
    if kind in ("datetime", "datetime-local", "date-local", "time-local"):
        m = _DATETIME.match(text)
        if not m:
            return kind, text
        date, time, frac, offset = m.groups()
        if time and len(time) == 5:
            time += ":00"
        frac = (frac or "")[:6].rstrip("0")       # tomllib keeps microseconds
        if offset in ("Z", "z", "-00:00"):
            offset = "+00:00"
        return kind, (date, time, frac, offset)
    return kind, text


def _norm(value, ordered: bool = True):
    """A tagged value in a form that compares as TOML's values do: tables as
    lists of pairs (sorted unless `ordered`), scalars by their meaning."""
    if isinstance(value, dict):
        if set(value) == {"type", "value"} and value["type"] in _SCALAR_TYPES and isinstance(value["value"], str):
            return _norm_scalar(value["type"], value["value"])
        pairs = [(k, _norm(v, ordered)) for k, v in value.items()]
        return pairs if ordered else sorted(pairs, key=lambda p: p[0])
    if isinstance(value, list):
        return [_norm(v, ordered) for v in value]
    return value


def _fits_int64(value) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, list, dict)):
        return True
    if isinstance(value, int):
        return INT64_MIN <= value <= INT64_MAX
    items = value.values() if isinstance(value, dict) else value
    return all(_fits_int64(v) for v in items)


def _verdict(text: str) -> tuple[str, object]:
    """("err", None) when tomllib rejects `text`; ("outside", None) when it
    reads an integer beyond int64; else ("ok", the value, normalised)."""
    try:
        value = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return "err", None
    if not _fits_int64(value):
        return "outside", None
    return "ok", _norm(_tagged(value))


def _out_of_range(line: str) -> bool:
    return line.startswith("err ") and "integer out of range" in line


def _written_ok(expected, written: str) -> bool:
    """Whether `written`, the driver's JSON string of what `std.toml` wrote
    (MYLA-402), is TOML that `tomllib` reads as `expected` (normalised, keys
    in order); the driver checked that `std.toml` reads it back as the same
    value."""
    if written.startswith("not read back"):
        return False
    try:
        return _norm(_tagged(tomllib.loads(json.loads(written)))) == expected
    except tomllib.TOMLDecodeError:
        return False


# --- Random documents ---------------------------------------------------------------

_CHARS = ["a", "z", "Q", " ", "\t", '"', "'", "\\", "#", "=", "[", "]", "{", "}", ",", ".",
          "\n", "\r", "\b", "\f", "\x00", "\x1f", "\x7f", "é", "λ", "€", "😀", "𝄞", " "]


def _string_value(rng: random.Random) -> str:
    return "".join(rng.choice(_CHARS) for _ in range(rng.randrange(0, 8)))


def _quote(rng: random.Random, s: str) -> str:
    """`s` as a basic or (when it can be) a literal string."""
    literal_ok = "'" not in s and all(c == "\t" or (ord(c) >= 32 and c != "\x7f") for c in s)
    if literal_ok and rng.random() < 0.3:
        return "'" + s + "'"
    out = []
    for c in s:
        if c == '"':
            out.append('\\"')
        elif c == "\\":
            out.append("\\\\")
        elif c in "\b\t\n\f\r" and rng.random() < 0.8:
            out.append({"\b": "\\b", "\t": "\\t", "\n": "\\n", "\f": "\\f", "\r": "\\r"}[c])
        elif c == "\t":
            out.append("\t")
        elif ord(c) < 32 or c == "\x7f":
            out.append(f"\\u{ord(c):04x}" if rng.random() < 0.5 else f"\\U{ord(c):08X}")
        elif ord(c) > 127 and rng.random() < 0.3:
            out.append(f"\\u{ord(c):04X}" if ord(c) < 0x10000 else f"\\U{ord(c):08x}")
        else:
            out.append(c)
    return '"' + "".join(out) + '"'


def _multi_line(rng: random.Random) -> str:
    """A multi-line basic or literal string: line breaks, quotes beside the
    closing ones, a backslash at a line's end."""
    s = _string_value(rng).replace("\r", "")
    if rng.random() < 0.5 and "'''" not in s and all(c in "\t\n" or (ord(c) >= 32 and c != "\x7f") for c in s):
        return "'''" + rng.choice(["", "\n"]) + s + rng.choice(["", "'", "''"]) + "'''"
    body = _quote(rng, s)[1:-1].replace('"""', '""\\"')
    if body.endswith('"') and not body.endswith('\\"'):
        body = body[:-1] + '\\"'
    parts = [body, rng.choice(["", "\n", "\\\n   ", "\\  \n\n  ", '"', '""'])]
    return '"""' + rng.choice(["", "\n"]) + "".join(parts) + '"""'


def _key(rng: random.Random) -> str:
    """A key as written: bare, or quoted with characters a bare key can't hold."""
    r = rng.random()
    if r < 0.7:
        return "".join(rng.choice("abcxyz019_-") for _ in range(rng.randrange(1, 5)))
    return _quote(rng, _string_value(rng) if r < 0.9 else rng.choice(["a", "b", "x"]))


def _dotted_key(rng: random.Random) -> str:
    parts = [_key(rng) for _ in range(rng.choice([1, 1, 1, 2, 3]))]
    return (_ws(rng) + "." + _ws(rng)).join(parts)


def _underscored(digits: str, rng: random.Random) -> str:
    if len(digits) > 3 and rng.random() < 0.3:
        groups = []
        while digits:
            groups.insert(0, digits[-3:])
            digits = digits[:-3]
        return "_".join(groups)
    return digits


def _integer(rng: random.Random) -> str:
    n = rng.choice([0, 1, -1, 7, 42, -300, INT64_MIN, INT64_MAX, rng.randrange(INT64_MIN, INT64_MAX),
                    rng.randrange(-10 ** 6, 10 ** 6)])
    base = rng.choice([10, 10, 10, 10, 16, 8, 2])
    if base != 10:
        m = abs(n)
        digits = {16: f"{m:x}", 8: f"{m:o}", 2: f"{m:b}"}[base]
        if base == 16 and rng.random() < 0.5:
            digits = digits.upper()
        return {16: "0x", 8: "0o", 2: "0b"}[base] + _underscored(digits, rng)
    sign = "-" if n < 0 else ("+" if rng.random() < 0.1 else "")
    return sign + _underscored(str(abs(n)), rng)


def _float(rng: random.Random) -> str:
    r = rng.random()
    if r < 0.15:
        return rng.choice(["", "+", "-"]) + rng.choice(["inf", "nan"])
    if r < 0.3:
        return rng.choice(["0.0", "-0.0", "+0.0", "1e0", "1E+2", "5e-324", "1.7976931348623157e308", "1e400", "-1e-400"])
    whole = str(rng.randrange(0, 10 ** rng.randrange(1, 8)))
    text = ("-" if rng.random() < 0.3 else "") + _underscored(whole, rng)
    if rng.random() < 0.7:
        text += "." + _underscored(str(rng.randrange(0, 10 ** rng.randrange(1, 10))).zfill(rng.randrange(1, 4)), rng)
        if rng.random() < 0.3:
            text += rng.choice("eE") + rng.choice(["", "+", "-"]) + str(rng.randrange(0, 40)).zfill(rng.randrange(1, 3))
    else:
        text += rng.choice("eE") + rng.choice(["", "+", "-"]) + str(rng.randrange(0, 300))
    return text


def _date(rng: random.Random) -> str:
    y = rng.choice([1, 1979, 2000, 2024, 9999, rng.randrange(1, 10000)])
    m = rng.randrange(1, 13)
    d = rng.randrange(1, 32 if m in (1, 3, 5, 7, 8, 10, 12) else (29 if m == 2 else 31))
    if m == 2 and y % 4 == 0 and (y % 100 != 0 or y % 400 == 0) and rng.random() < 0.3:
        d = 29
    return f"{y:04}-{m:02}-{d:02}"


def _time(rng: random.Random) -> str:
    text = f"{rng.randrange(24):02}:{rng.randrange(60):02}:{rng.randrange(60):02}"
    if rng.random() < 0.4:
        text += "." + "".join(rng.choice("0123456789") for _ in range(rng.randrange(1, 12)))
    return text


def _datetime(rng: random.Random) -> str:
    r = rng.random()
    if r < 0.2:
        return _date(rng)
    if r < 0.35:
        return _time(rng)
    text = _date(rng) + rng.choice(["T", "T", "t", " "]) + _time(rng)
    if rng.random() < 0.6:
        text += rng.choice(["Z", "z", f"+{rng.randrange(24):02}:{rng.randrange(60):02}",
                            f"-{rng.randrange(24):02}:{rng.randrange(60):02}", "+00:00", "-00:00"])
    return text


def _ws(rng: random.Random) -> str:
    return rng.choice(["", " ", " ", "  ", "\t"])


def _array(rng: random.Random, depth: int) -> str:
    items = [_value(rng, depth + 1) for _ in range(rng.randrange(0, 4))]
    if rng.random() < 0.5:
        sep = "," + rng.choice([" ", "\n  ", " # note\n  ", "\n\n"])
        trailing = "," if items and rng.random() < 0.4 else ""
        return "[" + rng.choice(["", "\n  "]) + sep.join(items) + trailing + rng.choice(["", "\n"]) + "]"
    return "[" + _ws(rng) + ", ".join(items) + _ws(rng) + "]"


def _value(rng: random.Random, depth: int) -> str:
    kinds = ["str", "str", "int", "float", "date", "bool", "ml"] + (["array", "array", "inline"] if depth < 3 else [])
    kind = rng.choice(kinds)
    if kind == "str":
        return _quote(rng, _string_value(rng))
    if kind == "ml":
        return _multi_line(rng)
    if kind == "int":
        return _integer(rng)
    if kind == "float":
        return _float(rng)
    if kind == "date":
        return _datetime(rng)
    if kind == "bool":
        return rng.choice(["true", "false"])
    if kind == "array":
        return _array(rng, depth)
    keys = []
    pairs = []
    for _ in range(rng.randrange(0, 4)):
        k = _dotted_key(rng)
        if k not in keys:
            keys.append(k)
            pairs.append(f"{k}{_ws(rng)}={_ws(rng)}{_value(rng, depth + 1)}")
    return "{" + _ws(rng) + ", ".join(pairs) + _ws(rng) + "}"


def _key_values(rng: random.Random, lines: list[str]) -> None:
    used: set[str] = set()
    for _ in range(rng.randrange(0, 4)):
        k = _dotted_key(rng) if rng.random() < 0.7 else _key(rng)
        if k in used:
            continue
        used.add(k)
        comment = rng.choice(["", "", " # comment", "\t#λ"])
        lines.append(f"{_ws(rng)}{k}{_ws(rng)}={_ws(rng)}{_value(rng, 0)}{_ws(rng)}{comment}")


def _document(rng: random.Random) -> str:
    lines: list[str] = []
    if rng.random() < 0.3:
        lines.append("# a document")
    _key_values(rng, lines)
    for _ in range(rng.randrange(0, 4)):
        path = [_key(rng) for _ in range(rng.randrange(1, 4))]
        lines.append("")
        double = rng.random() < 0.3
        lines.append(_ws(rng) + ("[[" if double else "[") + _ws(rng) + (_ws(rng) + "." + _ws(rng)).join(path) + _ws(rng)
                     + ("]]" if double else "]") + rng.choice(["", " # table"]))
        _key_values(rng, lines)
    newline = "\r\n" if rng.random() < 0.1 else "\n"
    return newline.join(lines) + rng.choice(["", newline])


def _valid_documents(seed: int, count: int) -> list[str]:
    rng = random.Random(seed)
    return [_document(rng) for _ in range(count)]


def _broken_documents(seed: int, count: int) -> list[str]:
    rng = random.Random(seed)
    noise = list("[]{}=,.\"'#\\ \t0123456789-_+:aetfnxuUoTZe") + ["\n", "\r", "é", "\x00", "\x7f", '"""', "'''"]
    texts = []
    while len(texts) < count:
        text = _document(rng)
        if not text:
            continue
        i = rng.randrange(len(text) + 1)
        how = rng.randrange(4)
        if how == 0 and i < len(text):
            text = text[:i] + text[i + 1:]
        elif how == 1:
            text = text[:i] + rng.choice(noise) + text[i:]
        elif how == 2 and i < len(text):
            text = text[:i] + text[i] + text[i:]
        else:
            text = text[:i]
        texts.append(text)
    return texts


# Writes TOML for any value (MYLA-402): reads length-framed JSON values and
# prints, for each, what `std.toml` writes, as a JSON string. A value that
# JSON hasn't (a float, a date, a time) comes as `{"$toml": "<its TOML>"}`.
WRITER_DRIVER = DRIVER.split("// A scalar as toml-test")[0].replace(
    "from std.json import Json, to_string", "from std.json import Json, to_string\nimport std.json as json") + """
fun to_toml(j: Json) -> Toml {
    return match j {
        Json.Str(s) => Toml.Str(s)
        Json.Int(n) => Toml.Int(n)
        Json.Bool(b) => Toml.Bool(b)
        Json.Array(items) => {
            var out: [Toml] = []
            for x in items { out.push(to_toml(x)) }
            Toml.Array(out)
        }
        Json.Object(members) => {
            if members.len() == 1 && members[0].0 == "$toml" {
                match members[0].1 {
                    Json.Str(text) => {
                        match parse("x = " + text) {
                            Ok(doc) => {
                                match toml.field(doc, "x") {
                                    Some(v) => { return v }
                                    None => {}
                                }
                            }
                            Err(e) => {}
                        }
                    }
                    _ => {}
                }
            }
            var out: [(str, Toml)] = []
            for m in members { out.push((m.0, to_toml(m.1))) }
            Toml.Table(out)
        }
        _ => Toml.Str("not a TOML value")
    }
}

fun main() {
    var input = Input { r: stdin() }
    while let Some(text) = input.next() {
        match json.parse(text) {
            Ok(j) => { println(to_string(Json.Str(toml.to_string(to_toml(j))))) },
            Err(e) => { println("err") },
        }
    }
}
"""


def _any_value(rng: random.Random, depth: int):
    """A value of any kind `std.toml`'s type holds, as JSON for the writer's
    driver and as Python's value: arrays of any values and arrays of tables
    too."""
    kinds = ["str", "int", "bool", "float", "date"] + (["array", "tables", "table", "table"] if depth < 3 else [])
    kind = rng.choice(kinds)
    if kind == "str":
        s = _string_value(rng)
        return s, s
    if kind == "int":
        n = rng.choice([0, -1, INT64_MIN, INT64_MAX, rng.randrange(INT64_MIN, INT64_MAX)])
        return n, n
    if kind == "bool":
        b = rng.random() < 0.5
        return b, b
    if kind in ("float", "date"):
        text = _float(rng) if kind == "float" else _datetime(rng)
        return {"$toml": text}, tomllib.loads("x = " + text)["x"]
    if kind == "array":
        pairs = [_any_value(rng, depth + 1) for _ in range(rng.randrange(0, 4))]
        return [p[0] for p in pairs], [p[1] for p in pairs]
    if kind == "tables":
        pairs = [_any_table(rng, depth + 1) for _ in range(rng.randrange(1, 3))]
        return [p[0] for p in pairs], [p[1] for p in pairs]
    return _any_table(rng, depth + 1)


def _any_table(rng: random.Random, depth: int) -> tuple[dict, dict]:
    """A table of such values, tables and key/value pairs in any order."""
    out_json, out_py = {}, {}
    for _ in range(rng.randrange(0, 5)):
        r = rng.random()
        key = (_string_value(rng) if r < 0.2 else
               "".join(rng.choice("abxyz_-19") for _ in range(rng.randrange(1, 4))))
        if key == "$toml":
            continue
        out_json[key], out_py[key] = _any_value(rng, depth)
    return out_json, out_py


def vendor(checkout: str, out: str = VENDORED) -> None:
    """Writes the TOML 1.0 files of a toml-test checkout to `out`: each valid
    file's text and JSON, each invalid file's text (bytes that aren't UTF-8 as
    surrogate escapes)."""
    root = os.path.join(checkout, "tests")
    commit = subprocess.run(["git", "-C", checkout, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    with open(os.path.join(root, "files-toml-1.0.0"), encoding="utf-8") as fh:
        names = [n for n in fh.read().split() if n.endswith(".toml")]
    data = {"source": "https://github.com/toml-lang/toml-test", "commit": commit, "license": "MIT",
            "valid": {}, "invalid": {}}
    for name in names:
        with open(os.path.join(root, name), "rb") as fh:
            text = fh.read().decode("utf-8", "surrogateescape")
        if name.startswith("valid/"):
            with open(os.path.join(root, name[:-5] + ".json"), encoding="utf-8") as fh:
                data["valid"][name] = {"toml": text, "json": json.load(fh)}
        else:
            data["invalid"][name] = text
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=True, indent=0, sort_keys=True)
        fh.write("\n")


def _suite() -> tuple[dict[str, tuple[bytes, object]], dict[str, bytes]]:
    """The toml-test files: valid ones' bytes and expected values, invalid
    ones' bytes, from MYLA_TOML_TEST's checkout or the vendored copy."""
    checkout = os.environ.get("MYLA_TOML_TEST")
    if checkout:
        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        tmp.close()
        vendor(checkout, tmp.name)
        path = tmp.name
    else:
        path = VENDORED
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if checkout:
        os.unlink(path)
    valid = {n: (v["toml"].encode("utf-8", "surrogateescape"), v["json"]) for n, v in data["valid"].items()}
    invalid = {n: t.encode("utf-8", "surrogateescape") for n, t in data["invalid"].items()}
    return valid, invalid


def _build(gen: str, source: str, out: str) -> list[str]:
    """`source` built for the machine, or for MYLA_TEST_TARGET by the CLI;
    the command that runs it."""
    if TEST_TARGET:
        native_build(check_file(source), out)
        return run_argv(out)[0]
    asm = subprocess.run([gen, source, STDLIB_ROOT], capture_output=True, text=True, check=True)
    with open(out + ".s", "w", encoding="utf-8") as fh:
        fh.write(asm.stdout)
    subprocess.run(["as", "--64", "-o", out + ".o", out + ".s"], check=True)
    subprocess.run(["ld", "-o", out, out + ".o"], check=True)
    return [out]


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TomlAgainstPython(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        gen = selfhost_tool("gen_main")
        path = os.path.join(cls.tmp.name, "main.my")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(DRIVER)
        sh_native = os.path.join(cls.tmp.name, "sh_native")
        cls.native = {"self-hosted native": _build(gen, path, sh_native)}
        writer = os.path.join(cls.tmp.name, "writer.my")
        with open(writer, "w", encoding="utf-8") as fh:
            fh.write(WRITER_DRIVER)
        cls.writer = _build(gen, writer, os.path.join(cls.tmp.name, "writer"))
        cls.interpreters = {
            "self-hosted interpreter": [selfhost_tool("interp_main"), path, STDLIB_ROOT],
        }

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def run_driver(self, argv: list[str], texts: list[str | bytes]) -> list[str]:
        proc = subprocess.run(argv, input=framed(texts), capture_output=True, timeout=600)
        self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
        lines = proc.stdout.decode("utf-8", "replace").split("\n")[:-1]
        self.assertEqual(len(lines), len(texts))
        return lines

    def check(self, implementations: dict[str, list[str]], texts: list[str]) -> dict[str, int]:
        """Run `texts` through each implementation and compare with tomllib;
        the number of documents of each verdict."""
        verdicts = [_verdict(t) for t in texts]
        counts: dict[str, int] = {}
        for kind, _ in verdicts:
            counts[kind] = counts.get(kind, 0) + 1
        for impl, argv in implementations.items():
            with self.subTest(implementation=impl):
                lines = self.run_driver(argv, texts)
                wrong = []
                for text, (kind, expected), got in zip(texts, verdicts, lines):
                    if kind == "err":
                        ok = got.startswith("err ")
                    elif kind == "outside":
                        ok = _out_of_range(got)
                    else:
                        ok = False
                        if got.startswith("ok "):
                            value, _, written = got[3:].partition("\t")
                            ok = _norm(json.loads(value)) == expected and _written_ok(expected, written)
                    if not ok:
                        wrong.append(f"{text!r}\n  tomllib: {kind} {str(expected)[:300]!r}\n  myla:    {got[:300]!r}")
                self.assertEqual(wrong[:5], [], f"{len(wrong)} of {len(texts)} differ")
        return counts

    def test_documents(self) -> None:
        # some repeat a key or a table by chance, which both must reject
        counts = self.check(self.native, _valid_documents(1, 3000))
        self.assertGreater(counts.get("ok", 0), 2000, counts)

    def test_broken_documents(self) -> None:
        counts = self.check(self.native, _broken_documents(2, 4000))
        # most break, many survive as valid TOML (a key or a string changed)
        self.assertGreater(counts.get("err", 0), 1500, counts)
        self.assertGreater(counts.get("ok", 0), 500, counts)

    def test_writer(self) -> None:
        # MYLA-402: what `std.toml` writes for any value of its type, arrays
        # of tables and of other values included, is TOML that tomllib reads
        # as that value, keys in order
        rng = random.Random(5)
        values = [_any_table(rng, 0) for _ in range(2000)]
        lines = self.run_driver(self.writer, [json.dumps(v[0], ensure_ascii=False) for v in values])
        wrong = []
        headers = 0
        for (_, value), line in zip(values, lines):
            text = json.loads(line)
            headers += text.count("[[")
            try:
                ok = _norm(_tagged(tomllib.loads(text))) == _norm(_tagged(value))
            except tomllib.TOMLDecodeError as e:
                ok = False
                text += f"  ({e})"
            if not ok:
                wrong.append(f"{value!r}\n  written: {text!r}")
        self.assertEqual(wrong[:5], [], f"{len(wrong)} of {len(values)} differ")
        self.assertGreater(headers, 200)            # arrays of tables were written

    def test_toml_test_suite(self) -> None:
        # MYLA-407: every valid TOML 1.0 file of toml-test reads as its JSON
        # says and is written back, every invalid one is refused
        # (2026-11-09: 208 of 208 valid, 509 of 509 invalid)
        valid, invalid = _suite()
        names = sorted(valid)
        lines = self.run_driver(self.native["self-hosted native"], [valid[n][0] for n in names])
        wrong = []
        for name, got in zip(names, lines):
            expected = _norm(valid[name][1], ordered=False)
            ok = False
            if got.startswith("ok "):
                value, _, written = got[3:].partition("\t")
                ok = _norm(json.loads(value), ordered=False) == expected and not written.startswith("not read back")
                if ok:
                    try:
                        ok = _norm(_tagged(tomllib.loads(json.loads(written))), ordered=False) == expected
                    except tomllib.TOMLDecodeError:
                        ok = False
            if not ok:
                wrong.append(f"{name}: {got[:300]}")
        self.assertEqual(wrong, [], f"{len(wrong)} of {len(names)} valid files wrong")
        names = sorted(invalid)
        lines = self.run_driver(self.native["self-hosted native"], [invalid[n] for n in names])
        accepted = [f"{name}: {got[:200]}" for name, got in zip(names, lines) if not got.startswith("err ")]
        self.assertEqual(accepted, [], f"{len(accepted)} of {len(names)} invalid files accepted")
        self.assertGreater(len(valid), 200)
        self.assertGreater(len(invalid), 500)

    def test_interpreters(self) -> None:
        self.check(self.interpreters, _valid_documents(3, 20) + _broken_documents(4, 40))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--vendor":
        vendor(sys.argv[2])
    else:
        unittest.main()
