"""The Python toolchain's answers, frozen (MYLA-219).

Until October 2026 the burn tests asked the Python toolchain (`src/myla/`,
retired by D101) what a program's tokens, tree, errors and output are, and
compared the self-hosted toolchain with it. Its answers to every question the
tests asked were recorded before it was removed, into
`tests/burn/data/golden/<name>.json.gz`; `@golden("name")` on an oracle
function answers from there.

The key of a question is the oracle's name and its arguments, a file named by
an argument standing for its content (and its path under the repository, or
its name elsewhere), so a test that asks something new, or about a changed
file, finds no answer and fails, saying so. A question about a file of the
self-hosted compiler, the tools or the standard library (`selfhost/`,
`tools/`, `lib/std/`), which change all the time and which nobody can ask
the Python toolchain about any more, is skipped instead when it has no answer:
the skip count shows how much of that corpus has changed since. A temporary
directory in an argument is replaced in the answer by a placeholder and put
back on replay.

The repository's own path in an answer is stored as a placeholder too, so a
checkout elsewhere replays with its own; in an argument (a program that names
a file of the repository) it is keyed as the checkout that recorded the
answers, `RECORDED_REPO`, saw it.

`MYLA_GOLDEN=record` (only on a checkout that still has the Python
toolchain, the branch `backup/python-toolchain-final`) computes and stores the
answers instead.
"""
from __future__ import annotations

import functools
import gzip
import hashlib
import json
import os
import threading
import unittest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_DIR = os.environ.get("MYLA_GOLDEN_DIR") or os.path.join(_REPO, "tests", "burn", "data", "golden")
RECORD = os.environ.get("MYLA_GOLDEN") == "record"
# where the answers were recorded: an argument holding the repository's path
# (a program that names a file of the repository) is keyed as it was there
RECORDED_REPO = "/home/user/myla"

# the corpus files (examples/) as the recordings saw them, kept for the gates
# that compare tokens and syntax trees, where an answer can't be moved to a
# rewritten text (MYLA-240); keyed by their paths under examples/
RECORDED_CORPUS = os.path.join(_REPO, "tests", "burn", "data", "recorded_corpus")


# The examples the recordings cover: those of the retired toolchain's last
# state (`backup/python-toolchain-final`, d94f948). An example added since
# has no recorded answer and is held to expectations of its own
# (test_examples_run, test_examples_compile), so the gates that ask the
# recordings about every example walk these (MYLA-288, MYLA-299).
RECORDED_EXAMPLES = (
    "attributes.my", "chars.my", "closures.my", "concurrency.my", "constants.my",
    "control_flow.my", "enums.my", "floats.my", "functions.my", "generic-types.my",
    "generic_traits.my", "generics.my", "hello.my", "interpolation.my", "lists.my",
    "loops.my", "maps.my", "methods.my", "operators.my", "option-result.my",
    "pipelines.my", "recursion.my", "regressions.my", "semicolons.my", "strings.my",
    "structs.my", "traits.my", "traits_on_builtins.my", "tuples.my", "types_and_aliases.my",
    "unicode.my", "variables.my",
)


def recorded_examples() -> list[str]:
    """The paths of RECORDED_EXAMPLES, sorted."""
    return [os.path.join(_REPO, "examples", n) for n in RECORDED_EXAMPLES]


def recorded(path: str) -> str:
    """The file at `path` (under the repository) as the recordings saw it:
    its copy in RECORDED_CORPUS when it was rewritten since, else itself."""
    copy = os.path.join(RECORDED_CORPUS, os.path.relpath(os.path.abspath(path), _REPO))
    return copy if os.path.exists(copy) else path


_stores: dict[str, dict] = {}
_lock = threading.Lock()


def _store(name: str) -> dict:
    with _lock:
        if name not in _stores:
            path = os.path.join(_DIR, f"{name}.json.gz")
            if os.path.exists(path):
                with gzip.open(path, "rt", encoding="utf-8") as fh:
                    _stores[name] = json.load(fh)
            else:
                _stores[name] = {}
        return _stores[name]


def save() -> None:
    """Write the recorded answers (called at exit when recording)."""
    os.makedirs(_DIR, exist_ok=True)
    with _lock:
        for name, store in _stores.items():
            # mtime 0: the same answers make the same bytes
            with open(os.path.join(_DIR, f"{name}.json.gz"), "wb") as raw, \
                    gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
                gz.write(json.dumps(store, indent=0, sort_keys=True, ensure_ascii=False).encode())


