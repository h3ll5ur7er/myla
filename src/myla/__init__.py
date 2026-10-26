"""The Myla reference toolchain, written in Python: the semantics reference
and the first stage of the bootstrap.

Package layout (see docs/Architecture.md):
    tokens.py       Token + TokenKind definitions
    lexer.py        source text -> [Token]
    parser.py       [Token] -> AST
    ast.py          AST node definitions
    canon.py        canonical token/AST dumps (the self-hosted gates' oracle)
    loader.py       module loader: links the import graph into one program
    types.py        type checker
    interpreter.py  tree-walking evaluator
    compiler/       AST -> x86-64 assembly (monomorphization, code generation)
    errors.py       diagnostics (file/line/column) and error types
    cli.py          command-line interface
    lsp/            language server
    std/            the standard library (Myla sources)
"""

__version__ = "0.0.1"
