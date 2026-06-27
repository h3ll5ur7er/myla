"""Myla bootstrapping compiler/interpreter (v0.0, written in Python).

Package layout (see docs/architecture.md):
    tokens.py       Token + TokenKind definitions
    lexer.py        source text -> [Token]
    errors.py       diagnostics (line/col) and error types
    cli.py          command-line interface
    ast.py          (planned) AST node definitions
    parser.py       (planned) [Token] -> AST
    types.py        (planned) type checker
    interpreter.py  (planned) tree-walking evaluator
    compiler/       (planned) AST -> x86-64 assembly
"""

__version__ = "0.0.1"