if RECORD:
    import atexit
    atexit.register(save)


def _describe(arg, dirs: list[str]):
    """An argument as it goes into the key; a file stands for its content."""
    if isinstance(arg, str) and len(arg) < 4096 and os.path.isfile(arg):
        path = os.path.abspath(arg)
        with open(path, "rb") as fh:
            data = fh.read()
        for r in {_REPO, os.path.realpath(_REPO)}:   # as the recording checkout saw it
            data = data.replace(r.encode(), RECORDED_REPO.encode())
        digest = hashlib.sha256(data).hexdigest()
        if path.startswith(RECORDED_CORPUS + os.sep):
            # a corpus file as it was recorded, before a rewrite (MYLA-240)
            where = os.path.relpath(path, RECORDED_CORPUS)
        elif path.startswith(_REPO + os.sep) and "/build/" not in path:
            where = os.path.relpath(path, _REPO)
        else:
            where = os.path.basename(path)
            for d in {os.path.dirname(path), os.path.dirname(os.path.realpath(path))}:
                if d not in dirs:
                    dirs.append(d)
        return {"file": where, "sha256": digest}
    if isinstance(arg, str):
        for r in {_REPO, os.path.realpath(_REPO)}:
            arg = arg.replace(r, RECORDED_REPO)
        return arg
    if isinstance(arg, (list, tuple)):
        return [_describe(a, dirs) for a in arg]
    if isinstance(arg, dict):
        return {k: _describe(v, dirs) for k, v in sorted(arg.items())}
    return arg


def _swap(value, pairs: list[tuple[str, str]]):
    if isinstance(value, str):
        for old, new in pairs:
            value = value.replace(old, new)
        return value
    if isinstance(value, list):
        return [_swap(v, pairs) for v in value]
    if isinstance(value, dict):
        return {k: _swap(v, pairs) for k, v in value.items()}
    return value


def _encode(value):
    if isinstance(value, tuple):
        return {"__tuple__": [_encode(v) for v in value]}
    if isinstance(value, list):
        return [_encode(v) for v in value]
    if isinstance(value, dict):
        return {k: _encode(v) for k, v in value.items()}
    return value


def _decode(value):
    if isinstance(value, dict) and set(value) == {"__tuple__"}:
        return tuple(_decode(v) for v in value["__tuple__"])
    if isinstance(value, list):
        return [_decode(v) for v in value]
    if isinstance(value, dict):
        return {k: _decode(v) for k, v in value.items()}
    return value


# MYLA_GOLDEN_TRACE=<file>: every question asked is appended to the file, its
# key and its arguments with the texts of the files they name (MYLA-240)
TRACE = os.environ.get("MYLA_GOLDEN_TRACE")


def _texts(arg):
    """An argument with each file it names replaced by its path and text."""
    if isinstance(arg, str) and len(arg) < 4096 and os.path.isfile(arg):
        with open(arg, encoding="utf-8", errors="surrogateescape") as fh:
            return {"path": os.path.abspath(arg), "text": fh.read()}
    if isinstance(arg, (list, tuple)):
        return [_texts(a) for a in arg]
    if isinstance(arg, dict):
        return {k: _texts(v) for k, v in sorted(arg.items())}
    return arg


def _trace(name: str, key: str, args: list, kwargs: dict, known: bool) -> None:
    with _lock:
        with open(TRACE, "a", encoding="utf-8", errors="surrogateescape") as fh:
            fh.write(json.dumps({"oracle": name, "key": key, "known": known, "args": _texts(args),
                                 "kwargs": _texts(kwargs)}, ensure_ascii=False) + "\n")


# -- aliases: answers for programs rewritten since the recording (MYLA-240) --
#
# When programs moved from `push(xs, v)` to `xs.push(v)` (MYLA-221, D103), a
# question about a rewritten program found no answer: keys hold the text.
# `tests/burn/golden_aliases.py` traced every question before the rewrite
# (`MYLA_GOLDEN_TRACE`), rewrote each text with `scripts/to_methods.py`, and
# stored for each changed key the original's key and the lines that changed
# (`aliases/<name>.json.gz`). The rewrite moves no line, so an answer's
# positions move only in columns on those lines: `translate` moves them, and
# puts the rewritten line where an answer shows source.

