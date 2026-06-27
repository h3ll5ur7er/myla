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
from .tokens import INT_SUFFIXES, KEYWORDS, Token, TokenKind

# Multi-character operators, longest first so the scanner matches greedily.
_TWO_CHAR_OPS: dict[str, TokenKind] = {
    "->": TokenKind.ARROW,
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
    "<": TokenKind.LT,
    ">": TokenKind.GT,
    "!": TokenKind.BANG,
    "=": TokenKind.ASSIGN,
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
}

_STRING_ESCAPES: dict[str, str] = {
    "n": "\n",
    "t": "\t",
    "\\": "\\",
    '"': '"',
}


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
            elif c == '"':
                self._string()
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

    def _number(self) -> None:
        start_line, start_col = self.line, self.column
        start_pos = self.pos
        while not self._at_end() and self._peek().isdigit():
            self._advance()
        digits = self.source[start_pos:self.pos]
        value = int(digits)

        suffix: str | None = None
        if not self._at_end() and self._peek() in ("i", "u"):
            suffix_pos = self.pos
            self._advance()  # i / u
            while not self._at_end() and self._peek().isdigit():
                self._advance()
            candidate = self.source[suffix_pos:self.pos]
            if candidate not in INT_SUFFIXES:
                raise LexError(
                    f"invalid integer literal suffix '{candidate}'",
                    start_line, start_col,
                )
            suffix = candidate
        elif not self._at_end() and _is_ident_continue(self._peek()):
            # e.g. `5x` or `123abc`: a number cannot abut identifier chars.
            bad = self._peek()
            raise LexError(
                f"invalid integer literal: unexpected '{bad}' after digits",
                self.line, self.column,
            )

        lexeme = self.source[start_pos:self.pos]
        self._add(TokenKind.INT, lexeme, start_line, start_col, value=value, suffix=suffix)

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
