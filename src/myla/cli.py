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
import os
import sys

from . import __version__
from .ast import format_ast
from .compiler import BuildError, build as build_program
from .errors import MylaError
from .interpreter import Interpreter
from .lexer import tokenize as lex_source
from .loader import default_stdlib_root, link as link_program, parse_package_flag
from .parser import parse as parse_tokens
from .types import check as check_program


def _read_source(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _render_in_file(err: MylaError, entry: str, entry_source: str) -> str:
    """`err` with the line it points at, from the file it comes from: the
    entry file, or the imported module the error names (MYLA-10)."""
    name, source = entry, entry_source
    if err.path is not None and os.path.realpath(err.path) != os.path.realpath(entry):
        name = os.path.relpath(err.path)
        try:
            source = _read_source(err.path)
        except OSError:
            source = None
    return err.render(source, name)


def report_text(err: MylaError, entry: str, entry_source: str) -> str:
    """What the CLI prints for `err`: it and the errors in its `more`, each in
    its file, a blank line apart, then a summary line when there are several
    (MYLA-65, D80)."""
    errors = [err, *err.more]
    text = "\n\n".join(_render_in_file(e, entry, entry_source) for e in errors)
    if len(errors) > 1:
        text += f"\n\nerror: aborting due to {len(errors)} previous errors"
    return text


def _report(err: MylaError, entry: str, entry_source: str) -> None:
    print(report_text(err, entry, entry_source), file=sys.stderr)


def _warn(checker, entry: str, entry_source: str) -> None:
    """The checker's warnings (D95), each in its file, before the program is
    run or built."""
    for w in checker.warnings:
        print(_render_in_file(w, entry, entry_source) + "\n", file=sys.stderr)


def _cmd_tokenize(args: argparse.Namespace) -> int:
    source = _read_source(args.file)
    try:
        tokens = lex_source(source)
    except MylaError as err:
        print(err.render(source, args.file), file=sys.stderr)
        return 1
    if getattr(args, "canonical", False):
        # Stable cross-implementation format for differential self-hosting tests
        # (docs/Architecture/Self-hosted-compiler.md); the Myla lexer reproduces it byte-for-byte.
        from .canon import canonical_token
        for tok in tokens:
            print(canonical_token(tok))
        return 0
    for tok in tokens:
        print(tok)
    return 0


def _cmd_parse(args: argparse.Namespace) -> int:
    source = _read_source(args.file)
    try:
        tokens = lex_source(source)
        program = parse_tokens(tokens)
    except MylaError as err:
        _report(err, args.file, source)
        return 1
    if getattr(args, "canonical", False):
        from .canon import canonical_ast
        print(canonical_ast(program))
        return 0
    print(format_ast(program))
    return 0


def _front_end(path: str, args: argparse.Namespace):
    """Resolve the module graph rooted at `path` with the packages of the
    `--package name=dir` flags (MYLA-92), then lex -> parse -> type-check the
    merged program. Returns the populated Checker."""
    packages = [parse_package_flag(flag) for flag in args.package or []]
    return check_program(link_program(path, stdlib_root=default_stdlib_root(),
                                      packages=packages))


def _split_package_flags(argv: list[str], flags: list[str]) -> list[str]:
    """`argv` without its `--package <value>` pairs, whose values are added to
    `flags`: `myla run file.my --package geo=dir` takes the flag after the
    file too, as the self-hosted `myla run` does."""
    rest: list[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == "--package" and i + 1 < len(argv):
            flags.append(argv[i + 1])
            i += 2
        else:
            rest.append(argv[i])
            i += 1
    return rest


def _cmd_run(args: argparse.Namespace) -> int:
    source = _read_source(args.file)
    # argv[0] is the program as invoked; the rest are its arguments (parity with
    # the native binary, where the kernel supplies argv at `_start`).
    args.package = list(args.package or [])
    argv = [args.file, *_split_package_flags(args.args, args.package)]
    try:
        checker = _front_end(args.file, args)
        _warn(checker, args.file, source)
        return Interpreter(checker, argv=argv).run()
    except MylaError as err:
        _report(err, args.file, source)
        return 1


def _cmd_test(args: argparse.Namespace) -> int:
    source = _read_source(args.file)
    try:
        checker = _front_end(args.file, args)
        _warn(checker, args.file, source)
        results = Interpreter(checker).run_tests()
    except MylaError as err:
        _report(err, args.file, source)
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
        checker = _front_end(args.file, args)
        _warn(checker, args.file, source)
        path = build_program(checker, args.output, keep_asm=args.keep_asm,
                             debug=args.debug, entry_path=args.file)
    except MylaError as err:
        _report(err, args.file, source)
        return 1
    except BuildError as err:
        print(f"build error: {err}", file=sys.stderr)
        return 1
    print(f"wrote {path}")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    """Type-check a program. With --canonical, emit the stable accept/reject +
    diagnostic-position line for self-hosting differential tests (v0.7): `ok` on
    success, else `err <line> <col> <kind>` for each error (a missing position
    is `-`, and `kind` is the first word of the diagnostic class, e.g.
    `type`/`module`)."""
    source = _read_source(args.file)
    canonical = getattr(args, "canonical", False)
    try:
        checker = _front_end(args.file, args)
    except MylaError as err:
        if canonical:
            for e in (err, *err.more):
                line = "-" if e.line is None else str(e.line)
                col = "-" if e.column is None else str(e.column)
                print(f"err {line} {col} {e.kind.split()[0]}")
            return 0
        _report(err, args.file, source)
        return 1
    if canonical:
        from .canon import canonical_warning
        for w in checker.warnings:
            print(canonical_warning(w))
    else:
        _warn(checker, args.file, source)
    print("ok")
    return 0


def _cmd_repl(args: argparse.Namespace) -> int:
    """The REPL is written in Myla, in the self-hosted CLI (MYLA-82)."""
    print("The REPL is part of the self-hosted CLI: build it with scripts/bootstrap.sh, "
          "then run `build/myla repl`.", file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="myla", description="The Myla language toolchain.")
    parser.add_argument("--version", action="version", version=f"myla {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_package_flag(p: argparse.ArgumentParser) -> None:
        p.add_argument("--package", action="append", metavar="NAME=DIR",
                       help="a dependency: imports of NAME resolve in DIR, as if it were "
                            "the directory NAME/ in the project root (repeatable)")

    p_run = sub.add_parser("run", help="interpret a .my file")
    p_run.add_argument("file")
    p_run.add_argument("args", nargs=argparse.REMAINDER,
                       help="arguments passed to the program (std.process.args)")
    add_package_flag(p_run)
    p_run.set_defaults(func=_cmd_run)

    p_build = sub.add_parser("build", help="compile a .my file to a native binary")
    p_build.add_argument("file")
    p_build.add_argument("-o", "--output", default="a.out")
    p_build.add_argument("--keep-asm", action="store_true",
                         help="keep the generated .s assembly next to the output")
    p_build.add_argument("-g", "--debug", action="store_true",
                         help="emit DWARF debug information so debuggers such as gdb "
                              "can break on and step through Myla source lines and "
                              "show variables")
    add_package_flag(p_build)
    p_build.set_defaults(func=_cmd_build)

    p_test = sub.add_parser("test", help="run #test cases in a .my file")
    p_test.add_argument("file")
    add_package_flag(p_test)
    p_test.set_defaults(func=_cmd_test)

    p_repl = sub.add_parser("repl", help="the interactive interpreter: see `build/myla repl`")
    p_repl.set_defaults(func=_cmd_repl)

    p_tok = sub.add_parser("tokenize", help="print the lexer's token stream for a .my file")
    p_tok.add_argument("file")
    p_tok.add_argument("--canonical", action="store_true",
                       help="emit the stable cross-implementation dump format "
                            "(for self-hosting differential tests)")
    p_tok.set_defaults(func=_cmd_tokenize)

    p_parse = sub.add_parser("parse", help="print the parsed AST for a .my file")
    p_parse.add_argument("file")
    p_parse.add_argument("--canonical", action="store_true",
                         help="emit the stable cross-implementation AST dump "
                              "(for self-hosting differential tests)")
    p_parse.set_defaults(func=_cmd_parse)

    p_check = sub.add_parser("check", help="type-check a .my file (no run/build)")
    p_check.add_argument("file")
    p_check.add_argument("--canonical", action="store_true",
                         help="emit the stable accept/reject + diagnostic-position "
                              "line (for self-hosting differential tests)")
    add_package_flag(p_check)
    p_check.set_defaults(func=_cmd_check)


    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    # A program's strings needn't be UTF-8; the interpreter carries the stray
    # bytes as escapes, which go out as the bytes they stand for (MYLA-12).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="surrogateescape")
    try:
        return args.func(args)
    except FileNotFoundError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
