#!/usr/bin/env python3
"""to_methods.py: builtin functions called as methods (MYLA-221, D103).

    scripts/to_methods.py FILE...        # .my files, myla blocks of .md files,
                                         # Myla programs in .py string literals,
                                         # "source"/strings of .json test data

`f(a, rest...)`, with `f` one of the builtin functions that are methods
(`len`, `push`, `pop`, `contains`, `remove`, `keys`, `chars`, `append`,
`append_byte`, `build`), becomes `a.f(rest...)`; `a` keeps its text, in
parentheses unless it is a postfix chain. Calls after `.` (methods already)
or `fun` (declarations) stay, and so does anything inside strings and
comments: the self-hosted lexer (`selfhost/lex_main.my`, built on first use
into `build/to_methods-lex`, or `$LEX_MAIN`) says where code is. Nested calls
are rewritten too. The rewrite only reorders text: lines never move.

The recorded answers' aliases (MYLA-240) use `rewrite_mapped`, which also
says where each character went, to move the positions in an answer recorded
about the original program.
"""
from __future__ import annotations

import ast
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import tokenize

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILTINS = {"len", "push", "pop", "contains", "remove", "keys", "chars", "append", "append_byte", "build"}
_TOKEN = re.compile(r'^([A-Z_0-9]+) (\d+) (\d+) ".*" (?:\S+ )*end=(\d+):(\d+)$')
_lex = None


def lex_main() -> str:
    """The self-hosted lexer's canonical dump tool."""
    global _lex
    if _lex:
        return _lex
    _lex = os.environ.get("LEX_MAIN") or os.path.join(REPO, "build", "to_methods-lex")
    if not os.environ.get("LEX_MAIN") and not os.path.exists(_lex):
        subprocess.run([os.path.join(REPO, "build", "myla"), "build", os.path.join(REPO, "selfhost", "lex_main.my"),
                        "-o", _lex, "--stdlib", os.path.join(REPO, "lib")], check=True, capture_output=True)
    return _lex


def _tokens(text: str):
    with tempfile.NamedTemporaryFile("w", suffix=".my", delete=False, encoding="utf-8",
                                     errors="surrogateescape") as fh:
        fh.write(text)
        path = fh.name
    try:
        out = subprocess.run([lex_main(), path], capture_output=True, text=True, errors="surrogateescape").stdout
    finally:
        os.remove(path)
    toks = []
    for line in out.splitlines():
        m = _TOKEN.match(line)
        if m:
            toks.append((m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5))))
    return toks


def _offsets(text: str):
    starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            starts.append(i + 1)
    return lambda line, col: starts[line - 1] + col - 1


def _simple(toks) -> bool:
    depth = 0
    for kind, *_ in toks:
        if kind in ("LPAREN", "LBRACKET", "LBRACE"):
            depth += 1
        elif kind in ("RPAREN", "RBRACKET", "RBRACE"):
            depth -= 1
        elif depth == 0 and kind not in ("IDENT", "SELF", "DOT", "INT", "STRING", "CHAR", "FLOAT", "TRUE", "FALSE",
                                         "STR", "QUESTION"):
            return False
    return True


