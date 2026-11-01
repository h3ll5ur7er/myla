#!/usr/bin/env python3
"""harvest_unit_programs.py: keep the programs the unit tests ran (MYLA-219).

The unit tests of the Python toolchain run hundreds of small Myla programs
through its interpreter and assert what they print. Before the Python
toolchain is removed, this runs the unit suite once with a hook on the
interpreter and writes every single-module program it ran, with its command
line and what came out (stdout, exit status, or the runtime error), to
`tests/burn/data/unit_programs.json`; `tests/burn/test_unit_programs.py` runs
them in the self-hosted interpreter and natively.

Run it on a checkout that still has the Python toolchain (the branch
`backup/python-toolchain-final`).
"""
from __future__ import annotations

import io
import json
import os
import sys
import threading
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "src"))   # first: myla.py in REPO would shadow the package

import myla.interpreter as interp_mod   # noqa: E402
import myla.lexer as lexer_mod          # noqa: E402
from myla.errors import MylaRuntimeError  # noqa: E402

OUT = os.path.join(REPO, "tests", "burn", "data", "unit_programs.json")

_last = threading.local()
_programs: dict[str, dict] = {}


def main() -> int:
    orig_tokenize = lexer_mod.tokenize
    orig_init = interp_mod.Interpreter.__init__
    orig_run = interp_mod.Interpreter.run

    from myla.types import _PRELUDE_SRC

    def tokenize(source, *a, **k):
        if source != _PRELUDE_SRC:      # the checker tokenizes its prelude itself
            _last.source = source
        return orig_tokenize(source, *a, **k)

    def init(self, checker, out=None, err=None, argv=None, stdin=None):
        orig_init(self, checker, out, err, argv, stdin)
        linked = any(getattr(d, "source_path", None) for d in checker.program.decls)
        self._harvest = None if linked or stdin is not None else {
            "source": getattr(_last, "source", None), "argv": list(argv) if argv else None,
            "out": out, "err": err}

    def run(self):
        h = getattr(self, "_harvest", None)
        try:
            code = orig_run(self)
        except MylaRuntimeError as e:
            if h and h["source"] is not None and isinstance(h["out"], io.StringIO):
                _keep(h, {"stdout": h["out"].getvalue(), "runtime_error": e.message})
            raise
        if h and h["source"] is not None and isinstance(h["out"], io.StringIO):
            _keep(h, {"stdout": h["out"].getvalue(), "exit": code})
        return code

    # every module that imported the names directly sees the hooks too
    lexer_mod.tokenize = tokenize
    for mod in list(sys.modules.values()):
        if getattr(mod, "tokenize", None) is orig_tokenize:
            mod.tokenize = tokenize
    interp_mod.Interpreter.__init__ = init
    interp_mod.Interpreter.run = run

    suite = unittest.defaultTestLoader.discover(os.path.join(REPO, "tests", "unit"), top_level_dir=REPO)
    for mod in list(sys.modules.values()):    # test modules imported tokenize by name
        if getattr(mod, "tokenize", None) is orig_tokenize:
            mod.tokenize = tokenize
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(sorted(_programs.values(), key=lambda p: (p["source"], json.dumps(p["argv"]))),
                  fh, indent=1, ensure_ascii=False)
    print(f"{result.testsRun} unit tests ({len(result.failures) + len(result.errors)} failed); "
          f"{len(_programs)} programs written to {os.path.relpath(OUT, REPO)}")
    return 0


def _keep(h: dict, outcome: dict) -> None:
    key = json.dumps([h["source"], h["argv"]])
    if key not in _programs:
        _programs[key] = {"source": h["source"], "argv": h["argv"], **outcome}


if __name__ == "__main__":
    sys.exit(main())
