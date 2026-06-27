"""Token definitions for the Myla lexer.

See docs/grammar.md §1 for the lexical grammar this implements. Note that `int`
is deliberately NOT a keyword: it is a built-in type alias for `int32` and is
lexed as an ordinary identifier, then resolved during type checking.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any


class TokenKind(Enum):
    # literals
    INT = auto()
    STRING = auto()

    # identifiers
    IDENT = auto()

    # keywords
    LET = auto()
    VAR = auto()
    FUN = auto()
    RETURN = auto()
    STRUCT = auto()
    TYPEALIAS = auto()
    IF = auto()
    ELSE = auto()
    WHILE = auto()
    FOR = auto()
    IN = auto()
    TRUE = auto()
    FALSE = auto()
    BOOL = auto()
    STR = auto()
    INT8 = auto()
    INT16 = auto()
    INT32 = auto()
    INT64 = auto()
    UINT8 = auto()
    UINT16 = auto()
    UINT32 = auto()
    UINT64 = auto()

    # operators & punctuation
    ARROW = auto()        # ->
    DOTDOT = auto()       # ..
    EQ = auto()           # ==
    NE = auto()           # !=
    LE = auto()           # <=
    GE = auto()           # >=
    AND = auto()          # &&
    OR = auto()           # ||
    PLUS = auto()         # +
    MINUS = auto()        # -
    STAR = auto()         # *
    SLASH = auto()        # /
    PERCENT = auto()      # %
    LT = auto()           # <
    GT = auto()           # >
    BANG = auto()         # !
    ASSIGN = auto()       # =
    LPAREN = auto()       # (
    RPAREN = auto()       # )
    LBRACE = auto()       # {
    RBRACE = auto()       # }
    LBRACKET = auto()     # [
    RBRACKET = auto()     # ]
    COMMA = auto()        # ,
    COLON = auto()        # :
    DOT = auto()          # .
    HASH = auto()         # #

    # structural
    NEWLINE = auto()      # statement separator
    EOF = auto()


# Keyword text -> TokenKind. `int` is intentionally absent (it is an alias).
KEYWORDS: dict[str, TokenKind] = {
    "let": TokenKind.LET,
    "var": TokenKind.VAR,
    "fun": TokenKind.FUN,
    "return": TokenKind.RETURN,
    "struct": TokenKind.STRUCT,
    "typealias": TokenKind.TYPEALIAS,
    "if": TokenKind.IF,
    "else": TokenKind.ELSE,
    "while": TokenKind.WHILE,
    "for": TokenKind.FOR,
    "in": TokenKind.IN,
    "true": TokenKind.TRUE,
    "false": TokenKind.FALSE,
    "bool": TokenKind.BOOL,
    "str": TokenKind.STR,
    "int8": TokenKind.INT8,
    "int16": TokenKind.INT16,
    "int32": TokenKind.INT32,
    "int64": TokenKind.INT64,
    "uint8": TokenKind.UINT8,
    "uint16": TokenKind.UINT16,
    "uint32": TokenKind.UINT32,
    "uint64": TokenKind.UINT64,
}

# Valid integer-literal type suffixes (docs/grammar.md: int_suffix).
INT_SUFFIXES: frozenset[str] = frozenset(
    {"i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64"}
)


@dataclass(frozen=True)
class Token:
    """A single lexical token.

    Attributes:
        kind:    the token category.
        lexeme:  the exact source text of the token.
        line:    1-based line number of the token's first character.
        column:  1-based column number of the token's first character.
        value:   parsed literal value (int for INT, str for STRING/IDENT and
                 keywords, bool for TRUE/FALSE); None otherwise.
        suffix:  for INT tokens, the type suffix (e.g. "u8") or None.
    """

    kind: TokenKind
    lexeme: str
    line: int
    column: int
    value: Any = None
    suffix: str | None = None

    def __str__(self) -> str:  # pragma: no cover - debugging aid
        extra = ""
        if self.value is not None:
            extra = f" value={self.value!r}"
        if self.suffix is not None:
            extra += f" suffix={self.suffix}"
        return f"{self.kind.name}({self.lexeme!r}{extra}) @ {self.line}:{self.column}"