def _edits(text: str) -> list[tuple[int, int, int, int, int, int, str, int]]:
    """The outermost calls to rewrite: (start, end, recv_start, recv_end,
    rest_start, rest_end, name, newlines) as offsets into `text`: the rest
    is the source after the first comma up to the `)`, as it stands (empty
    when the call has one argument); `recv` gets parentheses when it isn't
    simple (name prefixed with '('); `newlines`: the line breaks around the
    receiver, which move inside the parentheses so no line moves."""
    toks = _tokens(text)
    at = _offsets(text)
    found = []
    for k, (kind, line, col, eline, ecol) in enumerate(toks):
        if kind != "IDENT" or k + 1 >= len(toks) or toks[k + 1][0] != "LPAREN":
            continue
        name = text[at(line, col):at(eline, ecol)]
        if name not in BUILTINS or (k > 0 and toks[k - 1][0] in ("DOT", "FUN")):
            continue
        depth = 0
        j = k + 1
        args = [[]]
        while j < len(toks):
            t = toks[j]
            if t[0] in ("LPAREN", "LBRACKET", "LBRACE"):
                depth += 1
                if depth > 1:
                    args[-1].append(t)
            elif t[0] in ("RPAREN", "RBRACKET", "RBRACE"):
                depth -= 1
                if depth == 0:
                    break
                args[-1].append(t)
            elif t[0] == "COMMA" and depth == 1:
                args.append([])
            elif t[0] != "NEWLINE":
                args[-1].append(t)
            j += 1
        if j >= len(toks) or not args[0]:
            continue
        first = args[0]
        r0, r1 = at(first[0][1], first[0][2]), at(first[-1][3], first[-1][4])
        close = at(toks[j][1], toks[j][2])
        opened = at(toks[k + 1][1], toks[k + 1][2]) + 1
        if len(args) > 1:
            comma = text.index(",", r1)
            s0, s1 = comma + 1, close
            gaps = text[opened:r0] + text[r1:comma]
        else:
            s0 = s1 = close
            gaps = text[opened:r0] + text[r1:close]
        found.append((at(line, col), close + 1, r0, r1, s0, s1, ("" if _simple(first) else "(") + name,
                      gaps.count("\n")))
    chosen = []
    last_end = -1
    for e in sorted(found):
        if e[0] >= last_end:
            chosen.append(e)
            last_end = e[1]
    return chosen


def _apply(text: str, edits, piece=lambda a, b: None, newline: str = "\n") -> str:
    """`text` with the edits made; `piece(a, b)` may give the text of the
    span a..b another way (a literal's source, where a line break is
    `newline`)."""
    take = (lambda a, b: piece(a, b) if piece(a, b) is not None else text[a:b])
    out = []
    last = 0
    for (s, e, r0, r1, s0, s1, name, nl) in edits:
        out.append(take(last, s))
        recv = take(r0, r1)
        if name.startswith("("):
            name = name[1:]
            recv = "(" + recv + ")"
        rest = take(s0, s1)
        if not rest.strip(" \t"):
            rest = ""
        elif not rest.lstrip(" \t").startswith(("\n", "\\n")):
            rest = rest.lstrip(" \t")
        out.append(f"{recv}.{name}({newline * nl}{rest})")
        last = e
    out.append(take(last, len(text)))
    return "".join(out)


def _apply_mapped(text: str, edits) -> tuple[str, list[int]]:
    """`_apply` with an exact position map: for each offset of `text` (and
    its end), the offset in the result where that character went. A call's
    name, parentheses, receiver and rest go where the rewrite puts them; the
    name's first character, where the call expression began, maps to where
    it begins now (the receiver); a dropped character (the comma, a space)
    to the next one kept."""
    out: list[str] = []
    origin: list[int] = []    # for each output character, its source offset or -1

    def copy(a, b):
        for i in range(a, b):
            out.append(text[i])
            origin.append(i)

    def put(s):
        for ch in s:
            out.append(ch)
            origin.append(-1)
    starts = {}
    last = 0
    for (s, e, r0, r1, s0, s1, name, nl) in edits:
        copy(last, s)
        paren = name.startswith("(")
        name = name.lstrip("(")
        starts[s] = len(out)
        if paren:
            put("(")
        copy(r0, r1)
        if paren:
            put(")")
        put(".")
        copy(s, s + len(name))                 # the name
        open_at = text.index("(", s + len(name))
        copy(open_at, open_at + 1)             # its "("
        put("\n" * nl)
        rest_from = s0
        if text[s0:s1].strip(" \t"):
            if not text[s0:s1].lstrip(" \t").startswith("\n"):
                while rest_from < s1 and text[rest_from] in " \t":
                    rest_from += 1
            copy(rest_from, s1)
        copy(e - 1, e)                         # its ")"
        last = e
    copy(last, len(text))
    new = "".join(out)
    where = [-1] * (len(text) + 1)
    for j, i in enumerate(origin):
        if i >= 0:
            where[i] = j
    where[len(text)] = len(new)
    for s, j in starts.items():
        where[s] = j
    for i in range(len(text) - 1, -1, -1):
        if where[i] < 0:
            where[i] = where[i + 1]
    return new, where


