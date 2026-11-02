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
notes and positions, and the text its carets underline. A file without a
recording (new or changed since) is held to the self-hosted CLI's
diagnostics instead, read from what `myla check` (`myla run` for a runtime
error) prints; on the recorded files the two agree (checked below).
"""
import os
import re
import subprocess
import unittest

from ._golden import NoGolden, golden
from ._native import CAN_BUILD_NATIVE, build_and_run_full, check_file
from ._tools import STDLIB_ROOT, selfhost_tool

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


_HEADER = re.compile(r"^(lex|parse|module|type|runtime) error: (.*)$")
_NOTE_HEADER = re.compile(r"^(note|help): (.*)$")
_WHERE = re.compile(r"^\s*--> (.*):(\d+):(\d+)$")
_GUTTER = re.compile(r"^\s*(\d+) \| (.*)$")
_CARETS = re.compile(r"^\s*\| ( *)(\^+)")


def _rendered(text: str) -> list[dict]:
    """The diagnostics the self-hosted CLI rendered in `text`, each with its
    stage ("note" or "help" for a note), message, position and the text its
    carets underline."""
    out: list[dict] = []
    source = ""
    for line in text.split("\n"):
        m = _HEADER.match(line) or _NOTE_HEADER.match(line)
        if m:
            out.append({"stage": m.group(1), "message": m.group(2), "line": None, "column": None,
                        "underlined": None})
            continue
        if not out:
            continue
        if (w := _WHERE.match(line)) and out[-1]["line"] is None:
            out[-1]["line"], out[-1]["column"] = int(w.group(2)), int(w.group(3))
        elif g := _GUTTER.match(line):
            source = g.group(2)
        elif (c := _CARETS.match(line)) and out[-1]["underlined"] is None:
            start = len(c.group(1))
            out[-1]["underlined"] = source[start:start + len(c.group(2))]
    return out


def _selfhost_diagnostic(phase: str, path: str) -> dict | None:
    """`_diagnostic`'s answer from the self-hosted CLI: the first error of
    `myla check` (`myla run` for a runtime error), None when it is of another
    stage or there is none."""
    command = "run" if phase == "runtime" else "check"
    proc = subprocess.run([selfhost_tool("main"), command, path, "--stdlib", STDLIB_ROOT],
                          capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
    found = _rendered(proc.stderr)
    errors = [i for i, d in enumerate(found) if d["stage"] not in ("note", "help")]
    if not errors or found[errors[0]]["stage"] != phase:
        return None
    first = found[errors[0]]
    end = errors[1] if len(errors) > 1 else len(found)
    notes = found[errors[0] + 1:end]
    return {
        "message": first["message"],
        "line": first["line"],
        "column": first["column"],
        "underlined": first["underlined"],
        "notes": [(n["stage"], n["message"]) for n in notes],
        "note_underlined": [n["underlined"] for n in notes if n["line"] is not None],
        "more": [(found[i]["stage"] == phase, found[i]["message"]) for i in errors[1:]],
    }


def _expected_diagnostic(phase: str, path: str) -> dict | None:
    """The recorded diagnostic, or the self-hosted one for a file without a
    recording."""
    try:
        return _diagnostic(phase, path)
    except (NoGolden, unittest.SkipTest):
        return _selfhost_diagnostic(phase, path)


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

    @unittest.skipUnless(CAN_BUILD_NATIVE, "the self-hosted CLI needs a native build")
    def test_the_self_hosted_diagnostics_are_the_recorded_ones(self):
        # what stands in for a missing recording gives the recorded answer
        # wherever there is one (the parts the directives look at)
        compared = 0
        for name in _corpus():
            path = os.path.join(ERRORS_DIR, name)
            with open(path, encoding="utf-8") as fh:
                source = fh.read()
            phase, _ = _directive(source)
            try:
                recorded = _diagnostic(phase, path)
            except (NoGolden, unittest.SkipTest):
                continue
            with self.subTest(file=name):
                mine = _selfhost_diagnostic(phase, path)
                self.assertIsNotNone(mine)
                keys = ["message", "notes", "more"]
                if phase == "runtime":
                    keys += ["line", "column"]
                if _span(source) is not None:
                    keys.append("underlined")
                if _note_spans(source):
                    keys.append("note_underlined")
                self.assertEqual({k: mine[k] for k in keys}, {k: recorded[k] for k in keys})
                compared += 1
        self.assertGreater(compared, 150)

    @unittest.skipUnless(CAN_BUILD_NATIVE, "the self-hosted CLI needs a native build")
    def test_a_file_without_a_recording_gets_the_self_hosted_diagnostic(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "type_new_case.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("//~ type error: cannot assign\nfun main() {\n    let x = 1\n    x = 2\n}\n")
            diag = _expected_diagnostic("type", path)
            self.assertEqual((diag["message"], diag["line"], diag["underlined"]),
                             ("cannot assign to an immutable binding (declare it with 'var')", 4, "x = 2"))
            self.assertEqual(diag["notes"], [("note", "'x' is declared here")])
            self.assertIsNone(_expected_diagnostic("parse", path))


def _make(name: str):
    def test(self):
        path = os.path.join(ERRORS_DIR, name)
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        phase, needle = _directive(source)
        diag = _expected_diagnostic(phase, path)
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
