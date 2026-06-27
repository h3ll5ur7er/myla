"""Command-line interface for the Myla toolchain.

Commands (see README "CLI"):
    run <file.my>            interpret a program            (implemented)
    test <file.my>           run #test cases                (implemented)
    build <file.my> -o <bin> compile to a native binary     (implemented)
    repl                     interactive interpreter        (planned: v0.0.2)

Development/debug commands available now:
    tokenize <file.my>       print the token stream (the lexer is implemented)
    parse <file.my>          print the parsed AST (the parser is implemented)
"""
from __future__ import annotations

import argparse
import sys

from . import __version__
from .ast import format_ast
from .compiler import BuildError, build as build_program
from .errors import MylaError
from .interpreter import Interpreter
from .lexer import tokenize as lex_source
from .parser import parse as parse_tokens
from .types import check as check_program


def _read_source(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _cmd_tokenize(args: argparse.Namespace) -> int:
    source = _read_source(args.file)
    try:
        tokens = lex_source(source)
    except MylaError as err:
        print(err.render(source, args.file), file=sys.stderr)
        return 1
    for tok in tokens:
        print(tok)
    return 0


def _cmd_parse(args: argparse.Namespace) -> int:
    source = _read_source(args.file)
    try:
        tokens = lex_source(source)
        program = parse_tokens(tokens)
    except MylaError as err:
        print(err.render(source, args.file), file=sys.stderr)
        return 1
    print(format_ast(program))
    return 0


def _front_end(source: str, filename: str):
    """Lex -> parse -> type-check. Returns the populated Checker."""
    tokens = lex_source(source)
    program = parse_tokens(tokens)
    return check_program(program)


def _cmd_run(args: argparse.Namespace) -> int:
    source = _read_source(args.file)
    try:
        checker = _front_end(source, args.file)
        Interpreter(checker).run()
    except MylaError as err:
        print(err.render(source, args.file), file=sys.stderr)
        return 1
    return 0


def _cmd_test(args: argparse.Namespace) -> int:
    source = _read_source(args.file)
    try:
        checker = _front_end(source, args.file)
        results = Interpreter(checker).run_tests()
    except MylaError as err:
        print(err.render(source, args.file), file=sys.stderr)
        return 1

    if not results:
        print("no #test cases found.")
        return 0

    failures = 0
    for r in results:
        if r.passed:
            print(f"PASS  {r.function} #{r.index}")
        else:
            failures += 1
            print(f"FAIL  {r.function} #{r.index}: {r.detail}")
    total = len(results)
    print(f"\n{total - failures}/{total} passed.")
    return 1 if failures else 0


def _cmd_build(args: argparse.Namespace) -> int:
    source = _read_source(args.file)
    try:
        checker = _front_end(source, args.file)
        path = build_program(checker, args.output, keep_asm=args.keep_asm)
    except MylaError as err:
        print(err.render(source, args.file), file=sys.stderr)
        return 1
    except BuildError as err:
        print(f"build error: {err}", file=sys.stderr)
        return 1
    print(f"wrote {path}")
    return 0


def _not_yet(name: str, milestone: str):
    def handler(args: argparse.Namespace) -> int:
        print(
            f"`myla {name}` is not implemented yet (planned for {milestone}).",
            file=sys.stderr,
        )
        return 2

    return handler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="myla", description="The Myla language toolchain.")
    parser.add_argument("--version", action="version", version=f"myla {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="interpret a .my file")
    p_run.add_argument("file")
    p_run.set_defaults(func=_cmd_run)

    p_build = sub.add_parser("build", help="compile a .my file to a native binary")
    p_build.add_argument("file")
    p_build.add_argument("-o", "--output", default="a.out")
    p_build.add_argument("--keep-asm", action="store_true",
                         help="keep the generated .s assembly next to the output")
    p_build.set_defaults(func=_cmd_build)

    p_test = sub.add_parser("test", help="run #test cases in a .my file")
    p_test.add_argument("file")
    p_test.set_defaults(func=_cmd_test)

    p_repl = sub.add_parser("repl", help="start the interactive interpreter (planned: v0.0.2)")
    p_repl.set_defaults(func=_not_yet("repl", "v0.0.2"))

    p_tok = sub.add_parser("tokenize", help="print the lexer's token stream for a .my file")
    p_tok.add_argument("file")
    p_tok.set_defaults(func=_cmd_tokenize)

    p_parse = sub.add_parser("parse", help="print the parsed AST for a .my file")
    p_parse.add_argument("file")
    p_parse.set_defaults(func=_cmd_parse)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
