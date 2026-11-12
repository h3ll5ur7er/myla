"""Burn test: deep copies between tasks and actors, generated (MYLA-555).

The review's generator (`_gen_deep.py`, D92) makes every value shape (41:
strings, lists, maps, tuples, options, results, structs, the recursive and
mutually recursive enums, generics, closures, a StringBuilder, packed
lists of every width, and closures that capture the recursive enums) and
hands each about 60 times between tasks and actors. Each copy is checked
against a checksum: a shape passes when it counts no bad copy and every
runner prints the same checksum, interpreted, natively on the default
number of workers, on 1 and on 8, and built `--checked`. With
MYLA_TEST_TARGET set the native builds are the target's.

The suite runs 4 rounds of each shape; MYLA_GENERATED=full runs 20, the
review's size.
"""
from __future__ import annotations

import tempfile
import unittest

from . import _gen_deep as gen
from ._differential import CHECKED, FULL, INTERPRETED, NATIVE, Runner, check, driver, run_all
from ._native import CAN_BUILD_NATIVE, SKIP_REASON, write_program

ROUNDS = 20 if FULL else 4

RUNNERS = [INTERPRETED, NATIVE, Runner("1 worker", "native", {"MYLA_THREADS": "1"}),
           Runner("8 workers", "native", {"MYLA_THREADS": "8"}), CHECKED]

# the shapes that fail today, with the task that fixes them
KNOWN = {
    # B1: a closure that captures a recursive enum, deep-copied to a child
    # task, an actor or a channel, is a segmentation fault on x86-64 and
    # aarch64 (wasm32 passes)
    **{shape: {"": "MYLA-415", "aarch64-linux": "MYLA-415"}
       for shape in ["clst", "ctree", "cmutual", "hlst", "flst", "plst"]},
}


def no_bad_copy(name: str, outs: dict[str, str]) -> str | None:
    out = next(iter(outs.values()))
    return None if out.startswith(f"{name} bad=0 ") else "a copy was changed"


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class DeepCopies(unittest.TestCase):
    def test_every_shape_through_every_hand_over(self):
        names = list(gen.SH)
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, driver(gen.PRELUDE, gen.cases(names, ROUNDS), is_async=True), "deep.my")
            results = run_all(path, len(names), RUNNERS)
        check(self, names, results, KNOWN, no_bad_copy)


if __name__ == "__main__":
    unittest.main()
