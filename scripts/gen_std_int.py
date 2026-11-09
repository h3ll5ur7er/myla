#!/usr/bin/env python3
"""Generate lib/std/int.my, the methods of std.int on every integer width (MYLA-322).

Myla has no bound that names "an integer type", so each of the eight widths gets
its own `impl` block, written from one template here. The `#test` cases are
computed by Python's exact integers, so they check the Myla code against an
independent model of each operation.

    python3 scripts/gen_std_int.py           # writes lib/std/int.my
    python3 scripts/gen_std_int.py --check   # fails if lib/std/int.my isn't current
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "lib", "std", "int.my")


class Width:
    def __init__(self, name: str, bits: int, signed: bool) -> None:
        self.name = name
        self.bits = bits
        self.signed = signed
        self.min = -(1 << (bits - 1)) if signed else 0
        self.max = (1 << (bits - 1)) - 1 if signed else (1 << bits) - 1
        tag = ("i" if signed else "u") + str(bits)
        self.suffix = tag
        self.MIN = "MIN_" + tag.upper()
        self.MAX = "MAX_" + tag.upper()

    def fits(self, v: int) -> bool:
        return self.min <= v <= self.max

    def wrap(self, v: int) -> int:
        v &= (1 << self.bits) - 1
        if self.signed and v > self.max:
            v -= 1 << self.bits
        return v


WIDTHS = [Width("int8", 8, True), Width("int16", 16, True), Width("int32", 32, True),
          Width("int64", 64, True), Width("uint8", 8, False), Width("uint16", 16, False),
          Width("uint32", 32, False), Width("uint64", 64, False)]


# --- the model ----------------------------------------------------------------------

def trunc_div(a: int, b: int) -> int:
    q = abs(a) // abs(b)
    return q if (a < 0) == (b < 0) else -q


def trunc_rem(a: int, b: int) -> int:
    return a - b * trunc_div(a, b)


def gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return abs(a)


# --- rendering ----------------------------------------------------------------------

def lit(w: Width, v: int, receiver: bool = False) -> str:
    # The receiver carries its type's suffix: the native harness types an
    # unsuffixed literal receiver as int32.
    return f"{v}{w.suffix}" if receiver else str(v)


def opt(w: Width, v: int | None) -> str:
    return "None" if v is None else f"Some({lit(w, v)})"


def pair(w: Width, v: int, flag: bool) -> str:
    return f"({lit(w, v)}, {'true' if flag else 'false'})"


def case(w: Width, args: list[int], expected: str, label: str = "") -> str:
    parts = [lit(w, args[0], receiver=True)] + [lit(w, a) for a in args[1:]]
    line = f"    #test({', '.join(parts)})[{expected}]"
    return line + (f" // {label}" if label else "")


def named(w: Width, v: int) -> str:
    """How a case's comment names a boundary value."""
    if v == w.max:
        return "MAX"
    if v == w.min and w.signed:
        return "MIN"
    if v == w.max - 1:
        return "MAX - 1"
    if w.signed and v == w.min + 1:
        return "MIN + 1"
    return ""


def label2(w: Width, a: int, op: str, b: int) -> str:
    na, nb = named(w, a), named(w, b)
    if not na and not nb:
        return ""
    return f"{na or a} {op} {nb or b}"


# Operands, as functions of the width's (min, max). A pair whose values don't fit the
# width (a negative one for an unsigned width) is left out.
def pairs(w: Width, spec: list[tuple]) -> list[tuple[int, int]]:
    out = []
    for f in spec:
        a, b = f(w.min, w.max)
        if w.fits(a) and w.fits(b) and (a, b) not in out:
            out.append((a, b))
    return out


ADD_SPEC = [lambda lo, hi: (2, 3), lambda lo, hi: (-7, 3), lambda lo, hi: (hi, 1),
            lambda lo, hi: (hi - 1, 1), lambda lo, hi: (hi, hi), lambda lo, hi: (lo, -1),
            lambda lo, hi: (lo, hi), lambda lo, hi: (lo + 1, -1)]
SUB_SPEC = [lambda lo, hi: (5, 3), lambda lo, hi: (3, 5), lambda lo, hi: (lo, 1),
            lambda lo, hi: (lo + 1, 1), lambda lo, hi: (hi, -1), lambda lo, hi: (0, lo),
            lambda lo, hi: (-1, lo), lambda lo, hi: (hi, hi)]
