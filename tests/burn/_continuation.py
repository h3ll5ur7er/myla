"""Line continuation (D104 (3), MYLA-224) for tests that replay the retired
Python lexer's and parser's recorded answers, which were made before it.

Since D104 the lexer makes no NEWLINE token inside `( )` or `[ ]` (unless
within a `{ }` in them) nor after a binary operator that ends a line (not
`>`). `without_continued_newlines` turns a recorded token dump into what the
lexer makes now; `continues_a_line` says whether a source has such a line
break, where a recorded parse no longer describes the token stream."""
from __future__ import annotations

import re
import subprocess

from tests.burn._tools import selfhost_tool

# the kinds after which a line goes on (selfhost/lexer.my: continues_line)
_CONTINUING = {"PLUS", "MINUS", "STAR", "SLASH", "PERCENT", "EQ", "NE", "LT", "LE", "GE", "AND", "OR",
               "AMP", "PIPE", "CARET", "PIPEGT"}
_TOKEN = re.compile(r"^([A-Z_0-9]+) (\d+) (\d+) .* end=(\d+):(\d+)$")


def without_continued_newlines(dump: str) -> str:
    """A canonical token dump (`lex_main`'s) without the NEWLINE tokens that
    line continuation leaves out."""
    out = []
    opens: list[bool] = []
    last = ""
    for line in dump.split("\n"):
        m = _TOKEN.match(line)
        kind = m.group(1) if m else ""
        if kind == "NEWLINE" and ((opens and opens[-1]) or last in _CONTINUING):
            continue
        if kind in ("LPAREN", "LBRACKET"):
            opens.append(True)
        elif kind == "LBRACE":
            opens.append(False)
        elif kind in ("RPAREN", "RBRACKET") and opens and opens[-1]:
            opens.pop()
        elif kind == "RBRACE":
            while opens and opens[-1]:
                opens.pop()
            if opens:
                opens.pop()
        if kind:
            last = kind
        out.append(line)
    return "\n".join(out)


def continues_a_line(path: str) -> bool:
    """Whether the lexer leaves out a line break of the file `path`: two
    tokens on different lines with no NEWLINE between them."""
    dump = subprocess.run([selfhost_tool("lex_main"), path], capture_output=True, text=True).stdout
    prev_end = None
    for line in dump.split("\n"):
        m = _TOKEN.match(line)
        if not m:
            continue
        kind, start_line = m.group(1), int(m.group(2))
        if kind == "NEWLINE":
            prev_end = None
            continue
        if prev_end is not None and start_line > prev_end and kind != "EOF":
            return True
        prev_end = int(m.group(4))
    return False