_ALIAS_DIR = os.path.join(_DIR, "aliases")
_alias_stores: dict[str, dict] = {}


def _aliases(name: str) -> dict:
    with _lock:
        if name not in _alias_stores:
            path = os.path.join(_ALIAS_DIR, f"{name}.json.gz")
            _alias_stores[name] = {}
            if os.path.exists(path):
                with gzip.open(path, "rt", encoding="utf-8") as fh:
                    _alias_stores[name] = json.load(fh)
        return _alias_stores[name]


def _column_map(cols: list):
    """1-based column on the old line -> on the new one: `cols` holds each
    old column's place, the column after the line's end too; an end (the
    column after the last character) goes to the place after its last one."""
    def move(col: int, end: bool = False) -> int:
        if end and 2 <= col <= len(cols) + 1:
            return cols[col - 2] + 1
        return cols[col - 1] if 1 <= col <= len(cols) else col
    return move


def translate(value, lines: list, oracle: str = ""):
    """`value`, an answer about original programs, for the rewritten ones:
    `lines` holds each changed line, `[label, number, old, new, cols]`
    (`label` the file's name, "" for a program given as text; `cols` each
    old column's place on the new line, from the rewrite itself)."""
    import re
    if not lines:
        return value
    by = {}
    for label, number, old, new, cols in lines:
        by[(label, number)] = (old, new, _column_map(cols))
    labels = {entry[0] for entry in lines}
    only = next(iter(labels)) if len(labels) == 1 else None

    def find(label, number):
        """The changed line `number` of the file `label` (None: the
        answer's one program, when it names none)."""
        if label is not None:
            return by.get((label, number))
        if only is not None:
            return by.get((only, number))
        return None

    def move(label, number, col, end=False):
        hit = find(label, number)
        return hit[2](col, end) if hit else col

    def text(s: str) -> str:
        out = s.split("\n")
        current = None    # (label, line) of the last "-->"
        for i, ln in enumerate(out):
            m = re.match(r"^(\s*--> )(.*?):(\d+):(\d+)$", ln)
            if m:
                label = os.path.basename(m.group(2))
                number = int(m.group(3))
                current = (label, number)
                out[i] = f"{m.group(1)}{m.group(2)}:{number}:{move(label, number, int(m.group(4)))}"
                continue
            m = re.match(r"^(\s*)(\d+) \| (.*)$", ln)
            if m and current and int(m.group(2)) == current[1]:
                hit = find(*current)
                if hit:
                    out[i] = f"{m.group(1)}{m.group(2)} | {hit[1]}"
                    # the caret line under it
                    if i + 1 < len(out):
                        c = re.match(r"^(\s*\| )( *)(\^+)$", out[i + 1])
                        if c:
                            a = len(c.group(2)) + 1
                            b = a + len(c.group(3))
                            na, nb = hit[2](a), hit[2](b, True)
                            out[i + 1] = c.group(1) + " " * (na - 1) + "^" * max(1, nb - na)
                continue
            m = re.match(r"^(err|warn|note) (\d+) (\d+) (\d+):(\d+)-(\d+):(\d+)(.*)$", ln)
            if m:
                l0, c0, sl, sc, el, ec = (int(x) for x in m.groups()[1:7])
                out[i] = (f"{m.group(1)} {l0} {move(None, l0, c0)} {sl}:{move(None, sl, sc)}-"
                          f"{el}:{move(None, el, ec, True)}{m.group(8)}")
                continue
            out[i] = re.sub(r"([^\s:'\"]+\.my):(\d+):(\d+)",
                            lambda r: f"{r.group(1)}:{r.group(2)}:{move(os.path.basename(r.group(1)), int(r.group(2)), int(r.group(3)))}",
                            ln)
        return "\n".join(out)

    def under(old_text: str, number=None) -> str:
        """An underlined piece of an old line, as the rewritten line has it."""
        for (label, n), (old, new, mv) in by.items():
            if number is not None and n != number:
                continue
            at = old.find(old_text)
            if at >= 0 and old.find(old_text, at + 1) < 0:
                a, b = mv(at + 1), mv(at + 1 + len(old_text), True)
                return new[a - 1:b - 1]
        return old_text

    def walk(v):
        if isinstance(v, str):
            return text(v)
        if isinstance(v, dict):
            d = {k: walk(x) for k, x in v.items()}
            if isinstance(v.get("line"), int) and isinstance(v.get("column"), int):
                hit = find(None, v["line"])
                if hit:
                    d["column"] = hit[2](v["column"])
                    if isinstance(v.get("underlined"), str):
                        d["underlined"] = under(v["underlined"], v["line"])
            if isinstance(v.get("note_underlined"), list):
                d["note_underlined"] = [under(u) if isinstance(u, str) else u for u in v["note_underlined"]]
            return d
        if isinstance(v, list):
            if oracle == "lsp.members":
                return [_member(x, move) for x in v]
            return [walk(x) for x in v]
        if isinstance(v, tuple):
            # (stdout, line, column) of a runtime error
            if oracle == "selfhost_codegen.runtime_error" and len(v) == 3 and isinstance(v[1], int):
                return (v[0], v[1], move(None, v[1], v[2]))
            return tuple(walk(x) for x in v)
        return v
    return walk(value)


