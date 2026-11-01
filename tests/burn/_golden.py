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
`tools/`, `src/myla/std/`), which change all the time and which nobody can ask
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
        if path.startswith(_REPO + os.sep) and "/build/" not in path:
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


class NoGolden(AssertionError):
    pass


# where the files keep changing after the retirement (see the module docstring)
_CHANGING = tuple(os.path.join(_REPO, d) + os.sep for d in ("selfhost", "tools", os.path.join("src", "myla", "std")))


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
            if key not in store:
                if _changing_file(list(args) + list(kwargs.values())):
                    raise unittest.SkipTest(f"{name}: {key_obj[0]!r:.120} changed after the Python toolchain was retired")
                raise NoGolden(f"no recorded answer of the retired Python toolchain for {name}{tuple(key_obj[0])!r:.300}: "
                               "the question is new or its file changed; give the test an expectation of its own")
            return _decode(_swap(store[key], [(m, d) for d, m in marks]))
        return answer
    return wrap
