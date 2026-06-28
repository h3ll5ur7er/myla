"""The Myla lexer: source text -> list of Tokens.

Implements the lexical grammar in docs/grammar.md §1. The lexer is a single
forward pass that tracks 1-based line/column positions, skips whitespace and
comments, coalesces runs of blank lines into a single NEWLINE separator, and
emits a trailing EOF token.

Newlines are significant as statement separators (see the spec), so they are
emitted as NEWLINE tokens rather than skipped. Leading and duplicate newlines
are suppressed to keep the token stream clean for the parser.
"""
from __future__ import annotations

from .errors import LexError
from .tokens import FLOAT_SUFFIXES, INT_SUFFIXES, KEYWORDS, Token, TokenKind

# Multi-character operators, longest first so the scanner matches greedily.
_TWO_CHAR_OPS: dict[str, TokenKind] = {
    "->": TokenKind.ARROW,
    "=>": TokenKind.FATARROW,
    "|>": TokenKind.PIPEGT,
    "..": TokenKind.DOTDOT,
    "==": TokenKind.EQ,
    "!=": TokenKind.NE,
    "<=": TokenKind.LE,
    ">=": TokenKind.GE,
    "&&": TokenKind.AND,
    "||": TokenKind.OR,
}

_ONE_CHAR_OPS: dict[str, TokenKind] = {
    "+": TokenKind.PLUS,
    "-": TokenKind.MINUS,
    "*": TokenKind.STAR,
    "/": TokenKind.SLASH,
    "%": TokenKind.PERCENT,
    "&": TokenKind.AMP,
    "^": TokenKind.CARET,
    "~": TokenKind.TILDE,
    "<": TokenKind.LT,
    ">": TokenKind.GT,
    "!": TokenKind.BANG,
    "=": TokenKind.ASSIGN,
    "|": TokenKind.PIPE,
    "(": TokenKind.LPAREN,
    ")": TokenKind.RPAREN,
    "{": TokenKind.LBRACE,
    "}": TokenKind.RBRACE,
    "[": TokenKind.LBRACKET,
    "]": TokenKind.RBRACKET,
    ",": TokenKind.COMMA,
    ":": TokenKind.COLON,
    ".": TokenKind.DOT,
    "#": TokenKind.HASH,
    "?": TokenKind.QUESTION,
}

_STRING_ESCAPES: dict[str, str] = {
    "n": "\n",
    "t": "\t",
    "\\": "\\",
    '"': '"',
}

# Char-literal escapes -> the Unicode scalar they denote. `'\''` and `'\0'` are
# char-only; `'\u{…}'` (handled separately) names an arbitrary scalar (v0.5.3).
_CHAR_ESCAPES: dict[str, int] = {
    "n": 10,
    "t": 9,
    "r": 13,
    "\\": 92,
    "'": 39,
    "0": 0,
}

_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


# Digit alphabets per integer base (docs/grammar.md: int_lit).
_BASE_DIGITS: dict[int, str] = {
    2: "01",
    8: "01234567",
    10: "0123456789",
    16: "0123456789abcdefABCDEF",
}
_BASE_PREFIX: dict[str, int] = {"x": 16, "b": 2, "o": 8}


def _is_ident_start(c: str) -> bool:
    return c.isalpha() or c == "_"


def _is_ident_continue(c: str) -> bool:
    return c.isalnum() or c == "_"