def _member(entry, move):
    """An `lsp.members` entry: (line, col, name, kind, decl line 0-based,
    decl col 0-based or None)."""
    if not isinstance(entry, (list, tuple)) or len(entry) != 6:
        return entry
    line, col, name, kind, dl, dc = entry
    col = move(None, line, col)
    if dc is not None:
        dc = move(None, dl + 1, dc + 1) - 1
    return type(entry)((line, col, name, kind, dl, dc))


class NoGolden(AssertionError):
    pass


# where the files keep changing after the retirement (see the module docstring)
_CHANGING = tuple(os.path.join(_REPO, d) + os.sep for d in ("selfhost", "tools", os.path.join("lib", "std")))


def answer_for_file(path: str, ask):
    """`ask()`, an oracle keyed by a file's text rather than its path: when it
    has no answer for a file that keeps changing (see the module docstring),
    the question is skipped as `golden` skips it."""
    try:
        return ask()
    except NoGolden:
        if _changing_file([path]):
            raise unittest.SkipTest(f"{os.path.relpath(path, _REPO)} changed after the Python toolchain was retired")
        raise


def _changing_file(args) -> bool:
    for a in args:
        if isinstance(a, (list, tuple)) and _changing_file(a):
            return True
        if isinstance(a, str) and len(a) < 4096 and os.path.isfile(a) \
                and os.path.abspath(a).startswith(_CHANGING):
            return True
    return False


def golden(name: str):
    """An oracle function answered from the recorded answers of `name`."""
    def wrap(fn):
        @functools.wraps(fn)
        def answer(*args, **kwargs):
            dirs: list[str] = []
            key_obj = [_describe(list(args), dirs), _describe(kwargs, dirs)]
            key = hashlib.sha256(json.dumps(key_obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            store = _store(name)
            # numbered in the order the arguments name them, replaced longest
            # first; the repository's own path too, so a checkout elsewhere
            # (CI) gets its own back
            named = [(d, f"\x00DIR{i}\x00") for i, d in enumerate(dirs)]
            named += [(r, "\x00REPO\x00") for r in {_REPO, os.path.realpath(_REPO)}]
            marks = sorted(named, key=lambda m: -len(m[0]))
            if RECORD:
                value = fn(*args, **kwargs)
                store[key] = _swap(_encode(value), marks)
                return value
            if TRACE:
                _trace(name, key, list(args), kwargs, key in store or key in _aliases(name))
            if key not in store and key in _aliases(name):
                # a question about a program rewritten since the recording
                # (MYLA-240): the original's answer, its positions moved
                alias = _aliases(name)[key]
                value = _decode(_swap(store[alias["to"]], [(m, d) for d, m in marks]))
                return translate(value, alias["lines"], name)
            if key not in store:
                if _changing_file(list(args) + list(kwargs.values())):
                    raise unittest.SkipTest(f"{name}: {key_obj[0]!r:.120} changed after the Python toolchain was retired")
                raise NoGolden(f"no recorded answer of the retired Python toolchain for {name}{tuple(key_obj[0])!r:.300}: "
                               "the question is new or its file changed; give the test an expectation of its own")
            return _decode(_swap(store[key], [(m, d) for d, m in marks]))
        return answer
    return wrap
