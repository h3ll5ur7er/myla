"""Burn test: writes into containers, generated (MYLA-555).

The review's generators of the H4 audit (`_gen_writes.py`, R5b's `gen_h4.py`
and `gen_loc.py`): one statement per case that writes an element (an int, a
str or a list) of a container while its index, its value or a `var self`
method called in it snapshots, grows, shrinks or replaces that container,
then prints the whole state. The containers are a struct's fields (lists,
maps, lists of lists, maps of lists, a struct, a list of structs, a
StringBuilder) or the locals of a plain function, an async function and a
lambda: about 10,000 statements in 12 programs. Interpreted, native and
`--checked` must print the same.

The suite runs a sample of each program's cases (`SAMPLE`, drawn from a
fixed seed, always with the known failures); MYLA_GENERATED=full runs them
all.
"""
from __future__ import annotations

import tempfile
import unittest

from . import _gen_writes as gen
from ._differential import THREE, check, driver, run_all, sample
from ._native import CAN_BUILD_NATIVE, SKIP_REASON, write_program

SAMPLE = 150

# C9: in `g[g.k()].push(g.v())` the interpreter runs the index first,
# native code the value first (decision 3: the place first)
_ORDER = {case: "MYLA-543" for case in ["gpush_mv_ggrow", "gpush_mvg_grepl", "gpush_mvg_gshrink", "self_gpush"]}

# the cases that fail today, per program, with the task that fixes them
KNOWN = {
    "containers_str": {
        # B2: `op=` on a string element (and `x[i] = x[i] + v()`) whose
        # value replaces the container reads the old element after it was
        # freed natively
        case: "MYLA-543" for case in [
            "gadd_kkv_grow_repl", "gadd_kkv_plain_repl", "gadd_kkv_repl_repl", "gadd_kkv_shrink_repl",
            "gadd_kkv_snap_repl", "gadd_kkv_snapgrow_repl", "gadd_v_repl", "gadd_vb_repl", "inmadd_v_repl",
            "inmadd_vb_repl", "insadd_v_repl", "insadd_vb_repl", "ladd_kv_grow_repl", "ladd_kv_plain_repl",
            "ladd_kv_repl_repl", "ladd_kv_shrink_repl", "ladd_v_repl", "ladd_vb_repl", "lplain_v_repl",
            "lplain_vb_repl", "madd_kv_grow_repl", "madd_kv_plain_repl", "madd_kv_repl_repl",
            "madd_kv_shrink_repl", "madd_v_repl", "madd_vb_repl", "mgadd_v_repl", "mgadd_vb_repl",
            "mplain_v_repl", "mplain_vb_repl"]},
    **{f"locals_{ctx}_{elt}": _ORDER for ctx in gen.CONTEXTS for elt in gen.ELEMENTS},
}


def _program(test, name: str, made) -> None:
    pre, every, _ = made(None)
    known = KNOWN.get(name, {})
    names, cases = made(sample(every, SAMPLE, name, keep=known))[1:]
    is_async = name.startswith("locals_async_")
    with tempfile.TemporaryDirectory() as tmp:
        path = write_program(tmp, driver(pre, cases, is_async), f"{name}.my")
        results = run_all(path, len(names), THREE)
    check(test, names, results, known)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class WritesIntoContainers(unittest.TestCase):
    pass


def _make(name: str, made):
    def test(self):
        _program(self, name, made)
    test.__name__ = f"test_{name}"
    return test


for _elt in gen.ELEMENTS:
    _name = f"containers_{_elt}"
    setattr(WritesIntoContainers, f"test_{_name}",
            _make(_name, lambda names, e=_elt: gen.containers_cases(e, names)))
    for _ctx in gen.CONTEXTS:
        _name = f"locals_{_ctx}_{_elt}"
        setattr(WritesIntoContainers, f"test_{_name}",
                _make(_name, lambda names, e=_elt, c=_ctx: gen.locals_cases(e, c, names)))


if __name__ == "__main__":
    unittest.main()