class Lexer:
    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.column = 1
        self.tokens: list[Token] = []

    # -- low-level cursor helpers -------------------------------------------

    def _at_end(self) -> bool:
        return self.pos >= len(self.source)

    def _peek(self, offset: int = 0) -> str:
        idx = self.pos + offset
        if idx >= len(self.source):
            return "\0"
        return self.source[idx]

    def _advance(self) -> str:
        c = self.source[self.pos]
        self.pos += 1
        if c == "\n":
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return c

    # -- token emission ------------------------------------------------------

    def _add(self, kind: TokenKind, lexeme: str, line: int, column: int,
             value: object = None, suffix: str | None = None) -> None:
        self.tokens.append(Token(kind, lexeme, line, column, value, suffix))

    def _emit_newline(self) -> None:
        # Suppress a leading newline and collapse consecutive newlines.
        if not self.tokens or self.tokens[-1].kind is TokenKind.NEWLINE:
            return
        self._add(TokenKind.NEWLINE, "\\n", self.line, self.column)

    # -- main loop -----------------------------------------------------------

    def tokenize(self) -> list[Token]:
        while not self._at_end():
            c = self._peek()
            if c == "\n":
                self._advance()
                self._emit_newline()
            elif c in " \t\r":
                self._advance()
            elif c == "/" and self._peek(1) == "/":
                self._line_comment()
            elif c == "/" and self._peek(1) == "*":
                self._block_comment()
            elif c == "f" and self._peek(1) == '"':
                self._fstring()
            elif c == '"':
                self._string()
            elif c == "'":
                self._char()
            elif c.isdigit():
                self._number()
            elif _is_ident_start(c):
                self._identifier()
            else:
                self._operator()

        # A trailing NEWLINE before EOF is harmless but tidy to drop.
        if self.tokens and self.tokens[-1].kind is TokenKind.NEWLINE:
            self.tokens.pop()
        self._add(TokenKind.EOF, "", self.line, self.column)
        return self.tokens

    # -- scanners ------------------------------------------------------------

    def _line_comment(self) -> None:
        while not self._at_end() and self._peek() != "\n":
            self._advance()

    def _block_comment(self) -> None:
        start_line, start_col = self.line, self.column
        self._advance()  # /
        self._advance()  # *
        while not self._at_end():
            if self._peek() == "*" and self._peek(1) == "/":
                self._advance()
                self._advance()
                return
            self._advance()
        raise LexError("unterminated block comment", start_line, start_col)

    def _string(self) -> None:
        start_line, start_col = self.line, self.column
        self._advance()  # opening quote
        chars: list[str] = []
        while True:
            if self._at_end() or self._peek() == "\n":
                raise LexError("unterminated string literal", start_line, start_col)
            c = self._advance()
            if c == '"':
                break
            if c == "\\":
                esc_line, esc_col = self.line, self.column
                if self._at_end():
                    raise LexError("unterminated string literal", start_line, start_col)
                esc = self._advance()
                if esc not in _STRING_ESCAPES:
                    raise LexError(
                        f"invalid escape sequence '\\{esc}'", esc_line, esc_col
                    )
                chars.append(_STRING_ESCAPES[esc])
            else:
                chars.append(c)
        value = "".join(chars)
        self._add(TokenKind.STRING, value, start_line, start_col, value=value)

    def _fstring(self) -> None:
        """Scan an interpolated string `f"…{expr}…"` and lower it *inline* to a
        `format(fmt, args…)` call (D58, v0.5.6): the literal text becomes the
        format string (`{}` per hole, `{{`/`}}` literal braces preserved, normal
        string escapes applied), and each balanced `{ … }` hole is re-lexed as an
        ordinary expression. Pure front-end sugar — no new tokens, AST, checker,
        or runtime; the emitted `format(...)` call rides the existing machinery.
        """
        start_line, start_col = self.line, self.column
        self._advance()  # f
        self._advance()  # opening quote
        fmt_chars: list[str] = []
        arg_token_lists: list[list[Token]] = []
        while True:
            if self._at_end() or self._peek() == "\n":
                raise LexError(
                    'unterminated f-string literal (f"…" is single-line)',
                    start_line, start_col,
                )
            c = self._peek()
            if c == '"':
                self._advance()
                break
            if c == "{":
                if self._peek(1) == "{":
                    self._advance()
                    self._advance()
                    fmt_chars.append("{{")
                    continue
                self._advance()  # opening '{'
                arg_token_lists.append(self._fstring_hole(start_line, start_col))
                fmt_chars.append("{}")
                continue
            if c == "}":
                if self._peek(1) == "}":
                    self._advance()
                    self._advance()
                    fmt_chars.append("}}")
                    continue
                raise LexError(
                    "single '}' in f-string (use '}}' for a literal '}')",
                    self.line, self.column,
                )
            if c == "\\":
                esc_line, esc_col = self.line, self.column
                self._advance()  # backslash
                if self._at_end() or self._peek() == "\n":
                    raise LexError(
                        "unterminated f-string literal", start_line, start_col
                    )
                esc = self._advance()
                if esc not in _STRING_ESCAPES:
                    raise LexError(
                        f"invalid escape sequence '\\{esc}'", esc_line, esc_col
                    )
                fmt_chars.append(_STRING_ESCAPES[esc])
                continue
            self._advance()
            fmt_chars.append(c)
        # Emit `format ( "<fmt>" [ , <hole-tokens> ]* )` in place.
        self._add(TokenKind.IDENT, "format", start_line, start_col, value="format")
        self._add(TokenKind.LPAREN, "(", start_line, start_col)
        fmt = "".join(fmt_chars)
        self._add(TokenKind.STRING, fmt, start_line, start_col, value=fmt)
        for toks in arg_token_lists:
            self._add(TokenKind.COMMA, ",", start_line, start_col)
            self.tokens.extend(toks)
        self._add(TokenKind.RPAREN, ")", start_line, start_col)

    def _fstring_hole(self, fs_line: int, fs_col: int) -> list[Token]:
        """Scan one `{ … }` hole (cursor just past the `{`) by a balanced-brace
        scan that skips nested string/char literals, then re-lex the slice as a
        normal expression. Returns its tokens with positions mapped back onto the
        f-string's line."""
        slice_line, slice_col = self.line, self.column
        buf: list[str] = []
        depth = 1
        while True:
            if self._at_end() or self._peek() == "\n":
                raise LexError("unterminated '{' in f-string", fs_line, fs_col)
            c = self._peek()
            if c == "{":
                depth += 1
                buf.append(self._advance())
            elif c == "}":
                self._advance()
                depth -= 1
                if depth == 0:
                    break
                buf.append("}")
            elif c == '"' or c == "'":
                self._fstring_copy_quoted(buf, c)
            else:
                buf.append(self._advance())
        src = "".join(buf)
        if not src.strip():
            raise LexError(
                "empty '{}' hole in f-string (expected an expression)",
                slice_line, slice_col,
            )
        out: list[Token] = []
        for t in Lexer(src).tokenize():
            if t.kind in (TokenKind.EOF, TokenKind.NEWLINE):
                continue
            # The slice is single-line, so every sub-token sits on `slice_line`;
            # shift its column to its true position in the original source.
            col = slice_col + (t.column - 1)
            out.append(Token(t.kind, t.lexeme, slice_line, col, t.value, t.suffix))
        return out

    def _fstring_copy_quoted(self, buf: list[str], quote: str) -> None:
        """Copy a nested string/char literal verbatim into `buf` (cursor at the
        opening quote) so quotes and braces inside it don't disturb the brace
        scan; escapes are copied raw for the sub-lexer to re-process."""
        buf.append(self._advance())  # opening quote
        while True:
            if self._at_end() or self._peek() == "\n":
                raise LexError(
                    "unterminated string in f-string expression",
                    self.line, self.column,
                )
            ch = self._advance()
            buf.append(ch)
            if ch == "\\":
                if self._at_end():
                    raise LexError(
                        "unterminated string in f-string expression",
                        self.line, self.column,
                    )
                buf.append(self._advance())
                continue
            if ch == quote:
                return

    def _char(self) -> None:
        """Scan a char literal `'a'`, `'\\n'`, `'\\0'`, `'é'`, `'\\u{1F600}'`, …
        producing a CHAR token whose value is the Unicode scalar (codepoint).

        An ASCII literal stays flexible to the integer types (D42 byte compat);
        a multi-byte scalar is `char`-only (resolved by the checker)."""
        start_line, start_col = self.line, self.column
        start_pos = self.pos
        self._advance()  # opening quote
        if self._at_end() or self._peek() in ("\n", "'"):
            raise LexError("empty or unterminated char literal", start_line, start_col)
        c = self._advance()
        if c == "\\":
            esc_line, esc_col = self.line, self.column
            if self._at_end():
                raise LexError("unterminated char literal", start_line, start_col)
            esc = self._advance()
            if esc == "u":
                cp = self._unicode_escape(esc_line, esc_col)
            elif esc in _CHAR_ESCAPES:
                cp = _CHAR_ESCAPES[esc]
            else:
                raise LexError(f"invalid escape sequence '\\{esc}'", esc_line, esc_col)
        else:
            cp = ord(c)
        if self._at_end() or self._peek() != "'":
            raise LexError(
                "char literal must contain exactly one character",
                start_line, start_col,
            )
        self._advance()  # closing quote
        lexeme = self.source[start_pos:self.pos]
        self._add(TokenKind.CHAR, lexeme, start_line, start_col, value=cp)

    def _unicode_escape(self, line: int, col: int) -> int:
        """Parse the body of a `\\u{HEX}` char escape (the cursor is just past the
        `u`). Returns the Unicode scalar; rejects empty/oversized values and the
        surrogate range."""
        if self._at_end() or self._advance() != "{":
            raise LexError("expected '{' after '\\u' in char literal", line, col)
        digits: list[str] = []
        while not self._at_end() and self._peek() != "}":
            d = self._advance()
            if d not in _HEX_DIGITS:
                raise LexError(
                    f"invalid hex digit '{d}' in '\\u{{…}}' escape", line, col)
            digits.append(d)
        if self._at_end():
            raise LexError("unterminated '\\u{…}' escape", line, col)
        self._advance()  # closing brace
        if not digits:
            raise LexError("empty '\\u{…}' escape", line, col)
        cp = int("".join(digits), 16)
        if cp > 0x10FFFF or 0xD800 <= cp <= 0xDFFF:
            raise LexError(
                f"invalid Unicode scalar U+{cp:X} in char literal "
                "(must be 0..0x10FFFF and not a surrogate)",
                line, col,
            )
        return cp

    def _scan_digits(self, base: int) -> str:
        """Consume a run of base-`base` digits with optional `_` separators.

        Returns the digits with separators stripped. Underscores may only appear
        between two digits (no leading, trailing, or doubled `_`).
        """
        allowed = _BASE_DIGITS[base]
        chars: list[str] = []
        prev_underscore = False
        while not self._at_end():
            c = self._peek()
            if c == "_":
                if not chars or prev_underscore:
                    raise LexError(
                        "'_' separators in an integer literal must sit between "
                        "digits",
                        self.line, self.column,
                    )
                prev_underscore = True
                self._advance()
                continue
            if c in allowed:
                chars.append(c)
                prev_underscore = False
                self._advance()
                continue
            break
        if prev_underscore:
            raise LexError(
                "integer literal cannot end with '_'", self.line, self.column
            )
        return "".join(chars)

    def _number(self) -> None:
        start_line, start_col = self.line, self.column
        start_pos = self.pos

        # Prefixed bases (0x/0b/0o) are integer-only; floats are base 10.
        if self._peek() == "0" and self._peek(1).lower() in _BASE_PREFIX:
            prefix = self._peek(1).lower()
            base = _BASE_PREFIX[prefix]
            self._advance()  # 0
            self._advance()  # x / b / o
            digits = self._scan_digits(base)
            if digits == "":
                raise LexError(
                    f"integer literal has no digits after '0{prefix}'",
                    start_line, start_col,
                )
            value = int(digits, base)
            suffix = self._int_suffix(start_line, start_col)
            lexeme = self.source[start_pos:self.pos]
            self._add(TokenKind.INT, lexeme, start_line, start_col,
                      value=value, suffix=suffix)
            return

        # Base-10: may turn out to be a float (fraction, exponent, or `f`-suffix).
        int_digits = self._scan_digits(10)
        frac_digits = ""
        exp_str = ""
        is_float = False

        # Fractional part: only when a digit follows the dot, so `2..10` stays a
        # range (`INT DOTDOT INT`) and `t.0` tuple indexing is unaffected.
        if self._peek() == "." and self._peek(1).isdigit():
            self._advance()  # .
            frac_digits = self._scan_digits(10)
            is_float = True

        # Exponent: `e`/`E` with an optional sign, then digits.
        if self._peek() in ("e", "E"):
            nxt = self._peek(1)
            if nxt.isdigit() or (nxt in ("+", "-") and self._peek(2).isdigit()):
                self._advance()  # e / E
                sign = ""
                if self._peek() in ("+", "-"):
                    sign = self._advance()
                exp_digits = self._scan_digits(10)
                exp_str = "e" + sign + exp_digits
                is_float = True

        suffix: str | None = None
        if self._peek() == "f":
            suffix_pos = self.pos
            self._advance()  # f
            while self._peek().isdigit():
                self._advance()
            candidate = self.source[suffix_pos:self.pos]
            if candidate not in FLOAT_SUFFIXES:
                raise LexError(
                    f"invalid float literal suffix '{candidate}'",
                    start_line, start_col,
                )
            suffix = candidate
            is_float = True
        elif not is_float:
            suffix = self._int_suffix(start_line, start_col)

        if is_float:
            if _is_ident_continue(self._peek()):
                bad = self._peek()
                raise LexError(
                    f"invalid float literal: unexpected '{bad}' after digits",
                    self.line, self.column,
                )
            text = int_digits + ("." + frac_digits if frac_digits else "") + exp_str
            lexeme = self.source[start_pos:self.pos]
            self._add(TokenKind.FLOAT, lexeme, start_line, start_col,
                      value=float(text), suffix=suffix)
            return

        lexeme = self.source[start_pos:self.pos]
        self._add(TokenKind.INT, lexeme, start_line, start_col,
                  value=int(int_digits, 10), suffix=suffix)

    def _int_suffix(self, start_line: int, start_col: int) -> str | None:
        """Consume an optional integer type suffix (`i8`..`u64`).

        Raises on an unknown suffix or on identifier characters abutting the
        digits (e.g. `5x`).
        """
        if self._peek() in ("i", "u"):
            suffix_pos = self.pos
            self._advance()  # i / u
            while self._peek().isdigit():
                self._advance()
            candidate = self.source[suffix_pos:self.pos]
            if candidate not in INT_SUFFIXES:
                raise LexError(
                    f"invalid integer literal suffix '{candidate}'",
                    start_line, start_col,
                )
            return candidate
        if _is_ident_continue(self._peek()):
            # e.g. `5x` or `123abc`: a number cannot abut identifier chars.
            bad = self._peek()
            raise LexError(
                f"invalid integer literal: unexpected '{bad}' after digits",
                self.line, self.column,
            )
        return None

    def _identifier(self) -> None:
        start_line, start_col = self.line, self.column
        start_pos = self.pos
        while not self._at_end() and _is_ident_continue(self._peek()):
            self._advance()
        text = self.source[start_pos:self.pos]

        kind = KEYWORDS.get(text, TokenKind.IDENT)
        value: object = text
        if kind is TokenKind.TRUE:
            value = True
        elif kind is TokenKind.FALSE:
            value = False
        self._add(kind, text, start_line, start_col, value=value)

    def _operator(self) -> None:
        start_line, start_col = self.line, self.column
        two = self.source[self.pos:self.pos + 2]
        if two in _TWO_CHAR_OPS:
            self._advance()
            self._advance()
            self._add(_TWO_CHAR_OPS[two], two, start_line, start_col)
            return
        c = self._peek()
        if c in _ONE_CHAR_OPS:
            self._advance()
            self._add(_ONE_CHAR_OPS[c], c, start_line, start_col)
            return
        raise LexError(f"unexpected character '{c}'", start_line, start_col)


def tokenize(source: str) -> list[Token]:
    """Convenience wrapper: lex `source` and return the token list."""
    return Lexer(source).tokenize()