def rewrite_mapped(text: str) -> tuple[str, list[int]]:
    """`rewrite_text`, with the position map from the original's offsets
    (and its end) into the result's."""
    where = list(range(len(text) + 1))
    for _ in range(50):
        edits = _edits(text)
        if not edits:
            break
        new, step = _apply_mapped(text, edits)
        where = [step[w] for w in where]
        text = new
    return text, where


def rewrite_text(text: str) -> str:
    """`text` with every builtin call made a method call, nested ones too."""
    for _ in range(50):
        edits = _edits(text)
        if not edits:
            return text
        text = _apply(text, edits)
    return text


# -- containers of Myla text ---------------------------------------------------

def _rewrite_markdown(text: str) -> str:
    out = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        out.append(lines[i])
        m = re.match(r"^(\s*)```myla\b", lines[i])
        if m:
            j = i + 1
            while j < len(lines) and not re.match(r"^\s*```\s*$", lines[j]):
                j += 1
            ind = m.group(1)
            body = [ln[len(ind):] if ln.startswith(ind) else ln for ln in lines[i + 1:j]]
            new = rewrite_text("\n".join(body) + "\n").split("\n")[:-1]
            out.extend(ind + ln if ln else ln for ln in new)
            i = j
            continue
        i += 1
    return "\n".join(out)


_MYLA_HINT = re.compile(r"\bfun\s+\w+\s*[(<]|#main\b|\blet\s+\w+\s*=|\bvar\s+\w+\s*[=:]")


def _literal_value_map(raw: str):
    """(value, offsets): a non-f, non-bytes Python string literal's value and,
    for each value index, the span of source characters it came from."""
    m = re.match(r"(?is)^([ru]*)('''|\"\"\"|'|\")", raw)
    prefix, quote = m.group(1).lower(), m.group(2)
    body_start = len(m.group(0))
    body_end = len(raw) - len(quote)
    value = []
    spans = []
    i = body_start
    while i < body_end:
        c = raw[i]
        if c == "\\" and "r" not in prefix:
            n = raw[i + 1]
            simple = {"n": "\n", "t": "\t", "\\": "\\", "'": "'", '"': '"', "r": "\r", "0": "\0", "a": "\a",
                      "b": "\b", "f": "\f", "v": "\v"}
            if n == "\n":
                i += 2
                continue
            if n in simple and not (n == "0" and i + 2 < body_end and raw[i + 2].isdigit()):
                value.append(simple[n])
                spans.append((i, i + 2))
                i += 2
                continue
            if n == "x":
                value.append(chr(int(raw[i + 2:i + 4], 16)))
                spans.append((i, i + 4))
                i += 4
                continue
            if n == "u":
                value.append(chr(int(raw[i + 2:i + 6], 16)))
                spans.append((i, i + 6))
                i += 6
                continue
            if n == "U":
                value.append(chr(int(raw[i + 2:i + 10], 16)))
                spans.append((i, i + 10))
                i += 10
                continue
            if n == "N":
                e = raw.index("}", i)
                value.append(ast.literal_eval('"' + raw[i:e + 1] + '"'))
                spans.append((i, e + 1))
                i = e + 1
                continue
            if n in "01234567":
                k = i + 1
                while k < min(i + 4, body_end) and raw[k] in "01234567":
                    k += 1
                value.append(chr(int(raw[i + 1:k], 8)))
                spans.append((i, k))
                i = k
                continue
            value.append("\\")
            spans.append((i, i + 1))
            i += 1
            continue
        value.append(c)
        spans.append((i, i + 1))
        i += 1
    return "".join(value), spans, body_end