MUL_SPEC = [lambda lo, hi: (6, 7), lambda lo, hi: (-6, 7), lambda lo, hi: (hi, 2),
            lambda lo, hi: (hi // 2, 2), lambda lo, hi: (lo, -1), lambda lo, hi: (lo, 1),
            lambda lo, hi: (lo // 2, 2), lambda lo, hi: (hi, -1), lambda lo, hi: (0, hi),
            lambda lo, hi: (hi, hi)]
DIV_SPEC = [lambda lo, hi: (7, 2), lambda lo, hi: (-7, 2), lambda lo, hi: (7, 0),
            lambda lo, hi: (lo, -1), lambda lo, hi: (hi, hi)]
EUCLID_SPEC = [lambda lo, hi: (7, 3), lambda lo, hi: (-7, 3), lambda lo, hi: (7, -3),
               lambda lo, hi: (-7, -3), lambda lo, hi: (6, 3), lambda lo, hi: (-6, 3),
               lambda lo, hi: (lo, -1), lambda lo, hi: (lo + 1, lo), lambda lo, hi: (hi, 10)]
GCD_SPEC = [lambda lo, hi: (12, 18), lambda lo, hi: (-12, 18), lambda lo, hi: (12, -18),
            lambda lo, hi: (0, 5), lambda lo, hi: (0, 0), lambda lo, hi: (17, 5),
            lambda lo, hi: (hi, hi - 1), lambda lo, hi: (lo, lo // 2)]
LCM_SPEC = [lambda lo, hi: (4, 6), lambda lo, hi: (-4, 6), lambda lo, hi: (0, 6),
            lambda lo, hi: (21, 6), lambda lo, hi: (hi, 1)]
MINMAX_SPEC = [lambda lo, hi: (3, 4), lambda lo, hi: (4, 3), lambda lo, hi: (-3, 2),
               lambda lo, hi: (lo, hi), lambda lo, hi: (5, 5)]
POW_SPEC = [(3, 4), (2, 0), (0, 0), (0, 3), (-2, 3), (-1, 7), (2, -1), (2, -2), (3, 40)]
UNARY = [lambda lo, hi: 5, lambda lo, hi: -5, lambda lo, hi: 0, lambda lo, hi: hi, lambda lo, hi: lo,
         lambda lo, hi: lo + 1]


def unary(w: Width) -> list[int]:
    out = []
    for f in UNARY:
        v = f(w.min, w.max)
        if w.fits(v) and v not in out:
            out.append(v)
    return out


def pow_cases(w: Width) -> list[tuple[int, int]]:
    """(base, exponent) pairs: an exponent of -1 means "the largest that fits", -2 one more."""
    out = []
    for base, e in POW_SPEC:
        if not w.fits(base):
            continue
        if e < 0:
            k = 0
            while w.fits(base ** (k + 1)):
                k += 1
            e = k if e == -1 else k + 1
        if (base, e) not in out:
            out.append((base, e))
    if w.signed:
        # (-2)^(bits-1) is the minimum: it fits, though 2^(bits-1) doesn't.
        out.append((-2, w.bits - 1))
    return out


# --- the cases of each method --------------------------------------------------------

def binary_cases(w: Width, spec, model, render, op: str) -> list[str]:
    lines = []
    for a, b in pairs(w, spec):
        lines.append(case(w, [a, b], render(w, model(w, a, b)), label2(w, a, op, b)))
    return lines


def checked_model(op):
    def f(w: Width, a: int, b: int) -> int | None:
        v = op(a, b)
        return v if v is not None and w.fits(v) else None
    return f


def add(a, b): return a + b
def sub(a, b): return a - b
def mul(a, b): return a * b


def saturate(w: Width, v: int) -> int:
    return max(w.min, min(w.max, v))


def cases_for(w: Width, method: str) -> list[str]:
    S = w.signed
    if method == "abs":
        return [case(w, [v], lit(w, w.wrap(abs(v))), "MIN, which wraps" if v == w.min else "") for v in unary(w)]
    if method == "signum":
        return [case(w, [v], lit(w, (v > 0) - (v < 0))) for v in unary(w)]
    if method in ("min", "max"):
        f = min if method == "min" else max
        return [case(w, [a, b], lit(w, f(a, b))) for a, b in pairs(w, MINMAX_SPEC)]
    if method == "clamp":
        out = []
        for v, lo, hi in [(5, 0, 10), (-5, 0, 10), (15, 0, 10), (0, 0, 0), (w.max, w.min, 3), (7, 10, 3)]:
            if not (w.fits(v) and w.fits(lo) and w.fits(hi)):
                continue
            expected = f'panic("clamp: the minimum {lo} is above the maximum {hi}")' if lo > hi \
                else lit(w, max(lo, min(hi, v)))
            out.append(case(w, [v, lo, hi], expected))
        return out
    if method in ("pow", "wrapping_pow", "checked_pow", "saturating_pow", "overflowing_pow"):
        out = []
        for base, e in pow_cases(w):
            exact = base ** e
            if method in ("pow", "wrapping_pow"):
                expected = lit(w, w.wrap(exact))
            elif method == "checked_pow":
                expected = opt(w, exact if w.fits(exact) else None)
            elif method == "saturating_pow":
                expected = lit(w, saturate(w, exact))
            else:
                expected = pair(w, w.wrap(exact), not w.fits(exact))
            label = "wraps" if not w.fits(exact) and method in ("pow", "wrapping_pow") else ""
            out.append(f"    #test({lit(w, base, receiver=True)}, {e})[{expected}]" + (f" // {label}" if label else ""))
        return out
    if method == "gcd":
        return [case(w, [a, b], lit(w, w.wrap(gcd(a, b))), "wraps" if not w.fits(gcd(a, b)) else "")
                for a, b in pairs(w, GCD_SPEC)]
    if method == "lcm":
        out = []
        for a, b in pairs(w, LCM_SPEC):
            v = 0 if a == 0 or b == 0 else abs(a * b) // gcd(a, b)
            out.append(case(w, [a, b], lit(w, v)))
        return out
    if method in ("div_euclid", "rem_euclid"):
        out = []
        for a, b in pairs(w, EUCLID_SPEC):
            if b == 0:
                continue
            r = a % abs(b)
            q = (a - r) // b
            v = w.wrap(q) if method == "div_euclid" else r
            label = "wraps, as / does" if method == "div_euclid" and not w.fits(q) else ""
            out.append(case(w, [a, b], lit(w, v), label))
        return out
    ops = {"add": (add, ADD_SPEC, "+"), "sub": (sub, SUB_SPEC, "-"), "mul": (mul, MUL_SPEC, "*")}
    for kind in ("checked", "wrapping", "saturating", "overflowing"):
        for name, (op, spec, sym) in ops.items():
            if method != f"{kind}_{name}":
                continue
            if kind == "checked":
                return binary_cases(w, spec, checked_model(op), opt, sym)
            if kind == "wrapping":
                return binary_cases(w, spec, lambda w, a, b: w.wrap(op(a, b)), lit, sym)
            if kind == "saturating":
                return binary_cases(w, spec, lambda w, a, b: saturate(w, op(a, b)), lit, sym)
            return binary_cases(w, spec, lambda w, a, b: (w.wrap(op(a, b)), not w.fits(op(a, b))),
                                lambda w, v: pair(w, *v), sym)
    if method in ("checked_div", "checked_rem"):
        # Both are None where the quotient doesn't fit, as Rust has it: MIN % -1 too.
        def model(w: Width, a: int, b: int) -> int | None:
            if b == 0 or not w.fits(trunc_div(a, b)):
                return None
            return trunc_div(a, b) if method == "checked_div" else trunc_rem(a, b)
        return binary_cases(w, DIV_SPEC, model, opt, "/" if method == "checked_div" else "%")
    if method in ("checked_neg", "wrapping_neg", "overflowing_neg", "checked_abs"):
        out = []
        for v in unary(w):
            exact = abs(v) if method == "checked_abs" else -v
            if method in ("checked_neg", "checked_abs"):
                expected = opt(w, exact if w.fits(exact) else None)
            elif method == "wrapping_neg":
                expected = lit(w, w.wrap(exact))
            else:
                expected = pair(w, w.wrap(exact), not w.fits(exact))
            out.append(case(w, [v], expected))
        return out
    if method == "mulmod":
        out = []
        for a, b, m in [(7, 8, 5), (-7, 8, 5), (7, -8, 5), (w.max, w.max, w.max - 1), (w.max, w.max, w.max),
                        (w.max - 1, w.max - 2, w.max), (w.min, w.min, w.max), (w.min, 3, 1000),
                        (3, 4, 1), (3, 4, 0), (3, 4, -5)]:
            if not (w.fits(a) and w.fits(b) and w.fits(m)):
                continue
            expected = f'panic("mulmod: the modulus must be positive, not {m}")' if m <= 0 \
                else lit(w, (a * b) % m)
            out.append(case(w, [a, b, m], expected, label3(w, a, b, m)))
        return out
    if method == "powmod":
        out = []
        p = PRIMES[w.name]
        for a, e, m in [(2, 10, 1000), (3, 0, 7), (3, 0, 1), (-2, 3, 7), (0, 0, 5), (2, p - 1, p), (w.max, w.max, p),
                        (w.max - 1, 3, w.max), (5, 0, w.max), (2, 5, 0), (2, -1, 7)]:
            if not (w.fits(a) and w.fits(e) and w.fits(m)):
                continue
            if m <= 0:
                expected = f'panic("powmod: the modulus must be positive, not {m}")'
            elif e < 0:
                expected = f'panic("powmod: the exponent must not be negative, not {e}")'
            else:
                expected = lit(w, pow(a, e, m))
            out.append(case(w, [a, e, m], expected, label3(w, a, e, m)))
        return out
    if method == "modinv":
        out = []
        p = PRIMES[w.name]
        for a, m in [(3, 7), (-3, 7), (4, 8), (0, 7), (5, 1), (10, 17), (w.max, p), (2, w.max), (3, 0), (3, -7)]:
            if not (w.fits(a) and w.fits(m)):
                continue
            if m <= 0:
                expected = f'panic("modinv: the modulus must be positive, not {m}")'
            elif gcd(a, m) != 1:
                expected = "None"
            else:
                expected = f"Some({pow(a % m, -1, m) if m > 1 else 0})"
            out.append(case(w, [a, m], expected, label2(w, a, "mod", m)))
        return out
    if method in ("count_ones", "leading_zeros", "trailing_zeros"):
        out = []
        for v in bit_values(w):
            u = v & ((1 << w.bits) - 1)
            if method == "count_ones":
                r = bin(u).count("1")
            elif method == "leading_zeros":
                r = w.bits - u.bit_length()
            else:
                r = w.bits if u == 0 else (u & -u).bit_length() - 1
            out.append(case(w, [v], str(r), named(w, v)))
        return out
    raise KeyError(method)


def bit_values(w: Width) -> list[int]:
    """The receivers of the bit methods' cases: the ends, single bits, a pattern."""
    out = []
    for v in [0, 1, 2, 0x50, 1 << (w.bits - 2), w.max, w.min, -1, w.max - 1, 0x5555 & w.max]:
        if w.fits(v) and v not in out:
            out.append(v)
    return out


def label3(w: Width, a: int, b: int, m: int) -> str:
    names = [named(w, v) for v in (a, b, m)]
    if not any(names):
        return ""
    return ", ".join(n or str(v) for n, v in zip(names, (a, b, m)))


# The largest prime each width holds: a modulus whose every residue has an inverse.
PRIMES = {"int8": 127, "int16": 32749, "int32": 2147483647, "int64": 9223372036854775783,
          "uint8": 251, "uint16": 65521, "uint32": 4294967291, "uint64": 18446744073709551557}


# --- the code of each method ---------------------------------------------------------

def methods(w: Width) -> list[tuple[str, str, str]]:
    """(name, comment, code) for each method of the width, in the order written."""
    T, MIN, MAX, S = w.name, w.MIN, w.MAX, w.signed
    narrow = w.bits < 64
    m = []

    def add_method(name: str, comment: str, code: str) -> None:
        m.append((name, comment, code))

    if S:
        add_method("abs", "The absolute value. The minimum has none that fits: its `abs` is the\n"
                   "minimum again, as `-` wraps it (`checked_abs` says so).",
                   f"fun abs(self) -> {T} {{\n    return if self < 0 {{ -self }} else {{ self }}\n}}")
        add_method("signum", "-1, 0 or 1, the sign of the number.",
                   f"fun signum(self) -> {T} {{\n    return if self > 0 {{ 1 }} else if self < 0 {{ -1 }} else {{ 0 }}\n}}")
    add_method("min", "The smaller of the two.",
               f"fun min(self, other: {T}) -> {T} {{\n    return if other < self {{ other }} else {{ self }}\n}}")
    add_method("max", "The larger of the two.",
               f"fun max(self, other: {T}) -> {T} {{\n    return if other > self {{ other }} else {{ self }}\n}}")
    add_method("clamp", "The number held to `lo` to `hi`; `lo` above `hi` is a runtime error.",
               f"fun clamp(self, lo: {T}, hi: {T}) -> {T} {{\n"
               f"    if lo > hi {{\n"
               f"        panic(f\"clamp: the minimum {{lo}} is above the maximum {{hi}}\")\n"
               f"    }}\n"
               f"    return if self < lo {{ lo }} else if self > hi {{ hi }} else {{ self }}\n}}")
    add_method("pow", "The number to the power `exp`, multiplied as `*` does: past the width\n"
               "it wraps today (D4).",
               pow_code(T, "pow", "acc * base", "base * base", f"{T}"))
    add_method("gcd", "The greatest common divisor, never negative but for a result of 2^(bits - 1),\n"
               "which wraps to the minimum (`MIN.gcd(0)`); `0.gcd(0)` is 0." if S else
               "The greatest common divisor; `0.gcd(0)` is 0.",
               f"fun gcd(self, other: {T}) -> {T} {{\n"
               f"    var a = self\n    var b = other\n"
               f"    while b != 0 {{\n        let r = a % b\n        a = b\n        b = r\n    }}\n"
               f"    return {'a.abs()' if S else 'a'}\n}}")
    add_method("lcm", "The least common multiple" + (", never negative" if S else "") +
               "; 0 if either is 0. Past the width it wraps\nas `*` does.",
               f"fun lcm(self, other: {T}) -> {T} {{\n"
               f"    if self == 0 || other == 0 {{\n        return 0\n    }}\n"
               f"    return {'(self / self.gcd(other) * other).abs()' if S else 'self / self.gcd(other) * other'}\n}}")
    if S:
        add_method("div_euclid", "The quotient of Euclidean division: the `q` with `self == q * other + r`\n"
                   "and `0 <= r < |other|`. Division by zero is a runtime error; `MIN.div_euclid(-1)`\n"
                   "wraps to `MIN`, as `/` does.",
                   f"fun div_euclid(self, other: {T}) -> {T} {{\n"
                   f"    let q = self / other\n"
                   f"    if self % other < 0 {{\n"
                   f"        return if other > 0 {{ q - 1 }} else {{ q + 1 }}\n    }}\n"
                   f"    return q\n}}")
        add_method("rem_euclid", "The remainder of Euclidean division, never negative: from 0 to\n"
                   "`|other| - 1`. Division by zero is a runtime error.",
                   f"fun rem_euclid(self, other: {T}) -> {T} {{\n"
                   f"    let r = self % other\n"
                   f"    if r < 0 {{\n"
                   f"        return if other < 0 {{ r - other }} else {{ r + other }}\n    }}\n"
                   f"    return r\n}}")
    else:
        add_method("div_euclid", "The quotient of Euclidean division; for an unsigned number `/`.",
                   f"fun div_euclid(self, other: {T}) -> {T} {{\n    return self / other\n}}")
        add_method("rem_euclid", "The remainder of Euclidean division; for an unsigned number `%`.",
                   f"fun rem_euclid(self, other: {T}) -> {T} {{\n    return self % other\n}}")

    # bits: computed on the bits as a uint64, a negative number's two's
    # complement cut to the width
    if T == "uint64":
        bits64 = "self"
    elif S and narrow:
        bits64 = f"(self as uint64) & 0x{(1 << w.bits) - 1:X}"
    else:
        bits64 = "self as uint64"
    neg_note = " (a negative number's are its two's complement's)" if S else ""
    swar = ("    // SWAR: the counts of each 2, 4 and 8 bits side by side, then the\n"
            "    // bytes' added up by a multiplication into the top byte.\n"
            "    var x = v - ((v >> 1) & 0x5555555555555555)\n"
            "    x = (x & 0x3333333333333333) + ((x >> 2) & 0x3333333333333333)\n"
            "    x = (x + (x >> 4)) & 0x0F0F0F0F0F0F0F0F\n"
            "    return ((x * 0x0101010101010101) >> 56) as int\n}")
    add_method("count_ones", f"The number of bits set{neg_note}.",
               f"fun count_ones(self) -> int {{\n"
               f"    let v: uint64 = {bits64}\n" + swar)
    steps = "".join(f"    if x >> {s} != 0 {{\n        n -= {s}\n        x = x >> {s}\n    }}\n"
                    for s in (32, 16, 8, 4, 2) if s < w.bits)
    add_method("leading_zeros", f"The number of zero bits above the highest one set: {w.bits} for 0" +
               (", 0 for a\nnegative number." if S else "."),
               f"fun leading_zeros(self) -> int {{\n"
               f"    var x: uint64 = {bits64}\n"
               f"    if x == 0 {{\n        return {w.bits}\n    }}\n"
               f"    var n = {w.bits - 1}\n" + steps +
               f"    if x >> 1 != 0 {{\n        n -= 1\n    }}\n"
               f"    return n\n}}")
    mask = f" & 0x{(1 << w.bits) - 1:X}" if narrow else ""
    add_method("trailing_zeros", f"The number of zero bits below the lowest one set: {w.bits} for 0.",
               f"fun trailing_zeros(self) -> int {{\n"
               f"    let b: uint64 = {bits64}\n"
               f"    // the bits below the lowest one set (all of them for 0), counted as\n"
               f"    // `count_ones` counts them: written out, as a method isn't inlined\n"
               f"    let v = ((b & (0 - b)) - 1){mask}\n" + swar)

    # checked
    for op, sym in (("add", "+"), ("sub", "-"), ("mul", "*")):
        add_method(f"checked_{op}", f"`self {sym} other`, or `None` if it doesn't fit.",
                   f"fun checked_{op}(self, other: {T}) -> Option<{T}> {{\n"
                   f"    return if {op}_overflows_{w.suffix}(self, other) {{ None }} else {{ Some(self {sym} other) }}\n}}")
    div_none = "other == 0 || (self == " + MIN + " && other == -1)" if S else "other == 0"
    for op, sym in (("div", "/"), ("rem", "%")):
        add_method(f"checked_{op}", f"`self {sym} other`, or `None` if `other` is 0" +
                   (" or the quotient doesn't fit\n(`MIN / -1`)." if S else "."),
                   f"fun checked_{op}(self, other: {T}) -> Option<{T}> {{\n"
                   f"    return if {div_none} {{ None }} else {{ Some(self {sym} other) }}\n}}")
    if S:
        add_method("checked_neg", "`-self`, or `None` for the minimum.",
                   f"fun checked_neg(self) -> Option<{T}> {{\n"
                   f"    return if self == {MIN} {{ None }} else {{ Some(-self) }}\n}}")
        add_method("checked_abs", "The absolute value, or `None` for the minimum.",
                   f"fun checked_abs(self) -> Option<{T}> {{\n"
                   f"    return if self == {MIN} {{ None }} else {{ Some(self.abs()) }}\n}}")
    else:
        add_method("checked_neg", "`-self`: `Some(0)` for 0, `None` for any other unsigned number.",
                   f"fun checked_neg(self) -> Option<{T}> {{\n"
                   f"    return if self == 0 {{ Some(0) }} else {{ None }}\n}}")
    add_method("checked_pow", "The number to the power `exp`, or `None` if it doesn't fit.",
               f"fun checked_pow(self, exp: uint32) -> Option<{T}> {{\n"
               f"    var base = self\n    var e = exp\n    var acc: {T} = 1\n"
               f"    while e > 0 {{\n"
               f"        if (e & 1) == 1 {{\n            acc = acc.checked_mul(base)?\n        }}\n"
               f"        e = e >> 1\n"
               f"        if e > 0 {{\n            base = base.checked_mul(base)?\n        }}\n"
               f"    }}\n    return Some(acc)\n}}")

    # wrapping: `wrapping_add`, `wrapping_sub`, `wrapping_mul` and `wrapping_neg`
    # are the language's builtin methods (D175), one instruction natively
    add_method("wrapping_pow", f"The number to the power `exp`, modulo 2^{w.bits}.",
               pow_code(T, "wrapping_pow", WRAP["mul"]("acc", "base"), WRAP["mul"]("base", "base"), T))

    # saturating
    if S:
        sat = {"add": f"if other > 0 {{ {MAX} }} else {{ {MIN} }}",
               "sub": f"if other < 0 {{ {MAX} }} else {{ {MIN} }}",
               "mul": f"if (self < 0) == (other < 0) {{ {MAX} }} else {{ {MIN} }}"}
    else:
        sat = {"add": MAX, "sub": "0", "mul": MAX}
    for op, sym in (("add", "+"), ("sub", "-"), ("mul", "*")):
        add_method(f"saturating_{op}", f"`self {sym} other`, or the bound it passes if it doesn't fit.",
                   f"fun saturating_{op}(self, other: {T}) -> {T} {{\n"
                   f"    if {op}_overflows_{w.suffix}(self, other) {{\n        return {sat[op]}\n    }}\n"
                   f"    return self {sym} other\n}}")
    sat_pow = f"if self < 0 && (exp & 1) == 1 {{ {MIN} }} else {{ {MAX} }}" if S else MAX
    add_method("saturating_pow", "The number to the power `exp`, or the bound it passes if it doesn't fit.",
               f"fun saturating_pow(self, exp: uint32) -> {T} {{\n"
               f"    return match self.checked_pow(exp) {{\n"
               f"        Some(v) => v\n        None => {sat_pow}\n    }}\n}}")

    # overflowing
    for op, sym in (("add", "+"), ("sub", "-"), ("mul", "*")):
        add_method(f"overflowing_{op}", f"`self {sym} other` modulo 2^{w.bits}, and whether it didn't fit.",
                   f"fun overflowing_{op}(self, other: {T}) -> ({T}, bool) {{\n"
                   f"    return ({WRAP[op]('self', 'other')}, {op}_overflows_{w.suffix}(self, other))\n}}")
    add_method("overflowing_neg", f"`-self` modulo 2^{w.bits}, and whether it didn't fit.",
               f"fun overflowing_neg(self) -> ({T}, bool) {{\n"
               f"    return ({WRAP['neg']('self', '')}, {'self == ' + MIN if S else 'self != 0'})\n}}")
    add_method("overflowing_pow", f"The number to the power `exp` modulo 2^{w.bits}, and whether it didn't fit.",
               f"fun overflowing_pow(self, exp: uint32) -> ({T}, bool) {{\n"
               f"    let over = match self.checked_pow(exp) {{\n"
               f"        Some(_) => false\n        None => true\n    }}\n"
               f"    return (self.wrapping_pow(exp), over)\n}}")

    # modular
    positive = f"    if m {'<=' if S else '=='} 0 {{\n        panic(f\"{{NAME}}: the modulus must be positive, not {{m}}\")\n    }}\n"
    if narrow:
        if S:
            body = f"    return ((self as int64) * (other as int64)).rem_euclid(m as int64) as {T}\n"
        else:
            body = f"    return ((self as uint64) * (other as uint64) % (m as uint64)) as {T}\n"
        mulmod_code = (f"fun mulmod(self, other: {T}, m: {T}) -> {T} {{\n" + positive.replace("{NAME}", "mulmod")
                       + body + "}")
    else:
        root = "3037000499" if S else "4294967295"
        mulmod_code = (f"fun mulmod(self, other: {T}, m: {T}) -> {T} {{\n" + positive.replace("{NAME}", "mulmod") +
                       f"    var a = self.rem_euclid(m)\n    var b = other.rem_euclid(m)\n"
                       f"    if a <= {root} && b <= {root} {{\n        return a * b % m\n    }}\n"
                       f"    // Double and add: addmod adds only below m, so nothing overflows.\n"
                       f"    var r: {T} = 0\n"
                       f"    while b > 0 {{\n"
                       f"        if (b & 1) == 1 {{\n            r = addmod_{w.suffix}(r, a, m)\n        }}\n"
                       f"        a = addmod_{w.suffix}(a, a, m)\n        b = b >> 1\n    }}\n"
                       f"    return r\n}}")
    add_method("mulmod", "`self * other` modulo `m`, from 0 to `m - 1`, computed without overflow;\n"
               "`m` must be positive.", mulmod_code)
    neg_exp = (f"    if exp < 0 {{\n        panic(f\"powmod: the exponent must not be negative, not {{exp}}\")\n    }}\n"
               if S else "")
    add_method("powmod", "The number to the power `exp` modulo `m`, from 0 to `m - 1`, computed\n"
               "without overflow; `m` must be positive" + (" and `exp` not negative." if S else "."),
               f"fun powmod(self, exp: {T}, m: {T}) -> {T} {{\n" + positive.replace("{NAME}", "powmod") + neg_exp +
               f"    var base = self.rem_euclid(m)\n    var e = exp\n    var acc: {T} = if m == 1 {{ 0 }} else {{ 1 }}\n"
               f"    while e > 0 {{\n"
               f"        if (e & 1) == 1 {{\n            acc = acc.mulmod(base, m)\n        }}\n"
               f"        e = e >> 1\n"
               f"        if e > 0 {{\n            base = base.mulmod(base, m)\n        }}\n"
               f"    }}\n    return acc\n}}")
    add_method("modinv", "The inverse modulo `m`: the `x` from 0 to `m - 1` with `self * x` ≡ 1, or\n"
               "`None` if there is none (`self` and `m` have a common divisor); `m` must be\n"
               "positive.",
               f"fun modinv(self, m: {T}) -> Option<{T}> {{\n" + positive.replace("{NAME}", "modinv") +
               f"    // Extended Euclid, the coefficients of `self` kept modulo `m`, so none\n"
               f"    // overflows: t0 * self ≡ r0 and t1 * self ≡ r1.\n"
               f"    var r0 = m\n    var r1 = self.rem_euclid(m)\n    var t0: {T} = 0\n    var t1: {T} = if m == 1 {{ 0 }} else {{ 1 }}\n"
               f"    while r1 != 0 {{\n"
               f"        let q = r0 / r1\n        let r2 = r0 % r1\n        r0 = r1\n        r1 = r2\n"
               f"        let qt = q.mulmod(t1, m)\n"
               f"        let t2 = if t0 >= qt {{ t0 - qt }} else {{ m - (qt - t0) }}\n"
               f"        t0 = t1\n        t1 = t2\n    }}\n"
               f"    return if r0 == 1 {{ Some(t0) }} else {{ None }}\n}}")
    return m


# The wrapping operations as the generated code writes them: the builtin
# methods (D175).
WRAP = {
    "add": lambda a, b: f"{a} + {b}",
    "sub": lambda a, b: f"{a} - {b}",
    "mul": lambda a, b: f"{a} * {b}",
    "neg": lambda a, b: f"0 - {a}",
}


def pow_code(T: str, name: str, mul_acc: str, mul_base: str, ty: str) -> str:
    return (f"fun {name}(self, exp: uint32) -> {T} {{\n"
            f"    var base = self\n    var e = exp\n    var acc: {ty} = 1\n"
            f"    while e > 0 {{\n"
            f"        if (e & 1) == 1 {{\n            acc = {mul_acc}\n        }}\n"
            f"        e = e >> 1\n"
            f"        if e > 0 {{\n            base = {mul_base}\n        }}\n"
            f"    }}\n    return acc\n}}")


def helpers(w: Width) -> str:
    T, MIN, MAX, s = w.name, w.MIN, w.MAX, w.suffix
    out = [f"const {MIN}: {T} = {w.min}", f"const {MAX}: {T} = {w.max}", ""]
    if w.signed:
        out += [f"fun add_overflows_{s}(a: {T}, b: {T}) -> bool {{",
                f"    return if b > 0 {{ a > {MAX} - b }} else {{ a < {MIN} - b }}", "}", "",
                f"fun sub_overflows_{s}(a: {T}, b: {T}) -> bool {{",
                f"    return if b < 0 {{ a > {MAX} + b }} else {{ a < {MIN} + b }}", "}", ""]
        if w.bits < 64:
            out += [f"fun mul_overflows_{s}(a: {T}, b: {T}) -> bool {{",
                    "    let p = (a as int64) * (b as int64)",
                    f"    return p < ({MIN} as int64) || p > ({MAX} as int64)", "}", ""]
        else:
            out += [f"fun mul_overflows_{s}(a: {T}, b: {T}) -> bool {{",
                    "    // By division (CERT INT32-C), as no wider type holds the product.",
                    "    if a > 0 {",
                    f"        return if b > 0 {{ a > {MAX} / b }} else {{ b < {MIN} / a }}", "    }",
                    "    if b > 0 {", f"        return a < {MIN} / b", "    }",
                    f"    return a != 0 && b < {MAX} / a", "}", ""]
    else:
        out += [f"fun add_overflows_{s}(a: {T}, b: {T}) -> bool {{", f"    return a > {MAX} - b", "}", "",
                f"fun sub_overflows_{s}(a: {T}, b: {T}) -> bool {{", "    return a < b", "}", ""]
        if w.bits < 64:
            out += [f"fun mul_overflows_{s}(a: {T}, b: {T}) -> bool {{",
                    f"    return (a as uint64) * (b as uint64) > ({MAX} as uint64)", "}", ""]
        else:
            out += [f"fun mul_overflows_{s}(a: {T}, b: {T}) -> bool {{",
                    f"    return b != 0 && a > {MAX} / b", "}", ""]
    if w.bits == 64:
        out += [f"// `(x + y) % m` for x and y from 0 to m - 1, without overflow.",
                f"fun addmod_{s}(x: {T}, y: {T}, m: {T}) -> {T} {{",
                "    return if x >= m - y { x - (m - y) } else { x + y }", "}", ""]
    return "\n".join(out)


HEADER = """\
// std.int: methods on every integer width (MYLA-322, D164).
//
// GENERATED by scripts/gen_std_int.py: change that and run it, don't edit this
// file. Each width, int8 to int64 and uint8 to uint64, has its own `impl` with
// the same methods (`int` is `int32`); the cases are computed by the
// generator's exact integers.
//
// - `abs` and `signum` (signed widths), `min`, `max`, `clamp`, `pow`, `gcd`,
//   `lcm`, `div_euclid` and `rem_euclid` (never negative);
// - `count_ones`, `leading_zeros` and `trailing_zeros`, of the bits;
// - `checked_*` (an `Option`), `wrapping_*`, `saturating_*` and
//   `overflowing_*` (the result and whether it overflowed) of add, sub, mul and
//   pow, `checked_div`, `checked_rem`, `checked_neg`, `checked_abs`,
//   `wrapping_neg` and `overflowing_neg`;
// - `mulmod`, `powmod` and `modinv`, computed without overflow at every width.
//
// The plain methods (`pow`, `abs`, `lcm`) overflow as the operators do,
// wrapping today (D4). The `wrapping_*` methods are the one place that relies on
// the operators wrapping: if MYLA-311 makes them trap, those methods change and
// the rest stays, since the checked, saturating and overflowing ones decide
// overflow before they compute, by comparisons that can't overflow.
//
// Imported into every program by MYLA-320; until then, `import std.int`.
// It imports nothing.
"""


def generate(stub: bool = False) -> str:
    parts = [HEADER]
    for w in WIDTHS:
        parts.append(f"\nimpl {w.name} {{")
        first = True
        for name, comment, code in methods(w):
            if not first:
                parts.append("")
            first = False
            for line in comment.split("\n"):
                parts.append(f"    // {line}")
            parts.extend(cases_for(w, name))
            if stub:
                code = code.split("{\n", 1)[0] + "{\n    panic(\"todo\")\n}"
            for line in code.split("\n"):
                parts.append(f"    {line}" if line else "")
        parts.append("}")
    parts.append("\n// --- the overflow tests and the constants, per width " + "-" * 25 + "\n")
    for w in WIDTHS:
        parts.append(helpers(w))
    parts.append(PROPERTIES)
    return "\n".join(parts).rstrip() + "\n"


PROPERTIES = """\
// --- test functions -----------------------------------------------------------

// Fermat's little theorem and the inverses, at the largest 64-bit primes,
// where every product of two residues overflows 64 bits.
#test
fun modular_at_64_bits() {
    let p: int64 = 9223372036854775783
    let q: uint64 = 18446744073709551557
    var a: int64 = 2
    var b: uint64 = 2
    var i = 0
    while i < 20 {
        holds(a.powmod(p - 1, p) == 1, "a^(p-1) mod p, int64")
        holds(b.powmod(q - 1, q) == 1, "b^(q-1) mod q, uint64")
        match a.modinv(p) {
            Some(x) => holds(a.mulmod(x, p) == 1, "a * a^-1 mod p, int64")
            None => holds(false, "no inverse modulo a prime, int64")
        }
        match b.modinv(q) {
            Some(x) => holds(b.mulmod(x, q) == 1, "b * b^-1 mod q, uint64")
            None => holds(false, "no inverse modulo a prime, uint64")
        }
        a = a.mulmod(a, p) + 1
        b = b.mulmod(b, q) + 1
        i += 1
    }
}

// The four kinds of an operation agree, over boundary values of int64.
#test
fun kinds_agree() {
    let vs: [int64] = [0, 1, -1, 2, -2, 3037000499, -3037000500, 4611686018427387904,
        9223372036854775807, -9223372036854775807, -9223372036854775807 - 1]
    for a in vs {
        for b in vs {
            let (s, over) = a.overflowing_add(b)
            holds(s == a + b, "overflowing_add's value")
            match a.checked_add(b) {
                Some(v) => holds(!over && v == s && a.saturating_add(b) == s, "add fits")
                None => holds(over && a.saturating_add(b) == (if b > 0 { MAX_I64 } else { MIN_I64 }), "add overflows")
            }
            let (p, mover) = a.overflowing_mul(b)
            holds(p == a * b, "overflowing_mul's value")
            match a.checked_mul(b) {
                Some(v) => holds(!mover && v == p && a.saturating_mul(b) == p, "mul fits")
                None => holds(mover && a.saturating_mul(b) == (if (a < 0) == (b < 0) { MAX_I64 } else { MIN_I64 }), "mul overflows")
            }
            if b != 0 {
                let r = a.rem_euclid(b)
                holds(r >= 0 && (r < b || r < -b || b == -9223372036854775807 - 1), "rem_euclid's range")
                holds(a.div_euclid(b) * b + r == a, "q * b + r")
            }
        }
    }
}

// The test functions' assertion: `assert(ok, f"…")` doesn't compile
// natively yet (an IR verifier error on the f-string message), a function
// call with one does.
fun holds(ok: bool, what: str) {
    if !ok {
        panic(what)
    }
}
"""


def main() -> int:
    text = generate(stub="--stub" in sys.argv)
    if "--check" in sys.argv:
        with open(OUT, encoding="utf-8") as fh:
            if fh.read() != text:
                print(f"{OUT} is not current: run python3 scripts/gen_std_int.py", file=sys.stderr)
                return 1
        return 0
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
