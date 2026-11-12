"""Burn test: the standard library at extreme arguments, generated
(MYLA-555).

The review's generator (`_gen_extreme.py`, `repro-r5/std/gen.py` with
`harness.py`, D184): about 17,500 calls in five groups, each with boundary
values (0, ±1, the int32 and int64 limits, 2^30, widths, radixes, exponents,
indexes, counts and capacities out of range, digit strings past every
limit). Each case returns a text, or ends with a runtime error, and `myla
run`, a plain build and a `--checked` build must give the same: a library
function given what it can't take reports it the same way on every runner,
and never overflows in one build where it wraps in another (D184). The one
exception is std.int's arithmetic and the sums of lists and iterators,
which overflow as the operators do (D175): an `integer overflow` there in
`myla run` and `--checked` is a wrapped value in a plain build.

The suite runs `SAMPLE` cases of each group, drawn from a fixed seed and
always with the known failures, and the cases too slow to interpret
(`SLOW`) on the two builds; MYLA_GENERATED=full runs them all on all
three.
"""
from __future__ import annotations

import re
import tempfile
import unittest

from . import _gen_extreme as gen
from ._differential import CHECKED, FULL, NATIVE, THREE, check, driver, run_all, sample
from ._native import CAN_BUILD_NATIVE, SKIP_REASON, write_program

SAMPLE = 300

# how long a case may run
TIMEOUT = 20

_HUGE = r"(1073741823|1073741824|1073741825|2147483646|2147483647)"

# Cases left out of every run: they make 2^30 things or more (a string or a
# list of that many, a grid, deque, bitset, union-find or dense graph of
# that size): `out of memory` natively, under the gigabyte a run may take,
# and minutes interpreted, an answer of neither.
NEVER = [re.compile(p) for p in [
    rf"^to_(hex|binary)\(255u64,{_HUGE}\)$",
    rf"^grid\.new\((1,{_HUGE}|{_HUGE},1)\)$",
    r"^deque\.with_capacity\(107374182[34]\)$",
    rf"^(uf\.new|bitset\.fixed|bfs_dense|dijkstra_dense)\({_HUGE}[,)]",
    rf"^bitset\.of\(\[{_HUGE}\]\)",
    rf"^bitset\.(new|of\(3\))\.(insert|toggle)\({_HUGE}\)$",
    rf"^(list\.filled|pad_start|pad_end|StringBuilder)\({_HUGE}\)$",
    r"^repeat\(1073741823\)$",
    # whether 2,562,047 hours fit beside the monotonic clock's reading
    # depends on the reading: natively for the machine's first 47 minutes
    # up, on wasm32 under Node (whose clock starts elsewhere) later too
    r"^now\.add\(time\.hours\(2562047i64\)\)$",
]]

# Cases that take seconds or minutes interpreted: the suite runs them on the
# two builds only; MYLA_GENERATED=full on all three, where the interpreter
# may run out of time (they may fail then, as their known failures).
SLOW = [re.compile(p) for p in [
    # `ldexp` scales by 2^±1023 |k| / 1023 times: 2 million steps (MYLA-580)
    r"^ldexp\([^,]+,(1073741823|1073741824|1073741825|2147483646|2147483647|\(-2147483647 - 1\)"
    r"|-2147483647|-1073741824)\)$",
    # a number of 2^30 bits and more
    rf"^bigint\.shl\({_HUGE}\)$",
    # a million characters of padding, a character a step
    r"1000000\"\)$",
]]

# the cases that fail today, per group, with the task that fixes them
KNOWN: dict[str, dict] = {
    "seq": {
        # `bit_len` of a bigint shifted by 2^31 - 2 is negative in a plain
        # build and `integer overflow` checked (`mag_bitlen`)
        "bigint.shl(2147483646)": "MYLA-550",
        "bigint.shl(2147483647)": "MYLA-550",
    },
}


_OVERFLOW = re.compile(r"!! exit 1: runtime error: integer overflow\n  --> \S*/std/(int|list|iter)\.my:")


def runners_held(name: str, outs: dict[str, str]) -> list[str]:
    """The runners a case's answers are compared across: all three, but where
    `myla run` and `--checked` both end in `integer overflow` in std.int's
    arithmetic methods (`pow`, `abs`, `lcm`, …) or in a list's or an
    iterator's `sum`, which add as the operators do (D175: they wrap in a
    plain build), the plain build's answer is not held to theirs."""
    m = _OVERFLOW.search(outs.get("interpreted", ""))
    if m and outs["checked"] == outs["interpreted"] and (m.group(1) == "int" or ".sum(" in name):
        return ["interpreted", "checked"]
    return list(outs)


def _slow(label: str) -> bool:
    return any(p.search(label) for p in SLOW)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class ExtremeArguments(unittest.TestCase):
    pass


def _make(group: str):
    def test(self):
        every = [x for x in gen.driver_cases(group)[1] if not any(p.search(x) for p in NEVER)]
        known = KNOWN.get(group, {})
        slow = {x for x in every if _slow(x)}
        runs = [("", sample([x for x in every if FULL or x not in slow], SAMPLE, group, keep=set(known) - slow),
                 THREE, set(slow) if FULL else set())]
        if not FULL:
            runs.append(("slow", sorted(slow, key=every.index), [NATIVE, CHECKED], set()))
        with tempfile.TemporaryDirectory() as tmp:
            for kind, chosen, runners, may_pass in runs:
                if not chosen:
                    continue
                with self.subTest(kind or "sample"):
                    pre, names, cases = gen.driver_cases(group, chosen)
                    known_failing = {**{x: "slow interpreted" for x in may_pass}, **known}
                    path = write_program(tmp, driver(pre, cases), f"{group}{kind}.my")
                    check(self, names, run_all(path, len(names), runners, timeout=TIMEOUT), known_failing,
                          compared=runners_held, may_pass=may_pass - set(known))
    test.__name__ = f"test_{group}"
    return test


for _group in gen.GROUPS:
    setattr(ExtremeArguments, f"test_{_group}", _make(_group))


if __name__ == "__main__":
    unittest.main()
