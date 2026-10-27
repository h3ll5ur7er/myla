"""Burn test: the negative corpus in ``examples/errors/`` is rejected as expected.

Project convention (see README "Regression corpus"): every language feature is
exercised by a runnable example, and every *known edge case, past bug, and error*
is pinned by a program the toolchain must reject. The files in
``examples/errors/`` are those rejections.

Each file declares the diagnostic it expects with a directive comment on its own
line::

    //~ type error: cannot assign

The leading ``<lex|parse|module|type|runtime> error`` selects the pipeline stage
that must fail (lexer / parser / module loader / type-checker / interpreter),
and the trailing text is a substring the diagnostic message must contain. This
catches two kinds of regression at once: a feature that silently *stops*
rejecting bad input, and one that starts rejecting it for the *wrong* reason or
in the wrong stage.

A runtime error file also names what the native binary prints, whose message
has no values in it (MYLA-17, MYLA-58)::

    //~ native: runtime error: index out of bounds

and is built with the Python backend, which must exit with status 1 and print
exactly that line and the interpreter's position, `  --> <file>:<line>:<col>`
(MYLA-65, MYLA-66), on stderr. Module errors are checked through the loader,
with the bundled standard library.
"""
import os
import re
import unittest

from myla.errors import LexError, ModuleError, MylaRuntimeError, ParseError, TypeCheckError
from myla.interpreter import Interpreter
from myla.lexer import tokenize
from myla.loader import default_stdlib_root, link
from myla.parser import parse
from myla.types import check

from ._native import CAN_BUILD_NATIVE, build_and_run_full

ERRORS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "examples", "errors")
)

_DIRECTIVE = re.compile(r"//~\s*(lex|parse|module|type|runtime)\s+error:\s*(.*?)\s*$")
_NATIVE = re.compile(r"//~\s*native:\s*(.*?)\s*$")

# phase -> (exception class, how far to drive the pipeline)
_PHASES = {
    "lex": LexError,
    "parse": ParseError,
    "module": ModuleError,
    "type": TypeCheckError,
    "runtime": MylaRuntimeError,
}


def _drive(phase: str, source: str, path: str) -> None:
    """Run the pipeline far enough to reach `phase`; let its error escape."""
    if phase == "module":
        link(path, stdlib_root=default_stdlib_root())
        return
    tokens = tokenize(source)
    if phase == "lex":
        return
    program = parse(tokens)
    if phase == "parse":
        return
    checker = check(program)
    if phase == "type":
        return
    Interpreter(checker).run()


def _corpus() -> list[str]:
    if not os.path.isdir(ERRORS_DIR):
        return []
    return sorted(f for f in os.listdir(ERRORS_DIR) if f.endswith(".my"))


def _native(source: str) -> str | None:
    matches = [m.group(1) for line in source.splitlines() if (m := _NATIVE.match(line.strip()))]
    return matches[0] if matches else None


def _directive(source: str) -> tuple[str, str]:
    matches = [m for line in source.splitlines() if (m := _DIRECTIVE.match(line.strip()))]
    if len(matches) != 1:
        raise AssertionError(
            f"expected exactly one '//~ <phase> error: <substr>' directive, "
            f"found {len(matches)}"
        )
    return matches[0].group(1), matches[0].group(2)


class TestErrorCorpus(unittest.TestCase):
    def test_corpus_is_not_empty(self):
        self.assertTrue(_corpus(), "no negative cases found in examples/errors/")


def _make(name: str):
    def test(self):
        path = os.path.join(ERRORS_DIR, name)
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        phase, needle = _directive(source)
        exc_type = _PHASES[phase]
        with self.assertRaises(exc_type, msg=f"{name}: expected a {phase} error") as ctx:
            _drive(phase, source, path)
        if needle:
            self.assertIn(
                needle.lower(),
                str(ctx.exception).lower(),
                f"{name}: diagnostic '{ctx.exception}' should contain '{needle}'",
            )
        native = _native(source)
        if phase == "runtime":
            self.assertIsNotNone(native, f"{name}: a runtime error file needs a '//~ native:' line")
            if CAN_BUILD_NATIVE:
                checker = check(link(path, stdlib_root=default_stdlib_root()))
                out, err, code = build_and_run_full(checker, entry_path=path)
                self.assertEqual(code, 1, f"{name}: the native binary should exit 1")
                where = f"  --> {path}:{ctx.exception.line}:{ctx.exception.column}"
                self.assertEqual(err, f"{native}\n{where}\n", f"{name}: native stderr")
        else:
            self.assertIsNone(native, f"{name}: '//~ native:' only goes with a runtime error")
    return test


for _name in _corpus():
    setattr(TestErrorCorpus, f"test_{_name[:-3].replace('.', '_')}", _make(_name))


if __name__ == "__main__":
    unittest.main()
