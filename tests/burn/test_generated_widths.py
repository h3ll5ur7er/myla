"""Burn test: generic code per width, generated (MYLA-555).

The review's generator (`_gen_widths.py`, `repro-r5/interp/gen.py`): generic
functions, methods of generic structs and impls, operator traits on structs,
generic enums, closures made in one generic function and called in another,
lazy iterators, trait functions without `self` and tail calls, each
instantiated with an integer width or a float width and a second type, at
the type's limits.

- The safe program of each type prints the same under `myla run`,
  `--checked` and a plain build, without a runtime error.
- Each trap statement (44 or 45 per integer type: a sum, a product, a
  negation, a division of the minimum by -1, each through another of those
  generic paths) is the runtime error `integer overflow` under `myla run`,
  the same text and exit status under `--checked`. (A plain build wraps, and
  some of the statements then never end, so it doesn't run them.)

The suite runs every safe program and `TRAPS` trap statements of each
integer type, drawn from a fixed seed; MYLA_GENERATED=full runs all of them.
"""
from __future__ import annotations

import tempfile
import unittest

from . import _gen_widths as gen
from ._differential import CHECKED, INTERPRETED, THREE, check, driver, run_all, sample
from ._native import CAN_BUILD_NATIVE, SKIP_REASON, write_program

TRAPS = 10

# the cases that fail today, per type, with the task that fixes them
KNOWN: dict[str, dict] = {}


def no_runtime_error(name: str, outs: dict[str, str]) -> str | None:
    return "a runtime error" if "!!" in outs["interpreted"] else None


def overflows(name: str, outs: dict[str, str]) -> str | None:
    return None if "integer overflow" in outs["interpreted"] else "not the runtime error `integer overflow`"


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class GenericCodePerWidth(unittest.TestCase):
    pass


def _make(ty: str):
    def test(self):
        known = KNOWN.get(ty, {})
        programs = [("safe", gen.safe_cases(ty), THREE, no_runtime_error)]
        if gen.is_int(ty):
            traps = sample(gen.trap_names(ty), TRAPS, ty, keep=known)
            programs.append(("traps", gen.trap_cases(ty, traps), [INTERPRETED, CHECKED], overflows))
        with tempfile.TemporaryDirectory() as tmp:
            for kind, (pre, names, cases), runners, valid in programs:
                with self.subTest(kind):
                    path = write_program(tmp, driver(pre, cases), f"{ty}_{kind}.my")
                    check(self, names, run_all(path, len(names), runners), known, valid)
    test.__name__ = f"test_{ty}"
    return test


for _ty in gen.TYPES:
    setattr(GenericCodePerWidth, f"test_{_ty}", _make(_ty))


if __name__ == "__main__":
    unittest.main()