def _rewrite_literal(raw: str) -> str | None:
    """The literal with its Myla code rewritten, edits made on its source so
    escapes stay as they were; None when nothing changes or it can't be done
    safely."""
    try:
        value, spans, body_end = _literal_value_map(raw)
    except (ValueError, IndexError):
        return None
    if ast.literal_eval(raw) != value:
        return None
    new_value = value
    new_raw = raw
    for _ in range(20):
        edits = _edits(new_value)
        if not edits:
            break

        def src(a, b, spans=spans, raw_now=new_raw):
            if a == b:
                start = spans[a][0] if a < len(spans) else body_end
                return raw_now[start:start]
            return raw_now[spans[a][0]:spans[b - 1][1]]

        head = new_raw[:spans[0][0]] if spans else new_raw[:body_end]
        tail = new_raw[body_end:]
        newline = "\n" if raw.lstrip("rRuU")[:3] in ('"""', "'''") else "\\n"
        body = _apply(new_value, edits, piece=lambda a, b: src(a, b), newline=newline)
        candidate = head + body + tail
        try:
            new_value2, spans2, body_end2 = _literal_value_map(candidate)
        except (ValueError, IndexError):
            return None
        if new_value2 != _apply(new_value, edits) or ast.literal_eval(candidate) != new_value2:
            return None
        new_raw, new_value, spans, body_end = candidate, new_value2, spans2, body_end2
    return new_raw if new_raw != raw else None


def _rewrite_python(text: str) -> str:
    """The Myla programs in a Python file's string literals: a run of
    adjacent literals that looks like Myla code (not a docstring, not an
    f-string or bytes)."""
    toks = list(tokenize.generate_tokens(io.StringIO(text).readline))
    lines = text.split("\n")
    starts = [0]
    for ln in lines:
        starts.append(starts[-1] + len(ln) + 1)
    at = lambda pos: starts[pos[0] - 1] + pos[1]
    groups = []
    i = 0
    while i < len(toks):
        if toks[i].type == tokenize.STRING:
            j = i
            group = []
            while j < len(toks) and toks[j].type in (tokenize.STRING, tokenize.NL, tokenize.COMMENT):
                if toks[j].type == tokenize.STRING:
                    group.append(toks[j])
                j += 1
            prev = next((t for t in reversed(toks[:i]) if t.type not in (tokenize.NL, tokenize.COMMENT)), None)
            docstring = prev is None or prev.type in (tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
                                                      tokenize.ENCODING)
            groups.append((group, docstring))
            i = j
        else:
            i += 1
    edits = []
    for group, docstring in groups:
        if docstring:
            continue
        raws = [t.string for t in group]
        if any(re.match(r"(?i)^[rub]*[fb]", r) for r in raws):
            continue
        try:
            joined = "".join(ast.literal_eval(r) for r in raws)
        except (ValueError, SyntaxError):
            continue
        if not isinstance(joined, str) or not _MYLA_HINT.search(joined):
            continue
        for t in group:
            new = _rewrite_literal(t.string)
            if new is not None:
                edits.append((at(t.start), at(t.end), new))
    for s, e, new in sorted(edits, reverse=True):
        text = text[:s] + new + text[e:]
    return text


def _rewrite_json(text: str) -> str:
    data = json.loads(text)

    def walk(v):
        if isinstance(v, str):
            return rewrite_text(v) if _MYLA_HINT.search(v) else v
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, dict):
            return {k: (walk(x) if k in ("source",) or isinstance(x, (list, dict)) else x) for k, x in v.items()}
        return v
    new = walk(data)
    if new == data:
        return text
    indent = None
    m = re.match(r"^[\[{]\n( +)", text)
    if m:
        indent = len(m.group(1))
    return json.dumps(new, indent=indent, ensure_ascii=False) + ("\n" if text.endswith("\n") else "")


def rewrite_file(path: str) -> bool:
    with open(path, encoding="utf-8", errors="surrogateescape") as fh:
        text = fh.read()
    if path.endswith(".my"):
        new = rewrite_text(text)
    elif path.endswith(".md"):
        new = _rewrite_markdown(text)
    elif path.endswith(".py"):
        new = _rewrite_python(text)
    elif path.endswith(".json"):
        new = _rewrite_json(text)
    else:
        return False
    if new == text:
        return False
    with open(path, "w", encoding="utf-8", errors="surrogateescape") as fh:
        fh.write(new)
    return True


def main() -> int:
    changed = [p for p in sys.argv[1:] if rewrite_file(p)]
    print(f"{len(changed)} of {len(sys.argv) - 1} files rewritten")
    for p in changed:
        print("  " + os.path.relpath(p, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
