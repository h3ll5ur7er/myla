"""Burn test: the negative corpus in ``examples/errors/`` is rejected as expected.

Project convention (docs/Development/Testing.md, "The error corpus"): every language feature is
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

and is built with the self-hosted compiler, which must exit with status 1 and
print exactly that line and the interpreter's position, `  --> <file>:<line>:<col>`
(MYLA-65, MYLA-66), on stderr. Module errors are checked through the loader,
with the bundled standard library, as are the type errors of a file that
imports.

A file may also pin the source text the diagnostic underlines (MYLA-65)::

    //~ span: nope(1)

The stage reports exactly one error, unless the file says how many it reports
(MYLA-65, D80), and then may name a substring of each later error's message, in
order::

    //~ errors: 3
    //~ next: expected an expression
    //~ next: unknown name

The first error's notes (MYLA-65) are named in order, each by its label and a
substring of its message, and a note's underlined text may be pinned like the
error's; a file without these directives expects no notes::

    //~ note: is declared here
    //~ note span: let n = 1
    //~ help: did you mean 'count'?

The diagnostics are the retired Python toolchain's, recorded
(`tests/burn/_golden.py`, MYLA-219): the stage that failed, its messages,
notes and positions, and the text its carets underline.
"""
import os
import re
import unittest

from ._golden import golden
from ._native import CAN_BUILD_NATIVE, build_and_run_full, check_file

ERRORS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "examples", "errors")
)

_DIRECTIVE = re.compile(r"//~\s*(lex|parse|module|type|runtime)\s+error:\s*(.*?)\s*$")
_NATIVE = re.compile(r"//~\s*native:\s*(.*?)\s*$")
_SPAN = re.compile(r"//~\s*span:\s?(.*?)$")
_COUNT = re.compile(r"//~\s*errors:\s*(\d+)\s*$")
_NEXT = re.compile(r"//~\s*next:\s*(.*?)\s*$")
_NOTE = re.compile(r"//~\s*(note|help):\s*(.*?)\s*$")
_NOTE_SPAN = re.compile(r"//~\s*note span:\s?(.*?)$")


@golden("error_corpus.diagnostic")
def _diagnostic(phase: str, path: str) -> dict | None:
    """The error of stage `phase` the Python toolchain reports for the file
    `path` (None if it reports none): its message, the text it underlines,
    its notes, its position and the errors after it."""
    from myla.ast import ImportDecl
    from myla.errors import (LexError, ModuleError, MylaRuntimeError, ParseError, TypeCheckError,
                             caret_range)
    from myla.interpreter import Interpreter
    from myla.lexer import tokenize
    from myla.loader import default_stdlib_root, link
    from myla.parser import parse
    from myla.types import check

    # phase -> exception class
    phases = {
        "lex": LexError,
        "parse": ParseError,
        "module": ModuleError,
        "type": TypeCheckError,
        "runtime": MylaRuntimeError,
    }

    def drive() -> None:
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
        if any(isinstance(d, ImportDecl) for d in program.decls):
            # a program that imports is checked as 'myla check' does, linked
            program = link(path, stdlib_root=default_stdlib_root())
        checker = check(program)
        if phase == "type":
            return
        Interpreter(checker).run()

    def underlined(err) -> str:
        """The text of the error's (or note's) line under its carets."""
        text = source.splitlines()[err.line - 1]
        start, end = caret_range(text, err.line, err.column, err.span)
        return text[start - 1:end - 1]

    with open(path, encoding="utf-8") as fh:
        source = fh.read()
    exc_type = phases[phase]
    try:
        drive()
    except exc_type as exc:
        notes = exc.notes
        placed = [n for n in notes if n.line is not None]
        return {
            "message": str(exc),
            "line": exc.line,
            "column": exc.column,
            "underlined": underlined(exc) if _span(source) is not None else None,
            "notes": [(n.label, n.message) for n in notes],
            "note_underlined": [underlined(n) for _, n in zip(_note_spans(source), placed)],
            # each later error: (of the same stage?, its text)
            "more": [(isinstance(e, exc_type), str(e)) for e in exc.more],
        }
    return None


def _corpus() -> list[str]:
    if not os.path.isdir(ERRORS_DIR):
        return []
    return sorted(f for f in os.listdir(ERRORS_DIR) if f.endswith(".my"))


def _native(source: str) -> str | None:
    matches = [m.group(1) for line in source.splitlines() if (m := _NATIVE.match(line.strip()))]
    return matches[0] if matches else None


def _span(source: str) -> str | None:
    matches = [m.group(1) for line in source.splitlines() if (m := _SPAN.match(line.strip()))]
    return matches[0] if matches else None


def _count(source: str) -> int:
    matches = [int(m.group(1)) for line in source.splitlines() if (m := _COUNT.match(line.strip()))]
    return matches[0] if matches else 1


def _nexts(source: str) -> list[str]:
    return [m.group(1) for line in source.splitlines() if (m := _NEXT.match(line.strip()))]


def _notes(source: str) -> list[tuple[str, str]]:
    return [(m.group(1), m.group(2)) for line in source.splitlines()
            if (m := _NOTE.match(line.strip()))]


def _note_spans(source: str) -> list[str]:
    return [m.group(1) for line in source.splitlines() if (m := _NOTE_SPAN.match(line.strip()))]


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
        diag = _diagnostic(phase, path)
        if diag is None:
            self.fail(f"{name}: expected a {phase} error")
        message = diag["message"]
        if needle:
            self.assertIn(
                needle.lower(),
                message.lower(),
                f"{name}: diagnostic '{message}' should contain '{needle}'",
            )
        span = _span(source)
        if span is not None:
            self.assertEqual(diag["underlined"], span, f"{name}: the underlined text")
        notes, wanted = diag["notes"], _notes(source)
        self.assertEqual([label for label, _ in notes], [label for label, _ in wanted],
                         f"{name}: the notes: {notes}")
        for (_, want), (_, got) in zip(wanted, notes):
            self.assertIn(want.lower(), got.lower(), f"{name}: a note")
        for want, got in zip(_note_spans(source), diag["note_underlined"]):
            self.assertEqual(got, want, f"{name}: the text a note underlines")
        later = diag["more"]
        self.assertEqual(1 + len(later), _count(source),
                         f"{name}: the errors reported: {[message, *(text for _, text in later)]}")
        nexts = _nexts(source)
        if nexts:
            self.assertEqual(len(nexts), len(later), f"{name}: one 'next' directive per later error")
            for want, (same_stage, text) in zip(nexts, later):
                self.assertTrue(same_stage, f"{name}: a later error of another stage")
                self.assertIn(want.lower(), text.lower(), f"{name}: a later error")
        native = _native(source)
        if phase == "runtime":
            self.assertIsNotNone(native, f"{name}: a runtime error file needs a '//~ native:' line")
            if CAN_BUILD_NATIVE:
                out, err, code = build_and_run_full(check_file(path), entry_path=path)
                self.assertEqual(code, 1, f"{name}: the native binary should exit 1")
                where = f"  --> {path}:{diag['line']}:{diag['column']}"
                self.assertEqual(err, f"{native}\n{where}\n", f"{name}: native stderr")
        else:
            self.assertIsNone(native, f"{name}: '//~ native:' only goes with a runtime error")
    return test


for _name in _corpus():
    setattr(TestErrorCorpus, f"test_{_name[:-3].replace('.', '_')}", _make(_name))


if __name__ == "__main__":
    unittest.main()
