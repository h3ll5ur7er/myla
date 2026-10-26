"""Type representations and the static type checker for Myla v0.0.

The checker (docs/architecture.md §5) runs after parsing and before
interpretation/compilation. It:

- builds global tables of structs, functions, and type aliases (order
  independent), resolving the built-in `int` = `int32` alias and user
  `typealias` declarations (with cycle detection);
- validates the `#main` / `#test` attributes;
- type-checks every function body, annotating each value expression with a
  `resolved_type` attribute that the interpreter and compiler rely on.

Integer literals are "flexible": an unsuffixed literal adopts the type required
by its context (annotation, parameter, return, or the other operand of a binary
op), defaulting to `int` (`int32`).
"""
from __future__ import annotations

import copy
import dataclasses
import math
import struct
from dataclasses import dataclass

from . import ast
from .errors import TypeCheckError, in_file


# --- type representations --------------------------------------------------


class Type:
    pass


@dataclass(frozen=True)
class IntType(Type):
    width: int   # 8, 16, 32, 64
    signed: bool


@dataclass(frozen=True)
class FloatType(Type):
    width: int   # 32 or 64 (IEEE-754 single / double)


@dataclass(frozen=True)
class CharType(Type):
    """A Unicode scalar value (D25): a 32-bit codepoint distinct from the integer
    types. Char literals default to `char` but an ASCII literal stays flexible to
    the integer types so byte comparisons like `s[i] == 'a'` keep working (D42)."""
    pass


@dataclass(frozen=True)
class BoolType(Type):
    pass


@dataclass(frozen=True)
class StrType(Type):
    pass


@dataclass(frozen=True)
class StringBuilderType(Type):
    """A `StringBuilder` (D41): a mutable, growable, reference-counted byte buffer
    with copy-on-write value semantics. Used to assemble strings in a loop
    without the quadratic cost of repeated `+`. `build(sb)` snapshots it as an
    immutable `str`."""
    pass


@dataclass(frozen=True)
class StructType(Type):
    name: str
    args: tuple[Type, ...] = ()   # type arguments for a generic instantiation


@dataclass(frozen=True)
class TupleType(Type):
    elems: tuple[Type, ...]


@dataclass(frozen=True)
class ListType(Type):
    """A list `[T]` (D39): a reference-counted, copy-on-write heap sequence with
    value semantics. `elem` is the element type."""
    elem: Type


@dataclass(frozen=True)
class MapType(Type):
    """A map `[K: V]` (D39): a reference-counted, copy-on-write hash table with
    value semantics. `key` must be a primitive comparable type (D37)."""
    key: Type
    value: Type


@dataclass(frozen=True)
class EnumType(Type):
    name: str
    args: tuple[Type, ...] = ()   # type arguments for a generic instantiation


@dataclass(frozen=True)
class FuncType(Type):
    """A function value type `(T0, T1, …) -> R` (v0.4.2, D48/D49).

    `params` are the parameter types and `ret` the result (None for a void
    result). At runtime a function value is a 16-byte fat value
    `(code_ptr, env_ptr)`; the type itself carries no capture information (a
    closure and a plain `fun` reference share one type and calling convention).
    """
    params: tuple[Type, ...]
    ret: Type | None = None


@dataclass(frozen=True)
class TypeParam(Type):
    """A generic type parameter (`T`) inside a generic declaration's body.

    It is opaque: the only operations allowed on a `T` value are the ones that
    work for any type (bind, pass, store, return, pattern-bind). Concrete
    instances are produced by monomorphization (D13); the interpreter erases it.
    """
    name: str


@dataclass(frozen=True)
class SelfType(Type):
    """The `Self` type inside a `trait` signature (v0.4.4): a placeholder for the
    implementing type. Substituted by the concrete target when checking an
    `impl Trait for T` for conformance; never appears in a checked value."""
    pass


BOOL = BoolType()
STR = StrType()
STRING_BUILDER = StringBuilderType()
SELF = SelfType()

# primitive type-name keyword -> Type
_PRIMITIVES: dict[str, Type] = {
    "bool": BOOL,
    "str": STR,
    "StringBuilder": STRING_BUILDER,
    "int8": IntType(8, True),
    "int16": IntType(16, True),
    "int32": IntType(32, True),
    "int64": IntType(64, True),
    "uint8": IntType(8, False),
    "uint16": IntType(16, False),
    "uint32": IntType(32, False),
    "uint64": IntType(64, False),
    "float32": FloatType(32),
    "float64": FloatType(64),
    "char": CharType(),
}

# integer literal suffix -> Type
_SUFFIX_TYPES: dict[str, Type] = {
    "i8": IntType(8, True), "i16": IntType(16, True),
    "i32": IntType(32, True), "i64": IntType(64, True),
    "u8": IntType(8, False), "u16": IntType(16, False),
    "u32": IntType(32, False), "u64": IntType(64, False),
}

# float literal suffix -> Type
_FLOAT_SUFFIX_TYPES: dict[str, Type] = {
    "f32": FloatType(32), "f64": FloatType(64),
}

INT = IntType(32, True)  # what `int` aliases
BYTE = IntType(8, False)  # `uint8`: the element type of byte indexing `s[i]`
FLOAT = FloatType(32)  # what `float` aliases (D19/D56)
CHAR = CharType()  # the Unicode-scalar `char` type (D25)


def type_name(t: Type | None) -> str:
    if t is None:
        return "()"
    if isinstance(t, IntType):
        return f"{'int' if t.signed else 'uint'}{t.width}"
    if isinstance(t, FloatType):
        return f"float{t.width}"
    if isinstance(t, CharType):
        return "char"
    if isinstance(t, BoolType):
        return "bool"
    if isinstance(t, StrType):
        return "str"
    if isinstance(t, StringBuilderType):
        return "StringBuilder"
    if isinstance(t, (StructType, EnumType)):
        if t.args:
            return f"{t.name}<{', '.join(type_name(a) for a in t.args)}>"
        return t.name
    if isinstance(t, TypeParam):
        return t.name
    if isinstance(t, SelfType):
        return "Self"
    if isinstance(t, TupleType):
        if len(t.elems) == 1:
            return f"({type_name(t.elems[0])},)"
        return "(" + ", ".join(type_name(e) for e in t.elems) + ")"
    if isinstance(t, ListType):
        return f"[{type_name(t.elem)}]"
    if isinstance(t, MapType):
        return f"[{type_name(t.key)}: {type_name(t.value)}]"
    if isinstance(t, FuncType):
        params = ", ".join(type_name(p) for p in t.params)
        return f"({params}) -> {type_name(t.ret)}"
    return str(t)


def _type_to_typeexpr(t: Type | None) -> "ast.TypeExpr":
    """Render a resolved `Type` back as a source-level type annotation.

    Used to give checker-synthesized lambdas (`>>` composition, `_` partial
    application) self-describing parameter annotations, so the monomorphizer's
    re-check resolves them without relying on contextual hints (the expected
    type that was available during the first check is gone by then)."""
    if isinstance(t, (IntType, FloatType, CharType, BoolType, StrType,
                      StringBuilderType)):
        return ast.TypeRef(type_name(t))
    if isinstance(t, ListType):
        return ast.ListTypeRef(_type_to_typeexpr(t.elem))
    if isinstance(t, MapType):
        return ast.MapTypeRef(_type_to_typeexpr(t.key), _type_to_typeexpr(t.value))
    if isinstance(t, TupleType):
        return ast.TupleTypeRef([_type_to_typeexpr(e) for e in t.elems])
    if isinstance(t, FuncType):
        return ast.FnTypeRef(
            [_type_to_typeexpr(p) for p in t.params],
            _type_to_typeexpr(t.ret) if t.ret is not None else None,
        )
    if isinstance(t, (StructType, EnumType)):
        return ast.TypeRef(t.name, [_type_to_typeexpr(a) for a in t.args])
    if isinstance(t, TypeParam):
        return ast.TypeRef(t.name)
    raise TypeCheckError(
        f"cannot render type '{type_name(t)}' as an annotation", 0, 0
    )


# The built-in operator traits (D52, X8) and the operators that desugar to each.
# Arithmetic operators map to a same-typed method returning `Self`; `Eq`/`Ord`
# back the comparison operators.
_ARITH_OP_TRAITS: dict[str, tuple[str, str]] = {
    "+": ("Add", "add"),
    "-": ("Sub", "sub"),
    "*": ("Mul", "mul"),
    "/": ("Div", "div"),
    "%": ("Rem", "rem"),
}
_BUILTIN_OP_TRAIT_NAMES = frozenset(
    {"Add", "Sub", "Mul", "Div", "Rem", "Eq", "Ord"}
)


def _primitive_default_trait(t: Type, trait: str) -> bool:
    """Whether primitive type `t` ships an *implicit default* impl of operator
    `trait` (D52) — the hardwired v0.0–v0.3 semantics that a user `impl` may
    override. Integers get the full arithmetic/compare set; `bool` and `str`
    get equality (and `str` gets `Add` for concatenation)."""
    if isinstance(t, (IntType, FloatType)):
        return trait in ("Add", "Sub", "Mul", "Div", "Rem", "Eq", "Ord")
    if isinstance(t, CharType):
        return trait in ("Eq", "Ord")   # chars compare; no arithmetic (cast to int)
    if isinstance(t, BoolType):
        return trait == "Eq"
    if isinstance(t, StrType):
        return trait in ("Add", "Eq")
    return False


def _is_map_key(t: Type) -> bool:
    """Whether `t` is a valid map key: a primitive comparable type — an integer
    type (incl. the byte `uint8`), `char`, `bool`, or `str` (D37)."""
    return isinstance(t, (IntType, CharType, BoolType, StrType))


def int_fits(value: int, t: IntType) -> bool:
    """Whether a non-negative literal magnitude fits `t`.

    For signed types we permit the magnitude up to 2**(width-1) so that a
    negated literal like `-128i8` is accepted (the unary minus is a separate
    node). This is intentionally permissive, matching the wrapping semantics.
    """
    if t.signed:
        return 0 <= value <= (1 << (t.width - 1))
    return 0 <= value <= (1 << t.width) - 1


def _const_int(expr: ast.Expr) -> int | None:
    """A constant integer value for compile-time checks, or None if not constant.

    Recognises plain integer literals and negated integer literals; everything
    else is treated as non-constant (checked at runtime instead).
    """
    if isinstance(expr, ast.IntLit):
        return expr.value
    if (isinstance(expr, ast.Unary) and expr.op == "-"
            and isinstance(expr.operand, ast.IntLit)):
        return -expr.operand.value
    return None


def _wrap_int(value: int, t: Type) -> int:
    """Wrap `value` into the range of integer type `t` (two's complement)."""
    if not isinstance(t, IntType):
        return value
    m = value & ((1 << t.width) - 1)
    if t.signed and (m >> (t.width - 1)) & 1:
        m -= 1 << t.width
    return m


def _const_idiv(a: int, b: int) -> int:
    """Integer division truncated toward zero (matches the interpreter)."""
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def round_float(value: float, t: Type) -> float:
    """Round `value` to the precision of float type `t`.

    Python floats are IEEE-754 `float64`; for `float32` we narrow to single
    precision (round to nearest) so the interpreter and native backend agree —
    the float analogue of integer `_wrap_int` (D56 parity discipline)."""
    if isinstance(t, FloatType) and t.width == 32:
        return struct.unpack("f", struct.pack("f", value))[0]
    return value


def float_to_int(value: float, t: IntType) -> int:
    """`value as t` for a float: truncate toward zero and clamp to the range
    of `t`; NaN gives 0 (D59). Both native backends emit the same clamps."""
    if value != value:
        return 0
    lo = -(1 << (t.width - 1)) if t.signed else 0
    hi = (1 << (t.width - 1 if t.signed else t.width)) - 1
    if value <= lo:
        return lo
    if value >= hi:
        return hi
    return int(value)


def float_div(a: float, b: float) -> float:
    """IEEE-754 division: by zero yields ±inf (or NaN for 0/0), never traps."""
    if b == 0.0:
        if a == 0.0 or a != a:
            return float("nan")
        return math.copysign(math.inf, a) * math.copysign(1.0, b)
    return a / b


def float_rem(a: float, b: float) -> float:
    """IEEE-754 remainder (`fmod`): an undefined remainder yields NaN."""
    if b == 0.0 or a in (math.inf, -math.inf):
        return float("nan")
    return math.fmod(a, b)


# Float formatting (D56). Myla renders a float as round-trippable *plain decimal*
# (no scientific notation): the magnitude is scaled to a P-significant-digit
# integer (P = 9 for `float32`, 17 for `float64` — the round-trip digit counts),
# trailing zeros are trimmed, and the digits are laid out positionally.
#
# A 17-digit integer exceeds 2**53, so a single f64 multiply cannot carry it; the
# scaling therefore uses double-double (two-double) extended precision — Dekker's
# `two_prod` plus a high/low power-of-ten table. The algorithm uses
# only f64 +,-,* (identical IEEE ops in CPython and SSE2), int64, and a shared
# constant table, so the interpreter and the native x86-64 backend (which emits
# the *same* table and instruction sequence) produce byte-identical output.
_FF_MINK = -323
_FF_MAXK = 308
_FF_SPLIT = 134217729.0   # 2**27 + 1, Dekker's splitting constant
_FF_BIG = 2.0 ** 996      # above this, _FF_SPLIT * x overflows (see _ff_two_prod)
_FF_UP = 2.0 ** 64
_FF_DOWN = 2.0 ** -64


def _ff_build_pow10_dd() -> list[tuple[float, float]]:
    from decimal import Decimal, getcontext
    getcontext().prec = 80
    table: list[tuple[float, float]] = []
    for k in range(_FF_MINK, _FF_MAXK + 1):
        hi = float(f"1e{k}")
        lo = float(Decimal(10) ** k - Decimal(hi))
        table.append((hi, lo))
    return table


# (hi, lo) for 10**k, k in [_FF_MINK, _FF_MAXK]; `hi` alone is the plain f64 table.
_FF_POW10_DD = _ff_build_pow10_dd()


def _ff_pow10_hi(k: int) -> float:
    return _FF_POW10_DD[k - _FF_MINK][0]


def _ff_two_prod(a: float, b: float) -> tuple[float, float]:
    """Dekker's exact product: returns (p, e) with p + e == a*b exactly.

    Splitting an operand above 2**996 would overflow (`_FF_SPLIT * a`), so such
    an operand is scaled down by 2**64 and the other one up by 2**64 first:
    both scalings are exact, the other operand is tiny (the products here are
    about 10**17), and the product is unchanged (MYLA-29)."""
    if a > _FF_BIG:
        a = a * _FF_DOWN
        b = b * _FF_UP
    elif b > _FF_BIG:
        a = a * _FF_UP
        b = b * _FF_DOWN
    p = a * b
    ca = _FF_SPLIT * a
    ahi = ca - (ca - a)
    alo = a - ahi
    cb = _FF_SPLIT * b
    bhi = cb - (cb - b)
    blo = b - bhi
    e = ((ahi * bhi - p) + ahi * blo + alo * bhi) + alo * blo
    return p, e


def _ff_llrint(x: float) -> int:
    """Round to nearest int64, ties to even (matches SSE `cvtsd2si`)."""
    if x != x or x in (math.inf, -math.inf):
        return 0
    return int(round(x))


def _ff_scaled_int(m: float, idx: int) -> int:
    """round(m * 10**idx) as an exact integer, via double-double scaling."""
    e1 = 0.0
    if idx > _FF_MAXK:
        # Tiny magnitudes: 10**idx isn't a double, so scale by 10**200 first and
        # carry the result as a double-double (m, e1) into the second step
        # (collapsing it to one double lost the last digit, MYLA-29).
        hi, lo = _FF_POW10_DD[200 - _FF_MINK]
        p, e = _ff_two_prod(m, hi)
        m, e1 = p, e + m * lo
        idx -= 200
    hi, lo = _FF_POW10_DD[idx - _FF_MINK]
    p, e = _ff_two_prod(m, hi)
    e = e + m * lo + e1 * hi
    return _ff_llrint(p) + _ff_llrint(e)


def _ff_positional(digits: str, e10: int) -> str:
    """Lay `digits` out in positional decimal; the leading digit has place
    value `10**e10`."""
    n = len(digits)
    if e10 >= n - 1:
        return digits + "0" * (e10 - (n - 1))   # integer with trailing zeros
    if e10 >= 0:
        return digits[:e10 + 1] + "." + digits[e10 + 1:]
    return "0." + "0" * (-e10 - 1) + digits


def format_float(value: float, t: Type) -> str:
    """Render a float as Myla's canonical round-trippable decimal text (D56)."""
    if value != value:
        return "nan"
    if value == math.inf:
        return "inf"
    if value == -math.inf:
        return "-inf"
    neg = math.copysign(1.0, value) < 0.0
    sign = "-" if neg else ""
    m = -value if neg else value
    if m == 0.0:
        return sign + "0"
    width = 32 if (isinstance(t, FloatType) and t.width == 32) else 64
    P = 9 if width == 32 else 17
    # e10 = the largest exponent with 10**e10 <= m (binary search the table).
    lo, hi, e10 = _FF_MINK, _FF_MAXK, _FF_MINK - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if _ff_pow10_hi(mid) <= m:
            e10 = mid
            lo = mid + 1
        else:
            hi = mid - 1
    idx = (P - 1) - e10
    d = _ff_scaled_int(m, idx)
    if d >= 10 ** P:                       # rounding carried into an extra digit
        d //= 10
        e10 += 1
    elif d < 10 ** (P - 1):                # underflow guard (extreme exponents)
        d = 10 ** (P - 1)
    digits = str(d).rstrip("0") or "0"
    return sign + _ff_positional(digits, e10)


def _cast_const_value(v, src: Type, target: Type):
    """Compile-time numeric cast used by const folding (mirrors backends)."""
    if isinstance(target, CharType):
        return int(v)                      # int -> char: the codepoint (unchecked)
    if isinstance(src, CharType):
        return _wrap_int(int(v), target)   # char -> int: wrap to width
    if isinstance(target, FloatType):
        return round_float(float(v), target)
    if isinstance(src, FloatType):
        return float_to_int(v, target)
    return _wrap_int(v, target)


def char_utf8_bytes(cp: int) -> bytes:
    """Encode a Unicode scalar as UTF-8 (mirrors the native `__char_to_str`).

    Used to render a `char` for `print`/`format` as its glyph. The same range
    branches and bit masks are emitted in assembly, so the interpreter and the
    native backend produce byte-identical output (D25)."""
    cp &= 0xFFFFFFFF
    if cp < 0x80:
        return bytes((cp,))
    if cp < 0x800:
        return bytes((0xC0 | (cp >> 6), 0x80 | (cp & 0x3F)))
    if cp < 0x10000:
        return bytes((0xE0 | (cp >> 12), 0x80 | ((cp >> 6) & 0x3F),
                      0x80 | (cp & 0x3F)))
    return bytes((
        0xF0 | ((cp >> 18) & 0x07),
        0x80 | ((cp >> 12) & 0x3F),
        0x80 | ((cp >> 6) & 0x3F),
        0x80 | (cp & 0x3F),
    ))


@dataclass
class FuncSig:
    params: list[Type]
    ret: Type | None
    decl: ast.FunDecl
    type_params: list[str] = None  # type: ignore[assignment]
    # v0.4.4 (X9): {type-param name: [trait, …]} built-in-trait bounds.
    bounds: dict[str, list[str]] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.type_params is None:
            self.type_params = []
        if self.bounds is None:
            self.bounds = {}


@dataclass
class TraitMethodSig:
    """A trait method signature (v0.4.4). `params[0]` is the receiver (`Self`);
    parameter/return types may mention `SelfType`, substituted by the concrete
    target when an `impl` is checked for conformance."""
    name: str
    params: list[Type]
    ret: Type | None
    receiver: str  # "self" or "var self"


@dataclass
class TraitSig:
    name: str
    methods: dict[str, TraitMethodSig]
    decl: ast.TraitDecl
    builtin: bool = False  # a built-in operator trait (Add/Eq/…) vs a user trait
    # the trait's own type parameters (v0.5.5, D55); method signatures may mention
    # them as `TypeParam`s, substituted by an impl's `trait_args`.
    type_params: list = dataclasses.field(default_factory=list)


@dataclass
class _Binding:
    type: Type
    mutable: bool


@dataclass
class ConstInfo:
    """A folded module-level `const`: its type and compile-time value (D28)."""
    type: Type
    value: object  # int | bool | str


class _Scope:
    def __init__(self, parent: "_Scope | None" = None):
        self.parent = parent
        self.names: dict[str, _Binding] = {}

    def define(self, name: str, binding: _Binding) -> bool:
        if name in self.names:
            return False
        self.names[name] = binding
        return True

    def lookup(self, name: str) -> _Binding | None:
        scope: _Scope | None = self
        while scope is not None:
            if name in scope.names:
                return scope.names[name]
            scope = scope.parent
        return None

    def lookup_scope(self, name: str) -> "_Scope | None":
        """The scope where `name` is defined (for closure-capture analysis)."""
        scope: _Scope | None = self
        while scope is not None:
            if name in scope.names:
                return scope
            scope = scope.parent
        return None


class _LambdaCtx:
    """Tracks the free (captured) outer variables referenced by a lambda body
    while it is being type-checked (v0.4.2). `boundary` is the lambda's own
    parameter scope; any binding resolved in a *strict ancestor* of `boundary`
    is captured by value (D15)."""
    def __init__(self, boundary: "_Scope"):
        self.boundary = boundary
        self._captures: dict[str, Type] = {}

    def add(self, name: str, t: Type) -> None:
        if name not in self._captures:
            self._captures[name] = t

    def ordered(self) -> list[tuple[str, Type]]:
        return list(self._captures.items())


# names that may not be used as user declarations
_BUILTIN_FUNCS = {"print", "assert", "panic", "unreachable", "len", "push", "pop",
                  "contains", "remove", "keys", "format", "chars",
                  "StringBuilder", "append", "append_byte", "build",
                  # low-level std runtime primitives (D29); the public surface
                  # lives in `std.io` / `std.process` / `std.fs` and wraps these.
                  "__write", "__exit", "__args", "__read_file", "__io_errno",
                  "__run", "__run_stderr", "__run_exit_code", "__run_signal",
                  "__run_errno", "__write_file"}

# builtin calls that never return (the checker treats them like a `return`)
_DIVERGING_BUILTINS = {"panic", "unreachable", "__exit"}

# sentinel for a match arm whose body diverges (definitely returns)
_DIVERGE = object()

# The prelude (D16): `Option`/`Result` are injected into every program so they
# are always in scope, and their variants may be constructed *unqualified*
# (`Some(x)`, `None`, `Ok(x)`, `Err(e)`) — the only enums exempt from the
# `Enum.Variant` form until modules/`use` arrive (v0.5).
_PRELUDE_SRC = (
    "enum Option<T> { Some(T), None }\n"
    "enum Result<T, E> { Ok(T), Err(E) }\n"
    # `get` is the safe map lookup (§2.3): a thin generic wrapper over the
    # `contains` builtin and indexing, so it reuses Option's monomorphization.
    "fun get<K, V>(m: [K: V], k: K) -> Option<V> {\n"
    "    if contains(m, k) {\n"
    "        return Some(m[k])\n"
    "    }\n"
    "    return None\n"
    "}\n"
)
# bare variant name -> the prelude enum that owns it
_PRELUDE_VARIANTS = {
    "Some": "Option", "None": "Option", "Ok": "Result", "Err": "Result",
}


class Checker:
    def __init__(self, program: ast.Program):
        self.program = program
        self.structs: dict[str, dict[str, Type]] = {}
        self.struct_decls: dict[str, ast.StructDecl] = {}
        # enum name -> ordered {variant_name: [payload Types]}; order defines tags
        self.enums: dict[str, dict[str, list[Type]]] = {}
        self.enum_decls: dict[str, ast.EnumDecl] = {}
        # enums that take part in a by-value type cycle; the compiler boxes these
        # behind a heap pointer wherever they appear as an aggregate member (v0.2.3).
        self.recursive_enums: set[str] = set()
        self.functions: dict[str, FuncSig] = {}
        # methods (v0.4.1): type-key -> {method_name: FuncSig}. Each method is
        # also registered in `functions` under a mangled `"<TypeKey>.<method>"`
        # name (the dot keeps it distinct from any user identifier), with the
        # receiver synthesized as `params[0]`.
        self.methods: dict[str, dict[str, FuncSig]] = {}
        self._impl_decls: list[ast.ImplDecl] = []
        self._method_decls: list[ast.FunDecl] = []
        # traits (v0.4.4): name -> TraitSig (signatures only, `Self`-typed)
        self.traits: dict[str, TraitSig] = {}
        self._trait_decls: list[ast.TraitDecl] = []
        # which traits each type implements via a *user* `impl Trait for T`
        # (type-key -> {trait name}); primitive built-in operator-trait defaults
        # are handled by `_type_implements` rather than stored here.
        self.trait_impls: dict[str, set[str]] = {}
        self._user_trait_impls: set[tuple[str, str]] = set()  # (trait, key)
        # `Self` is only resolvable while a trait signature is being resolved
        self._allow_self = False
        # module-level constants (D28): name -> folded ConstInfo
        self.consts: dict[str, ConstInfo] = {}
        self._const_decls: dict[str, ast.ConstDecl] = {}
        self._const_folding: set[str] = set()  # in-progress, for cycle detection
        self._aliases_raw: dict[str, ast.TypeRef] = {}
        self._alias_paths: dict[str, str | None] = {}   # alias -> its module's file
        self._alias_cache: dict[str, Type] = {}
        self.entry: ast.FunDecl | None = None
        self._current_ret: Type | None = None
        self._try_counter = 0
        self._loop_depth = 0
        # type parameters in scope while resolving/checking a generic decl
        self._type_params: frozenset[str] = frozenset()
        # {type-param name: frozenset(trait)} bounds in scope while checking a
        # bounded generic body (v0.4.4, X9)
        self._type_param_bounds: dict[str, frozenset[str]] = {}
        # stack of lambdas currently being checked (innermost last), for
        # by-value capture analysis (v0.4.2)
        self._lambda_stack: list[_LambdaCtx] = []
        # when not None, value-returning `return`s in a void context append
        # their (stmt, type) here instead of erroring — used to infer the result
        # type of a block-bodied lambda with no expected function type
        self._lambda_infer: list[tuple[ast.Return, Type]] | None = None
        # lambdas collected across the program (for the native lambda-lifting
        # pass); each is assigned a unique `lifted_name`
        self._lambdas: list[ast.Lambda] = []
        self._lambda_ids: set[int] = set()

    # -- public entry --------------------------------------------------------

    def check(self) -> "Checker":
        self._collect_globals()
        self._resolve_signatures()
        self._resolve_traits()
        self._synthesize_derives()
        self._resolve_impls()
        self._validate_bounds()
        self._fold_consts()
        self._check_attributes_and_entry()
        for decl in self.program.decls:
            if isinstance(decl, ast.FunDecl):
                with in_file(_source_path(decl)):
                    self._check_function(decl)
        for mdecl in self._method_decls:
            with in_file(_source_path(mdecl)):
                self._check_function(mdecl)
        return self

    # -- global collection ---------------------------------------------------

    def _collect_globals(self) -> None:
        seen: dict[str, ast.Node] = {}
        for decl in self.program.decls:
            with in_file(_source_path(decl)):
                if isinstance(decl, ast.ImportDecl):
                    # v0.5.1a parses imports but the module loader (v0.5.1b) is not
                    # wired yet; reaching the checker with an import means the source
                    # was type-checked directly rather than loaded as a module.
                    raise TypeCheckError(
                        "module imports are not supported yet (the loader arrives in "
                        "v0.5.1b)",
                        decl.line, decl.column,
                    )
                if isinstance(decl, ast.ImplDecl):
                    self._impl_decls.append(decl)
                    continue
                if isinstance(decl, ast.TraitDecl):
                    if decl.name in _BUILTIN_OP_TRAIT_NAMES:
                        raise TypeCheckError(
                            f"'{decl.name}' is a built-in operator trait and cannot "
                            "be redeclared",
                            decl.line, decl.column,
                        )
                    if any(t.name == decl.name for t in self._trait_decls):
                        raise TypeCheckError(
                            f"duplicate trait '{decl.name}'", decl.line, decl.column
                        )
                    self._trait_decls.append(decl)
                    continue
                name = decl.name
                if name in _BUILTIN_FUNCS:
                    raise TypeCheckError(
                        f"cannot redefine builtin '{name}'", decl.line, decl.column
                    )
                if name in seen:
                    raise TypeCheckError(
                        f"duplicate top-level declaration '{name}'", decl.line, decl.column
                    )
                seen[name] = decl
                if isinstance(decl, ast.StructDecl):
                    self.struct_decls[name] = decl
                    self.structs[name] = {}  # filled during resolution
                elif isinstance(decl, ast.EnumDecl):
                    self.enum_decls[name] = decl
                    self.enums[name] = {}  # filled during resolution
                elif isinstance(decl, ast.TypeAliasDecl):
                    self._aliases_raw[name] = decl.target
                    self._alias_paths[name] = _source_path(decl)
                elif isinstance(decl, ast.ConstDecl):
                    self._const_decls[name] = decl
                elif isinstance(decl, ast.FunDecl):
                    self.functions[name] = FuncSig([], None, decl)  # filled later

    def _resolve_signatures(self) -> None:
        # resolve every alias eagerly so cycles / bad targets are caught even
        # when the alias is never referenced
        for name, ref in self._aliases_raw.items():
            with in_file(self._alias_paths.get(name)):
                self._resolve(ref, frozenset({name}))
        # struct fields (resolved under the struct's own type parameters)
        for name, decl in self.struct_decls.items():
            with in_file(_source_path(decl)):
                self._check_type_params(decl)
                self._type_params = frozenset(decl.type_params)
                try:
                    fields: dict[str, Type] = {}
                    for f in decl.fields:
                        if f.name in fields:
                            raise TypeCheckError(
                                f"duplicate field '{f.name}' in struct '{name}'", f.line, f.column
                            )
                        fields[f.name] = self._resolve(f.type)
                finally:
                    self._type_params = frozenset()
                self.structs[name] = fields
        # enum variants & payloads (resolved under the enum's type parameters)
        for name, decl in self.enum_decls.items():
            with in_file(_source_path(decl)):
                self._check_type_params(decl)
                self._type_params = frozenset(decl.type_params)
                try:
                    variants: dict[str, list[Type]] = {}
                    for v in decl.variants:
                        if v.name in variants:
                            raise TypeCheckError(
                                f"duplicate variant '{v.name}' in enum '{name}'", v.line, v.column
                            )
                        variants[v.name] = [self._resolve(p) for p in v.payload]
                finally:
                    self._type_params = frozenset()
                self.enums[name] = variants
        self._resolve_recursion()
        # function signatures (resolved under the function's own type parameters)
        for name, sig in self.functions.items():
            with in_file(_source_path(sig.decl)):
                decl = sig.decl
                self._check_type_params(decl)
                self._type_params = frozenset(decl.type_params)
                try:
                    params = [self._resolve(p.type) for p in decl.params]
                    ret = self._resolve(decl.ret_type) if decl.ret_type is not None else None
                finally:
                    self._type_params = frozenset()
                self.functions[name] = FuncSig(params, ret, decl, list(decl.type_params),
                                               dict(decl.type_param_bounds))

    def _check_type_params(self, decl) -> None:
        seen: set[str] = set()
        for tp in decl.type_params:
            if tp in _PRIMITIVES or tp == "int":
                raise TypeCheckError(
                    f"type parameter '{tp}' shadows a built-in type name",
                    decl.line, decl.column,
                )
            # A type parameter may shadow a user type name (standard lexical
            # scoping — and the prelude's `Result<T, E>` must coexist with a user
            # type happening to be named `E`).
            if tp in seen:
                raise TypeCheckError(
                    f"duplicate type parameter '{tp}'", decl.line, decl.column
                )
            seen.add(tp)

    # -- traits (v0.4.4) -----------------------------------------------------

    def _register_builtin_op_traits(self) -> None:
        """Seed the fixed set of built-in operator traits (D52). Their method
        signatures are `Self`-typed; primitives carry implicit defaults
        (`_primitive_default_trait`) and user types provide an `impl`."""
        specs = [
            ("Add", "add", SELF), ("Sub", "sub", SELF), ("Mul", "mul", SELF),
            ("Div", "div", SELF), ("Rem", "rem", SELF),
            ("Eq", "eq", BOOL), ("Ord", "cmp", INT),
        ]
        for name, method, ret in specs:
            msig = TraitMethodSig(method, [SELF, SELF], ret, "self")
            self.traits[name] = TraitSig(name, {method: msig}, None, builtin=True)

    def _resolve_traits(self) -> None:
        """Resolve each user `trait`'s method signatures, with `Self` allowed."""
        self._register_builtin_op_traits()
        for decl in self._trait_decls:
            with in_file(_source_path(decl)):
                self._check_trait_type_params(decl)
                methods: dict[str, TraitMethodSig] = {}
                for m in decl.methods:
                    if m.name in methods:
                        raise TypeCheckError(
                            f"duplicate method '{m.name}' in trait '{decl.name}'",
                            m.line, m.column,
                        )
                    # `Self` and the trait's own type parameters are both in scope
                    # for the signatures (v0.5.5); the latter resolve to `TypeParam`s.
                    self._allow_self = True
                    self._type_params = frozenset(decl.type_params)
                    try:
                        params = [SELF] + [self._resolve(p.type) for p in m.params]
                        ret = (self._resolve(m.ret_type)
                               if m.ret_type is not None else None)
                    finally:
                        self._allow_self = False
                        self._type_params = frozenset()
                    methods[m.name] = TraitMethodSig(m.name, params, ret, m.receiver)
                self.traits[decl.name] = TraitSig(decl.name, methods, decl,
                                                  type_params=list(decl.type_params))

    def _check_trait_type_params(self, decl: ast.TraitDecl) -> None:
        seen: set[str] = set()
        for p in decl.type_params:
            if p == "Self":
                raise TypeCheckError(
                    f"trait '{decl.name}' cannot use 'Self' as a type parameter",
                    decl.line, decl.column,
                )
            if p in seen:
                raise TypeCheckError(
                    f"duplicate type parameter '{p}' on trait '{decl.name}'",
                    decl.line, decl.column,
                )
            seen.add(p)

    def _subst_self(self, t: Type | None, target: Type,
                    param_map: dict | None = None) -> Type | None:
        """Replace `SelfType` with the implementing `target` type, and (for a
        generic trait, v0.5.5) each trait `TypeParam` with its `impl` argument
        via `param_map`. Recursive."""
        if t is None or isinstance(t, (IntType, BoolType, StrType,
                                       StringBuilderType, CharType, FloatType)):
            return t
        if isinstance(t, SelfType):
            return target
        if isinstance(t, TypeParam):
            if param_map is not None and t.name in param_map:
                return param_map[t.name]
            return t
        if isinstance(t, ListType):
            return ListType(self._subst_self(t.elem, target, param_map))
        if isinstance(t, MapType):
            return MapType(self._subst_self(t.key, target, param_map),
                           self._subst_self(t.value, target, param_map))
        if isinstance(t, TupleType):
            return TupleType(tuple(self._subst_self(e, target, param_map)
                                   for e in t.elems))
        if isinstance(t, FuncType):
            return FuncType(
                tuple(self._subst_self(p, target, param_map) for p in t.params),
                self._subst_self(t.ret, target, param_map)
                if t.ret is not None else None,
            )
        if isinstance(t, StructType):
            return StructType(t.name, tuple(self._subst_self(a, target, param_map)
                                            for a in t.args))
        if isinstance(t, EnumType):
            return EnumType(t.name, tuple(self._subst_self(a, target, param_map)
                                          for a in t.args))
        return t

    def _check_trait_conformance(self, impl: ast.ImplDecl, key: str,
                                 target: Type, trait: TraitSig,
                                 param_map: dict | None = None) -> None:
        """Verify `impl Trait for T` covers exactly the trait's signatures with
        matching receiver mutability and `Self`-substituted parameter/return
        types (D52). For a generic trait, `param_map` substitutes the trait's
        type parameters with this impl's `trait_args` (v0.5.5, D55)."""
        impl_methods = {m.name: m for m in impl.methods}
        missing = set(trait.methods) - set(impl_methods)
        if missing:
            raise TypeCheckError(
                f"impl of trait '{trait.name}' for '{key}' is missing method(s): "
                f"{', '.join(sorted(missing))}",
                impl.line, impl.column,
            )
        extra = set(impl_methods) - set(trait.methods)
        if extra:
            raise TypeCheckError(
                f"impl of trait '{trait.name}' for '{key}' declares method(s) not "
                f"in the trait: {', '.join(sorted(extra))}",
                impl.line, impl.column,
            )
        for mname, tmsig in trait.methods.items():
            sig = self.methods[key][mname]
            if sig.decl.receiver != tmsig.receiver:
                raise TypeCheckError(
                    f"method '{mname}' in impl of trait '{trait.name}' for "
                    f"'{key}' has receiver '{sig.decl.receiver}' but the trait "
                    f"declares '{tmsig.receiver}'",
                    sig.decl.line, sig.decl.column,
                )
            exp_params = [self._subst_self(p, target, param_map)
                          for p in tmsig.params]
            exp_ret = self._subst_self(tmsig.ret, target, param_map)
            if sig.params != exp_params or sig.ret != exp_ret:
                exp = (f"({', '.join(type_name(p) for p in exp_params[1:])}) -> "
                       f"{type_name(exp_ret)}")
                raise TypeCheckError(
                    f"method '{mname}' in impl of trait '{trait.name}' for "
                    f"'{key}' does not match the trait signature (expected "
                    f"'{exp}')",
                    sig.decl.line, sig.decl.column,
                )

    def _validate_bounds(self) -> None:
        """Check every generic signature's bounds name a real type parameter and
        a known trait (built-in or user); reject unknown bounds early (X9)."""
        for sig in self.functions.values():
            with in_file(_source_path(sig.decl)):
                for tp, traits in sig.bounds.items():
                    if tp not in sig.type_params:
                        raise TypeCheckError(
                            f"bound on unknown type parameter '{tp}'",
                            sig.decl.line, sig.decl.column,
                        )
                    for tr in traits:
                        if tr not in self.traits:
                            raise TypeCheckError(
                                f"unknown trait '{tr}' in bound '{tp}: {tr}'",
                                sig.decl.line, sig.decl.column,
                            )

    def _check_call_bounds(self, sig: FuncSig, subst: dict[str, Type],
                           expr: ast.Call) -> None:
        """At a generic call site, verify each concrete type argument satisfies
        its declared bound (X9). A type parameter argument (calling one bounded
        generic from another) is satisfied when the caller's own bound covers
        the trait."""
        for tp, traits in sig.bounds.items():
            concrete = subst.get(tp)
            if concrete is None:
                continue
            for tr in traits:
                if isinstance(concrete, TypeParam):
                    ok = tr in self._type_param_bounds.get(concrete.name, frozenset())
                else:
                    ok = self._type_implements(concrete, tr)
                if not ok:
                    raise TypeCheckError(
                        f"type '{type_name(concrete)}' does not satisfy the bound "
                        f"'{tp}: {tr}' required by '{sig.decl.name}'",
                        expr.line, expr.column,
                    )

    def _type_implements(self, t: Type, trait: str) -> bool:
        """Whether type `t` provides `trait` — a user `impl Trait for t`, or a
        built-in implicit default on a primitive (D52). Used by operator
        resolution and generic-bound checking (v0.4.4)."""
        key = self._method_key(t)
        if key is not None and trait in self.trait_impls.get(key, set()):
            return True
        return _primitive_default_trait(t, trait)

    # -- #derive (v0.4.4) ----------------------------------------------------

    def _synthesize_derives(self) -> None:
        """Lower `#derive(Eq)` on a struct/enum into a synthesized structural
        `impl Eq for T` (D52, X8). The synthesized `eq` is written in terms of
        `==` on the components, so nested user types must themselves be `Eq`;
        the allow-list is `Eq` only (Ord is the planned next addition)."""
        targets: list[ast.StructDecl | ast.EnumDecl] = []
        for decl in self.program.decls:
            with in_file(_source_path(decl)):
                for attr in getattr(decl, "attributes", []):
                    if attr.name != "derive":
                        continue
                    if not isinstance(decl, (ast.StructDecl, ast.EnumDecl)):
                        raise TypeCheckError(
                            "'#derive' may only be applied to a struct or enum",
                            attr.line, attr.column,
                        )
                    if decl.type_params:
                        raise TypeCheckError(
                            "deriving on generic types is not supported yet (v0.4.4 "
                            "derives Eq for concrete structs/enums)",
                            attr.line, attr.column,
                        )
                    self._validate_derive_attr(attr)
                    if decl not in targets:
                        targets.append(decl)
        if not targets:
            return
        # The set of named types that will be `Eq` — user `impl Eq for T` plus
        # every type being derived — used for the structural derivability check.
        eq_types = {decl.name for decl in targets}
        for impl in self._impl_decls:
            if impl.trait_name == "Eq" and isinstance(impl.target, ast.TypeRef):
                eq_types.add(impl.target.name)
        for decl in targets:
            with in_file(_source_path(decl)):
                if any(i.trait_name == "Eq" and isinstance(i.target, ast.TypeRef)
                       and i.target.name == decl.name for i in self._impl_decls):
                    raise TypeCheckError(
                        f"type '{decl.name}' both derives Eq and has an explicit "
                        f"'impl Eq for {decl.name}'",
                        decl.line, decl.column,
                    )
                self._check_derivable_eq(decl, eq_types)
                impl = self._make_eq_impl(decl)
                self._impl_decls.append(impl)
                self.program.decls.append(impl)

    def _validate_derive_attr(self, attr: ast.Attribute) -> None:
        if attr.outputs is not None:
            raise TypeCheckError(
                "'#derive' takes trait names in parentheses, e.g. #derive(Eq)",
                attr.line, attr.column,
            )
        if not attr.args:
            raise TypeCheckError(
                "'#derive' needs at least one trait, e.g. #derive(Eq)",
                attr.line, attr.column,
            )
        for a in attr.args:
            if not isinstance(a, ast.Name):
                raise TypeCheckError(
                    "'#derive' arguments must be trait names", a.line, a.column
                )
            if a.ident != "Eq":
                raise TypeCheckError(
                    f"cannot derive '{a.ident}'; only 'Eq' is derivable in "
                    "v0.4.4 (Ord is the planned next addition)",
                    a.line, a.column,
                )

    def _check_derivable_eq(self, decl, eq_types: set[str]) -> None:
        def is_eq(t: Type) -> bool:
            if isinstance(t, (IntType, BoolType, StrType)):
                return True
            if isinstance(t, (StructType, EnumType)):
                return t.name in eq_types
            return False

        if isinstance(decl, ast.StructDecl):
            for fname, ftype in self.structs[decl.name].items():
                if not is_eq(ftype):
                    raise TypeCheckError(
                        f"cannot derive Eq for struct '{decl.name}': field "
                        f"'{fname}' has type '{type_name(ftype)}', which is "
                        "not Eq",
                        decl.line, decl.column,
                    )
        else:
            for vname, payload in self.enums[decl.name].items():
                for i, pt in enumerate(payload):
                    if not is_eq(pt):
                        raise TypeCheckError(
                            f"cannot derive Eq for enum '{decl.name}': payload "
                            f"#{i} of variant '{vname}' has type "
                            f"'{type_name(pt)}', which is not Eq",
                            decl.line, decl.column,
                        )

    def _make_eq_impl(self, decl) -> ast.ImplDecl:
        ln, col = decl.line, decl.column
        target = ast.TypeRef(decl.name).at(ln, col)
        other = ast.Param("other", ast.TypeRef(decl.name).at(ln, col)).at(ln, col)
        eq = ast.FunDecl(
            "eq", [other], ast.TypeRef("bool").at(ln, col),
            self._make_eq_body(decl), receiver="self",
        ).at(ln, col)
        return ast.ImplDecl(target, [eq], trait_name="Eq").at(ln, col)

    def _make_eq_body(self, decl) -> ast.Block:
        ln, col = decl.line, decl.column

        def conj(parts: list[ast.Expr]) -> ast.Expr:
            if not parts:
                return ast.BoolLit(True).at(ln, col)
            acc = parts[0]
            for p in parts[1:]:
                acc = ast.Binary("&&", acc, p).at(ln, col)
            return acc

        if isinstance(decl, ast.StructDecl):
            comps = [
                ast.Binary(
                    "==",
                    ast.FieldAccess(ast.Name("self").at(ln, col), f.name).at(ln, col),
                    ast.FieldAccess(ast.Name("other").at(ln, col), f.name).at(ln, col),
                ).at(ln, col)
                for f in decl.fields
            ]
            return ast.Block([ast.Return(conj(comps)).at(ln, col)]).at(ln, col)

        # enum: match on (self, other); equal variants compare payloads, a
        # mismatched pair falls through to `false`.
        arms: list[ast.MatchArm] = []
        for v in decl.variants:
            n = len(v.payload)
            self_pat = ast.PatEnum(
                decl.name, v.name,
                [ast.PatBinding(f"__a{i}").at(ln, col) for i in range(n)],
                has_payload_syntax=n > 0,
            ).at(ln, col)
            other_pat = ast.PatEnum(
                decl.name, v.name,
                [ast.PatBinding(f"__b{i}").at(ln, col) for i in range(n)],
                has_payload_syntax=n > 0,
            ).at(ln, col)
            tup = ast.PatTuple([self_pat, other_pat]).at(ln, col)
            body = conj([
                ast.Binary(
                    "==",
                    ast.Name(f"__a{i}").at(ln, col),
                    ast.Name(f"__b{i}").at(ln, col),
                ).at(ln, col)
                for i in range(n)
            ])
            arms.append(ast.MatchArm(tup, None, body).at(ln, col))
        # With a single variant the same-variant arm is already exhaustive; a
        # `_ => false` would be unreachable. With several, mismatched pairs fall
        # through to it.
        if len(decl.variants) > 1:
            arms.append(
                ast.MatchArm(ast.PatWildcard().at(ln, col), None,
                             ast.BoolLit(False).at(ln, col)).at(ln, col)
            )
        scrut = ast.TupleLit(
            [ast.Name("self").at(ln, col), ast.Name("other").at(ln, col)]
        ).at(ln, col)
        match = ast.Match(scrut, arms).at(ln, col)
        return ast.Block([ast.Return(match).at(ln, col)]).at(ln, col)

    # -- impl blocks & methods (v0.4.1) -------------------------------------

    def _resolve_impls(self) -> None:
        """Resolve every `impl` block into method signatures (D45/D46/D47).

        Each method is lowered to a top-level function with a synthesized `self`
        first parameter, registered both in `self.functions` (under a mangled
        `"<TypeKey>.<method>"` name) and in `self.methods` (for `recv.m(...)`
        resolution). Coherence: method names are unique per type and may not
        collide with a field; multiple `impl` blocks on one type are allowed.
        """
        for impl in self._impl_decls:
            with in_file(_source_path(impl)):
                self._check_type_params(impl)
                self._type_params = frozenset(impl.type_params)
                try:
                    target = self._resolve(impl.target)
                    trait_args = [self._resolve(a) for a in impl.trait_args]
                finally:
                    self._type_params = frozenset()
                key = self._method_key(target)
                if isinstance(target, (StructType, EnumType)):
                    if impl.type_params:
                        want = tuple(TypeParam(p) for p in impl.type_params)
                        if target.args != want:
                            raise TypeCheckError(
                                f"a generic impl must apply to "
                                f"'{key}<{', '.join(impl.type_params)}>' with its type "
                                "parameters in order",
                                impl.line, impl.column,
                            )
                    elif target.args:
                        raise TypeCheckError(
                            "cannot 'impl' on a concrete generic instantiation; write "
                            "'impl<T> " + key + "<T> { ... }' to cover every instance",
                            impl.line, impl.column,
                        )
                elif key is not None:
                    # A built-in receiver type (no orphan rule, D45). v0.4.1c covers
                    # read-only `self` on scalars / `str` / `StringBuilder`.
                    if impl.type_params:
                        raise TypeCheckError(
                            "generic impls on built-in types are not supported yet "
                            "(v0.4.1 covers concrete built-in receivers)",
                            impl.line, impl.column,
                        )
                    for m in impl.methods:
                        if m.receiver == "var self":
                            raise TypeCheckError(
                                "'var self' methods on built-in types are not "
                                "supported yet; use a read-only 'self' receiver",
                                m.line, m.column,
                            )
                else:
                    raise TypeCheckError(
                        f"cannot 'impl' on type '{type_name(target)}'; v0.4.1 supports "
                        "structs, enums, and concrete scalar / str / StringBuilder "
                        "receivers",
                        impl.line, impl.column,
                    )
                trait = None
                param_map: dict | None = None
                if impl.trait_name is not None:
                    trait = self.traits.get(impl.trait_name)
                    if trait is None:
                        raise TypeCheckError(
                            f"unknown trait '{impl.trait_name}' in "
                            f"'impl {impl.trait_name} for {key}'",
                            impl.line, impl.column,
                        )
                    # Match the trait's arity and bind its type parameters to this
                    # impl's arguments (v0.5.5, D55). Coherence (below) ignores the
                    # arguments, so a type implements a trait at most once.
                    if len(trait_args) != len(trait.type_params):
                        expected = (f"{impl.trait_name}<"
                                    f"{', '.join(trait.type_params)}>"
                                    if trait.type_params else impl.trait_name)
                        raise TypeCheckError(
                            f"trait '{impl.trait_name}' expects "
                            f"{len(trait.type_params)} type argument(s), got "
                            f"{len(trait_args)} (use 'impl {expected} for {key}')",
                            impl.line, impl.column,
                        )
                    if trait.type_params:
                        param_map = dict(zip(trait.type_params, trait_args))
                    pair = (impl.trait_name, key)
                    if pair in self._user_trait_impls:
                        raise TypeCheckError(
                            f"duplicate impl of trait '{impl.trait_name}' for type "
                            f"'{key}' (at most one user impl per trait/type pair)",
                            impl.line, impl.column,
                        )
                    self._user_trait_impls.add(pair)
                table = self.methods.setdefault(key, {})
                field_names = set(self.structs.get(key, {}).keys())
                for m in impl.methods:
                    if m.name in table:
                        raise TypeCheckError(
                            f"duplicate method '{m.name}' for type '{key}'",
                            m.line, m.column,
                        )
                    if m.name in field_names:
                        raise TypeCheckError(
                            f"method '{m.name}' collides with a field of '{key}'",
                            m.line, m.column,
                        )
                    self._register_method(impl, key, m)
                if trait is not None:
                    self._check_trait_conformance(impl, key, target, trait, param_map)
                    self.trait_impls.setdefault(key, set()).add(impl.trait_name)

    def _register_method(self, impl: ast.ImplDecl, key: str,
                         m: ast.FunDecl) -> None:
        mangled = f"{key}.{m.name}"
        self_param = ast.Param("self", copy.deepcopy(impl.target)).at(m.line, m.column)
        combined_tps = list(impl.type_params) + list(m.type_params)
        combined_bounds = {**impl.type_param_bounds, **m.type_param_bounds}
        fdecl = ast.FunDecl(
            mangled, [self_param] + list(m.params), m.ret_type, m.body,
            type_params=combined_tps, type_param_bounds=combined_bounds,
            receiver=m.receiver,
        ).at(m.line, m.column)
        fdecl.source_path = getattr(m, "source_path", None)
        self._check_type_params(fdecl)
        self._type_params = frozenset(combined_tps)
        try:
            params = [self._resolve(p.type) for p in fdecl.params]
            ret = self._resolve(fdecl.ret_type) if fdecl.ret_type is not None else None
        finally:
            self._type_params = frozenset()
        sig = FuncSig(params, ret, fdecl, combined_tps, combined_bounds)
        self.functions[mangled] = sig
        self.methods[key][m.name] = sig
        self._method_decls.append(fdecl)

    def _method_key(self, t: Type) -> str | None:
        """The method-table key for a receiver type.

        Structs/enums key on their (template) name; built-in receivers key on
        their canonical type name (e.g. `int32`, `bool`, `str`). Containers
        (list/map/tuple) are not yet supported as receivers (return None)."""
        if isinstance(t, (StructType, EnumType)):
            return t.name
        if isinstance(t, (IntType, BoolType, StrType, StringBuilderType)):
            return type_name(t)
        return None

    def _resolve(self, ref, visiting: frozenset[str] = frozenset()) -> Type:
        if isinstance(ref, ast.TupleTypeRef):
            return TupleType(tuple(self._resolve(e, visiting) for e in ref.elems))
        if isinstance(ref, ast.ListTypeRef):
            return ListType(self._resolve(ref.elem, visiting))
        if isinstance(ref, ast.MapTypeRef):
            kt = self._resolve(ref.key, visiting)
            vt = self._resolve(ref.value, visiting)
            # A type-parameter key (e.g. in a generic function) is validated when
            # the function is instantiated with a concrete key type.
            if not _is_map_key(kt) and not self._contains_type_param(kt):
                raise TypeCheckError(
                    f"map key type must be a primitive (integer, char, bool, or "
                    f"str), found '{type_name(kt)}'",
                    ref.line, ref.column,
                )
            return MapType(kt, vt)
        if isinstance(ref, ast.FnTypeRef):
            params = tuple(self._resolve(p, visiting) for p in ref.params)
            ret = self._resolve(ref.ret, visiting) if ref.ret is not None else None
            return FuncType(params, ret)
        name = ref.name
        args = getattr(ref, "args", []) or []
        if name == "Self":
            if not self._allow_self:
                raise TypeCheckError(
                    "'Self' is only valid inside a trait declaration",
                    ref.line, ref.column,
                )
            if args:
                raise TypeCheckError(
                    "'Self' cannot take type arguments", ref.line, ref.column
                )
            return SELF
        if name in self._type_params:
            if args:
                raise TypeCheckError(
                    f"type parameter '{name}' cannot take type arguments",
                    ref.line, ref.column,
                )
            return TypeParam(name)
        # generic struct/enum instantiation: `Box<int>`, `Result<int, str>`
        if name in self.struct_decls or name in self.enum_decls:
            params = (self.struct_decls.get(name) or self.enum_decls[name]).type_params
            if params or args:
                if len(args) != len(params):
                    raise TypeCheckError(
                        f"type '{name}' expects {len(params)} type argument(s), "
                        f"got {len(args)}",
                        ref.line, ref.column,
                    )
                resolved_args = tuple(self._resolve(a, visiting) for a in args)
                if name in self.struct_decls:
                    return StructType(name, resolved_args)
                return EnumType(name, resolved_args)
            return StructType(name) if name in self.struct_decls else EnumType(name)
        if args:
            raise TypeCheckError(
                f"type '{name}' is not generic (it takes no type arguments)",
                ref.line, ref.column,
            )
        if name in _PRIMITIVES:
            return _PRIMITIVES[name]
        if name in self._aliases_raw:
            if name in self._alias_cache:
                return self._alias_cache[name]
            if name in visiting:
                raise TypeCheckError(f"type alias cycle involving '{name}'", ref.line, ref.column)
            with in_file(self._alias_paths.get(name)):
                resolved = self._resolve(self._aliases_raw[name], visiting | {name})
            self._alias_cache[name] = resolved
            return resolved
        if name == "int":
            return INT
        if name == "float":
            return FLOAT
        raise TypeCheckError(f"unknown type '{name}'", ref.line, ref.column)

    def _resolve_recursion(self) -> None:
        """Classify by-value type cycles (e.g. a recursive `enum Expr`).

        An enum that takes part in a cycle is *boxed*: wherever it appears as an
        aggregate member the compiler stores an 8-byte heap pointer instead of an
        inline value, which breaks the otherwise-infinite size. So every cycle
        that runs through an enum is representable (v0.2.3).

        A cycle that runs purely through structs/tuples has no place to insert
        that indirection, so it stays an error — it would have infinite size.
        """
        # Recursion is a property of a *template* (List<int> and List<str> are
        # both recursive), so this works on aggregate names. We follow inline
        # members and the names appearing in their type arguments (a generic
        # member like `Box<E>` inlines an `E`), treating type parameters as
        # opaque leaves. The precise per-instantiation boxing/size decision is
        # re-derived on the fully concrete program after monomorphization.
        def member_types(name: str) -> list[Type]:
            if name in self.structs:
                return list(self.structs[name].values())
            out: list[Type] = []
            for payload in self.enums[name].values():
                out.extend(payload)
            return out

        def agg_refs(t: Type) -> list[tuple[str, bool]]:
            """Aggregate (name, is_enum) references appearing inline within `t`."""
            if isinstance(t, StructType):
                out = [(t.name, False)]
                for a in t.args:
                    out += agg_refs(a)
                return out
            if isinstance(t, EnumType):
                out = [(t.name, True)]
                for a in t.args:
                    out += agg_refs(a)
                return out
            if isinstance(t, TupleType):
                out = []
                for e in t.elems:
                    out += agg_refs(e)
                return out
            return []

        def find_cycle(root: str, current: str, seen: frozenset[str],
                       stop_at_boxed: bool) -> bool:
            for m in member_types(current):
                for nm, is_enum in agg_refs(m):
                    # A boxed enum member is a pointer — a leaf that breaks the cycle.
                    if stop_at_boxed and is_enum and nm in self.recursive_enums:
                        continue
                    if nm == root:
                        return True
                    if nm in seen:
                        continue
                    if find_cycle(root, nm, seen | {nm}, stop_at_boxed):
                        return True
            return False

        # 1) every enum that lies on a cycle becomes boxed.
        for name in self.enums:
            if find_cycle(name, name, frozenset({name}), stop_at_boxed=False):
                self.recursive_enums.add(name)

        # 2) any cycle that survives once boxed edges are cut is unrepresentable.
        for name in list(self.enums) + list(self.structs):
            if find_cycle(name, name, frozenset({name}), stop_at_boxed=True):
                kind = "enum" if name in self.enums else "struct"
                decl = self.enum_decls.get(name) or self.struct_decls.get(name)
                with in_file(_source_path(decl)):
                    raise TypeCheckError(
                        f"recursive {kind} '{name}' would have infinite size; "
                        "only enums can be recursive (they are boxed) — wrap the "
                        "cycle in an enum to introduce indirection",
                        decl.line, decl.column,
                    )

    # -- attributes & entry point -------------------------------------------

    # -- module-level constants (D28) ---------------------------------------

    def _fold_consts(self) -> None:
        """Type-check and constant-fold every `const`, detecting cycles."""
        for name in self._const_decls:
            self._ensure_const(name)

    def _ensure_const(self, name: str) -> ConstInfo:
        """Return the folded value of const `name`, folding it (and any consts it
        references) on demand. Raises on a cyclic definition."""
        if name in self.consts:
            return self.consts[name]
        decl = self._const_decls[name]
        if name in self._const_folding:
            raise TypeCheckError(
                f"const '{name}' is defined in terms of itself", decl.line, decl.column
            )
        self._const_folding.add(name)
        try:
            with in_file(_source_path(decl)):   # also when folded from elsewhere
                declared = self._resolve(decl.declared_type)
                if isinstance(declared, TypeParam):
                    raise TypeCheckError(
                        "a const type must be concrete", decl.line, decl.column
                    )
                vt = self._expect_value(decl.value, _Scope(), declared)
                if vt != declared:
                    raise TypeCheckError(
                        f"const '{name}' is declared '{type_name(declared)}' but its "
                        f"value has type '{type_name(vt)}'",
                        decl.value.line, decl.value.column,
                    )
                value = self._fold_const_expr(decl.value)
        finally:
            self._const_folding.discard(name)
        info = ConstInfo(declared, value)
        self.consts[name] = info
        return info

    def _fold_const_expr(self, expr: ast.Expr):
        if isinstance(expr, ast.IntLit):
            if isinstance(expr.resolved_type, CharType):
                return expr.value          # a char const folds to its codepoint
            return _wrap_int(expr.value, expr.resolved_type)
        if isinstance(expr, ast.FloatLit):
            return round_float(expr.value, expr.resolved_type)
        if isinstance(expr, ast.BoolLit):
            return expr.value
        if isinstance(expr, ast.StrLit):
            return expr.value
        if isinstance(expr, ast.Name):
            ref = getattr(expr, "const_ref", None)
            if ref is not None:
                return self._ensure_const(ref).value
            raise TypeCheckError(
                f"'{expr.ident}' is not a constant and cannot appear in a const "
                "initializer",
                expr.line, expr.column,
            )
        if isinstance(expr, ast.Unary):
            v = self._fold_const_expr(expr.operand)
            if expr.op == "-":
                if isinstance(expr.resolved_type, FloatType):
                    return round_float(-v, expr.resolved_type)
                return _wrap_int(-v, expr.resolved_type)
            if expr.op == "~":
                return _wrap_int(~v, expr.resolved_type)
            return not v  # "!"
        if isinstance(expr, ast.Cast):
            return _cast_const_value(
                self._fold_const_expr(expr.operand),
                expr.operand.resolved_type, expr.resolved_type)
        if isinstance(expr, ast.Binary):
            return self._fold_const_binary(expr)
        raise TypeCheckError(
            "const initializer must be a constant expression (literals, other "
            "consts, and arithmetic/bitwise/comparison/cast operations over them)",
            expr.line, expr.column,
        )

    def _fold_const_binary(self, expr: ast.Binary):
        op = expr.op
        if op == "&&":
            return bool(self._fold_const_expr(expr.left)
                        and self._fold_const_expr(expr.right))
        if op == "||":
            return bool(self._fold_const_expr(expr.left)
                        or self._fold_const_expr(expr.right))
        left = self._fold_const_expr(expr.left)
        right = self._fold_const_expr(expr.right)
        t = expr.resolved_type
        if isinstance(t, FloatType):
            if op == "+":
                return round_float(left + right, t)
            if op == "-":
                return round_float(left - right, t)
            if op == "*":
                return round_float(left * right, t)
            if op == "/":
                return round_float(float_div(left, right), t)  # IEEE (D56)
            if op == "%":
                return round_float(float_rem(left, right), t)
        if op == "+":
            return _wrap_int(left + right, t)
        if op == "-":
            return _wrap_int(left - right, t)
        if op == "*":
            return _wrap_int(left * right, t)
        if op in ("/", "%"):
            if right == 0:
                raise TypeCheckError(
                    f"const division by zero", expr.line, expr.column
                )
            q = _const_idiv(left, right)
            return _wrap_int(q if op == "/" else left - q * right, t)
        if op == "&":
            return _wrap_int(left & right, t)
        if op == "|":
            return _wrap_int(left | right, t)
        if op == "^":
            return _wrap_int(left ^ right, t)
        if op == "<<":
            return _wrap_int(left << (right & (t.width - 1)), t)
        if op == ">>":
            return _wrap_int(_wrap_int(left, expr.left.resolved_type)
                             >> (right & (t.width - 1)), t)
        if op == "<":
            return left < right
        if op == "<=":
            return left <= right
        if op == ">":
            return left > right
        if op == ">=":
            return left >= right
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        raise TypeCheckError(  # pragma: no cover - defensive
            f"unsupported const operator '{op}'", expr.line, expr.column
        )

    def _check_attributes_and_entry(self) -> None:
        main_decls: list[ast.FunDecl] = []
        for decl in self.program.decls:
            with in_file(_source_path(decl)):
                for attr in decl.attributes:
                    # `#derive` (v0.4.4) is validated and lowered by
                    # `_synthesize_derives`; skip it here.
                    if attr.name == "derive":
                        continue
                    if attr.name not in ("main", "test"):
                        raise TypeCheckError(
                            f"unknown attribute '#{attr.name}'", attr.line, attr.column
                        )
                    if not isinstance(decl, ast.FunDecl):
                        raise TypeCheckError(
                            f"attribute '#{attr.name}' may only be applied to functions",
                            attr.line, attr.column,
                        )
                    if decl.type_params:
                        raise TypeCheckError(
                            f"attribute '#{attr.name}' cannot be applied to a generic "
                            "function (it has no single concrete instantiation)",
                            attr.line, attr.column,
                        )
                    if attr.name == "main":
                        self._check_main_attr(decl, attr)
                        main_decls.append(decl)
                    else:
                        self._check_test_attr(decl, attr)

        named_main = self.functions.get("main")
        if main_decls and named_main is not None and named_main.decl not in main_decls:
            with in_file(_source_path(named_main.decl)):
                raise TypeCheckError(
                    "both a '#main' function and a function named 'main' are present",
                    named_main.decl.line, named_main.decl.column,
                )
        if len(main_decls) > 1:
            with in_file(_source_path(main_decls[1])):
                raise TypeCheckError(
                    "more than one '#main' entry point", main_decls[1].line, main_decls[1].column
                )
        entry = main_decls[0] if main_decls else (named_main.decl if named_main else None)
        if entry is not None and entry.params:
            with in_file(_source_path(entry)):
                raise TypeCheckError(
                    "entry point must take no parameters in v0.0", entry.line, entry.column
                )
        self.entry = entry

    def _check_main_attr(self, decl: ast.FunDecl, attr: ast.Attribute) -> None:
        if attr.args or attr.outputs is not None:
            raise TypeCheckError("'#main' takes no arguments", attr.line, attr.column)

    def _check_test_attr(self, decl: ast.FunDecl, attr: ast.Attribute) -> None:
        sig = self.functions[decl.name]
        if attr.outputs is None:
            raise TypeCheckError(
                "'#test' requires an expected result, e.g. #test(args)[expected]",
                attr.line, attr.column,
            )
        if sig.ret is None:
            raise TypeCheckError(
                "'#test' requires the function to return a value", attr.line, attr.column
            )
        if len(attr.args) != len(sig.params):
            raise TypeCheckError(
                f"'#test' expects {len(sig.params)} argument(s), got {len(attr.args)}",
                attr.line, attr.column,
            )
        for arg, ptype in zip(attr.args, sig.params):
            self._expect_value(arg, _Scope(), ptype)
        if len(attr.outputs) != 1:
            raise TypeCheckError(
                "'#test' expects exactly one expected value in [...]", attr.line, attr.column
            )
        self._expect_value(attr.outputs[0], _Scope(), sig.ret)

    # -- function bodies -----------------------------------------------------

    def _check_function(self, decl: ast.FunDecl) -> None:
        sig = self.functions[decl.name]
        self._current_ret = sig.ret
        self._type_params = frozenset(decl.type_params)
        self._type_param_bounds = {
            tp: frozenset(traits) for tp, traits in sig.bounds.items()
        }
        try:
            scope = _Scope()
            for i, (param, ptype) in enumerate(zip(decl.params, sig.params)):
                # A `var self` receiver (params[0] of a method) is mutable so the
                # body can write `self.field = ...`; every other param is borrowed
                # and immutable.
                mutable = (i == 0 and decl.receiver == "var self")
                scope.define(param.name, _Binding(ptype, mutable=mutable))
            self._check_block(decl.body, scope, sig.ret)
            if sig.ret is not None and not _block_returns(decl.body):
                raise TypeCheckError(
                    f"function '{decl.name}' may finish without returning a "
                    f"'{type_name(sig.ret)}'",
                    decl.line, decl.column,
                )
        finally:
            self._type_params = frozenset()
            self._type_param_bounds = {}

    def _check_block(self, block: ast.Block, parent: _Scope, ret: Type | None) -> None:
        scope = _Scope(parent)
        for stmt in block.statements:
            self._check_stmt(stmt, scope, ret)

    def _check_stmt(self, stmt: ast.Stmt, scope: _Scope, ret: Type | None) -> None:
        if isinstance(stmt, ast.VarDecl):
            declared = self._resolve(stmt.declared_type) if stmt.declared_type else None
            value_type = self._expect_value(stmt.init, scope, declared)
            final = declared if declared is not None else value_type
            if declared is not None and value_type != declared:
                raise TypeCheckError(
                    f"cannot assign value of type '{type_name(value_type)}' to "
                    f"binding of type '{type_name(declared)}'",
                    stmt.line, stmt.column,
                )
            if not scope.define(stmt.name, _Binding(final, mutable=(stmt.kind == "var"))):
                raise TypeCheckError(
                    f"'{stmt.name}' is already declared in this scope", stmt.line, stmt.column
                )

        elif isinstance(stmt, ast.DestructDecl):
            declared = self._resolve(stmt.declared_type) if stmt.declared_type else None
            value_type = self._expect_value(stmt.init, scope, declared)
            if declared is not None and value_type != declared:
                raise TypeCheckError(
                    f"cannot assign value of type '{type_name(value_type)}' to "
                    f"binding of type '{type_name(declared)}'",
                    stmt.line, stmt.column,
                )
            if not isinstance(value_type, TupleType):
                raise TypeCheckError(
                    f"cannot destructure non-tuple value of type '{type_name(value_type)}'",
                    stmt.line, stmt.column,
                )
            self._bind_pattern(stmt.binding, value_type, scope,
                               mutable=(stmt.kind == "var"))

        elif isinstance(stmt, ast.Assign):
            if isinstance(stmt.target, ast.Name) and stmt.target.ident == "self":
                raise TypeCheckError(
                    "cannot reassign 'self'; mutate its fields or elements instead",
                    stmt.line, stmt.column,
                )
            target_type, mutable = self._check_lvalue(stmt.target, scope)
            if not mutable:
                raise TypeCheckError(
                    "cannot assign to an immutable binding (declare it with 'var')",
                    stmt.line, stmt.column,
                )
            value_type = self._expect_value(stmt.value, scope, target_type)
            if value_type != target_type:
                raise TypeCheckError(
                    f"cannot assign '{type_name(value_type)}' to '{type_name(target_type)}'",
                    stmt.line, stmt.column,
                )

        elif isinstance(stmt, ast.If):
            self._expect_type(stmt.cond, scope, BOOL, "if condition")
            self._check_block(stmt.then, scope, ret)
            if isinstance(stmt.otherwise, ast.If):
                self._check_stmt(stmt.otherwise, scope, ret)
            elif isinstance(stmt.otherwise, ast.Block):
                self._check_block(stmt.otherwise, scope, ret)

        elif isinstance(stmt, ast.While):
            self._expect_type(stmt.cond, scope, BOOL, "while condition")
            self._loop_depth += 1
            self._check_block(stmt.body, scope, ret)
            self._loop_depth -= 1

        elif isinstance(stmt, ast.For):
            if stmt.iterable is not None:  # `for v in xs/m` — list/map iteration
                it = self._expect_value(stmt.iterable, scope, None)
                if isinstance(it, ListType):
                    loop_t: Type = it.elem
                elif isinstance(it, MapType):   # iterate keys (unspecified order)
                    loop_t = it.key
                else:
                    raise TypeCheckError(
                        f"`for ... in` requires a list or map, found "
                        f"'{type_name(it)}'",
                        stmt.iterable.line, stmt.iterable.column,
                    )
            else:  # `for v in start..end` — integer range
                start_t = self._expect_value(stmt.start, scope, None)
                end_t = self._expect_value(stmt.end, scope, None)
                loop_t = self._unify(stmt.start, start_t, stmt.end, end_t)
                if not isinstance(loop_t, IntType):
                    raise TypeCheckError("for-range bounds must be integers", stmt.line, stmt.column)
            body_scope = _Scope(scope)
            body_scope.define(stmt.var_name, _Binding(loop_t, mutable=False))
            self._loop_depth += 1
            self._check_block(stmt.body, body_scope, ret)
            self._loop_depth -= 1

        elif isinstance(stmt, (ast.Break, ast.Continue)):
            if self._loop_depth == 0:
                kw = "break" if isinstance(stmt, ast.Break) else "continue"
                raise TypeCheckError(
                    f"'{kw}' outside of a loop", stmt.line, stmt.column
                )

        elif isinstance(stmt, ast.Return):
            if ret is None:
                if stmt.value is not None:
                    if self._lambda_infer is not None:
                        vt = self._expect_value(stmt.value, scope, None)
                        self._lambda_infer.append((stmt, vt))
                    else:
                        raise TypeCheckError(
                            "cannot return a value from a function with no return type",
                            stmt.line, stmt.column,
                        )
            else:
                if stmt.value is None:
                    raise TypeCheckError(
                        f"expected a return value of type '{type_name(ret)}'",
                        stmt.line, stmt.column,
                    )
                vt = self._expect_value(stmt.value, scope, ret)
                if vt != ret:
                    raise TypeCheckError(
                        f"return type mismatch: expected '{type_name(ret)}', "
                        f"found '{type_name(vt)}'",
                        stmt.line, stmt.column,
                    )

        elif isinstance(stmt, ast.ExprStmt):
            if isinstance(stmt.expr, ast.Match):
                stmt.expr.is_statement = True
            self._infer(stmt.expr, scope, None)  # void calls allowed here

        else:  # pragma: no cover - defensive
            raise TypeCheckError(f"unsupported statement {type(stmt).__name__}",
                                 stmt.line, stmt.column)

    def _bind_pattern(self, binding, t: Type, scope: _Scope, mutable: bool) -> None:
        if isinstance(binding, ast.BindWildcard):
            return
        if isinstance(binding, ast.BindName):
            binding.resolved_type = t
            if not scope.define(binding.name, _Binding(t, mutable)):
                raise TypeCheckError(
                    f"'{binding.name}' is already declared in this scope",
                    binding.line, binding.column,
                )
            return
        if isinstance(binding, ast.BindTuple):
            if not isinstance(t, TupleType):
                raise TypeCheckError(
                    f"cannot destructure non-tuple value of type '{type_name(t)}'",
                    binding.line, binding.column,
                )
            if len(binding.elems) != len(t.elems):
                raise TypeCheckError(
                    f"tuple pattern expects {len(binding.elems)} element(s), "
                    f"but value has {len(t.elems)}",
                    binding.line, binding.column,
                )
            for elem, et in zip(binding.elems, t.elems):
                self._bind_pattern(elem, et, scope, mutable)
            return
        raise TypeCheckError(  # pragma: no cover - defensive
            "invalid destructuring binding", binding.line, binding.column
        )

    def _check_lvalue(self, expr: ast.Expr, scope: _Scope) -> tuple[Type, bool]:
        if isinstance(expr, ast.Name):
            binding = scope.lookup(expr.ident)
            if binding is None:
                raise TypeCheckError(f"unknown name '{expr.ident}'", expr.line, expr.column)
            expr.resolved_type = binding.type
            return binding.type, binding.mutable
        if isinstance(expr, ast.FieldAccess):
            base_type, mutable = self._check_lvalue(expr.target, scope)
            if not isinstance(base_type, StructType):
                raise TypeCheckError(
                    f"type '{type_name(base_type)}' has no fields", expr.line, expr.column
                )
            fields = self._struct_field_types(base_type)
            if expr.field_name not in fields:
                raise TypeCheckError(
                    f"struct '{base_type.name}' has no field '{expr.field_name}'",
                    expr.line, expr.column,
                )
            ft = fields[expr.field_name]
            expr.resolved_type = ft
            return ft, mutable
        if isinstance(expr, ast.Index):
            base_type, mutable = self._check_lvalue(expr.target, scope)
            if isinstance(base_type, MapType):
                self._expect_type(expr.index, scope, base_type.key, "map key")
                expr.resolved_type = base_type.value
                return base_type.value, mutable
            if isinstance(base_type, StrType):
                raise TypeCheckError(
                    "strings are immutable; `s[i]` cannot be assigned to",
                    expr.line, expr.column,
                )
            if not isinstance(base_type, ListType):
                raise TypeCheckError(
                    f"type '{type_name(base_type)}' is not a list and cannot be "
                    f"indexed with `[...]`",
                    expr.line, expr.column,
                )
            it = self._expect_value(expr.index, scope, INT)
            if not isinstance(it, IntType):
                raise TypeCheckError(
                    f"list index must be an integer, found '{type_name(it)}'",
                    expr.index.line, expr.index.column,
                )
            expr.resolved_type = base_type.elem
            return base_type.elem, mutable
        raise TypeCheckError("invalid assignment target", expr.line, expr.column)

    # -- expression typing ---------------------------------------------------

    def _expect_type(self, expr: ast.Expr, scope: _Scope, want: Type, ctx: str) -> None:
        t = self._expect_value(expr, scope, want)
        if t != want:
            raise TypeCheckError(
                f"{ctx} must be '{type_name(want)}', found '{type_name(t)}'",
                expr.line, expr.column,
            )

    def _expect_value(self, expr: ast.Expr, scope: _Scope, expected: Type | None) -> Type:
        t = self._infer(expr, scope, expected)
        if t is None:
            raise TypeCheckError("expression does not produce a value", expr.line, expr.column)
        return t

    def _infer(self, expr: ast.Expr, scope: _Scope, expected: Type | None) -> Type | None:
        if isinstance(expr, ast.IntLit):
            return self._infer_int_lit(expr, expected)
        if isinstance(expr, ast.FloatLit):
            return self._infer_float_lit(expr, expected)
        if isinstance(expr, ast.StrLit):
            expr.resolved_type = STR
            return STR
        if isinstance(expr, ast.BoolLit):
            expr.resolved_type = BOOL
            return BOOL
        if isinstance(expr, ast.Name):
            return self._infer_name(expr, scope, expected)
        if isinstance(expr, ast.Unary):
            return self._infer_unary(expr, scope, expected)
        if isinstance(expr, ast.Binary):
            return self._infer_binary(expr, scope, expected)
        if isinstance(expr, ast.Call):
            return self._infer_call(expr, scope, expected)
        if isinstance(expr, ast.FieldAccess):
            return self._infer_field(expr, scope, expected)
        if isinstance(expr, ast.StructLit):
            return self._infer_struct_lit(expr, scope, expected)
        if isinstance(expr, ast.TupleLit):
            return self._infer_tuple_lit(expr, scope, expected)
        if isinstance(expr, ast.TupleIndex):
            return self._infer_tuple_index(expr, scope)
        if isinstance(expr, ast.ListLit):
            return self._infer_list_lit(expr, scope, expected)
        if isinstance(expr, ast.MapLit):
            return self._infer_map_lit(expr, scope, expected)
        if isinstance(expr, ast.Index):
            return self._infer_index(expr, scope)
        if isinstance(expr, ast.Match):
            return self._infer_match(expr, scope, expected)
        if isinstance(expr, ast.Try):
            return self._infer_try(expr, scope)
        if isinstance(expr, ast.Cast):
            return self._infer_cast(expr, scope)
        if isinstance(expr, ast.Lambda):
            return self._infer_lambda(expr, scope, expected)
        if isinstance(expr, ast.Hole):
            raise TypeCheckError(
                "'_' placeholder is only valid as a call argument",
                expr.line, expr.column,
            )
        raise TypeCheckError(  # pragma: no cover - defensive
            f"unsupported expression {type(expr).__name__}", expr.line, expr.column
        )

    def _infer_lambda(self, expr: ast.Lambda, scope: _Scope,
                      expected: Type | None) -> Type:
        """Type a lambda `(params) => body` (v0.4.2).

        Parameter types come from their annotations, or — when the lambda is
        checked against an expected function type (a parameter/annotation) — from
        the matching expected parameter. The body is checked in a child scope;
        free outer variables are recorded as by-value captures (D15)."""
        exp = expected if isinstance(expected, FuncType) else None
        if exp is not None and len(exp.params) != len(expr.params):
            exp = None
        ptypes: list[Type] = []
        for i, p in enumerate(expr.params):
            if p.type is not None:
                pt = self._resolve(p.type)
            elif exp is not None:
                pt = exp.params[i]
            else:
                raise TypeCheckError(
                    f"cannot infer the type of lambda parameter '{p.name}'; "
                    f"annotate it (e.g. '{p.name}: int')",
                    p.line, p.column,
                )
            ptypes.append(pt)

        lam_scope = _Scope(scope)
        for p, pt in zip(expr.params, ptypes):
            if not lam_scope.define(p.name, _Binding(pt, mutable=False)):
                raise TypeCheckError(
                    f"duplicate lambda parameter '{p.name}'", p.line, p.column
                )
        want_ret = exp.ret if exp is not None else None
        ctx = _LambdaCtx(lam_scope)
        self._lambda_stack.append(ctx)
        saved_ret = self._current_ret
        try:
            if isinstance(expr.body, ast.Block):
                if want_ret is not None:
                    self._current_ret = want_ret
                    self._check_block(expr.body, lam_scope, want_ret)
                    if not _block_returns(expr.body):
                        raise TypeCheckError(
                            f"lambda may finish without returning a "
                            f"'{type_name(want_ret)}'",
                            expr.line, expr.column,
                        )
                    ret_t = want_ret
                else:
                    # No expected type: infer the result from the `return`s.
                    collector: list[tuple[ast.Return, Type]] = []
                    saved_infer = self._lambda_infer
                    self._lambda_infer = collector
                    self._current_ret = None
                    try:
                        self._check_block(expr.body, lam_scope, None)
                    finally:
                        self._lambda_infer = saved_infer
                    ret_t = collector[0][1] if collector else None
                    for stmt, vt in collector[1:]:
                        if vt != ret_t:
                            raise TypeCheckError(
                                f"inconsistent lambda return types: '{type_name(ret_t)}' "
                                f"vs '{type_name(vt)}'",
                                stmt.line, stmt.column,
                            )
            else:
                # a `?` in the body returns from the lambda (MYLA-72)
                self._current_ret = want_ret
                ret_t = self._infer(expr.body, lam_scope, want_ret)
        finally:
            self._current_ret = saved_ret
            self._lambda_stack.pop()

        ft = FuncType(tuple(ptypes), ret_t)
        expr.captures = ctx.ordered()
        # Assign a lifted name once per checker (the monomorphizer re-checks a
        # deep-copied program, so a stale name carried by the copy is replaced).
        if id(expr) not in self._lambda_ids:
            expr.lifted_name = f"__lambda_{len(self._lambdas)}"
            self._lambdas.append(expr)
            self._lambda_ids.add(id(expr))
        expr.resolved_type = ft
        return ft

    def _infer_tuple_lit(self, expr: ast.TupleLit, scope: _Scope,
                         expected: Type | None) -> Type:
        exp_elems: tuple[Type, ...] | None = None
        if isinstance(expected, TupleType) and len(expected.elems) == len(expr.elems):
            exp_elems = expected.elems
        elem_types: list[Type] = []
        for i, e in enumerate(expr.elems):
            want = exp_elems[i] if exp_elems is not None else None
            elem_types.append(self._expect_value(e, scope, want))
        t = TupleType(tuple(elem_types))
        expr.resolved_type = t
        return t

    def _infer_tuple_index(self, expr: ast.TupleIndex, scope: _Scope) -> Type:
        base = self._expect_value(expr.target, scope, None)
        if not isinstance(base, TupleType):
            raise TypeCheckError(
                f"type '{type_name(base)}' is not a tuple and cannot be indexed with '.{expr.index}'",
                expr.line, expr.column,
            )
        if not (0 <= expr.index < len(base.elems)):
            raise TypeCheckError(
                f"tuple index {expr.index} out of range for '{type_name(base)}'",
                expr.line, expr.column,
            )
        ft = base.elems[expr.index]
        expr.resolved_type = ft
        return ft

    def _infer_list_lit(self, expr: ast.ListLit, scope: _Scope,
                        expected: Type | None) -> Type:
        exp_elem = expected.elem if isinstance(expected, ListType) else None
        if not expr.elems:
            if exp_elem is None:
                raise TypeCheckError(
                    "cannot infer the element type of an empty list `[]`; "
                    "annotate it (e.g. `: [int]`)",
                    expr.line, expr.column,
                )
            t = ListType(exp_elem)
            expr.resolved_type = t
            return t
        # Infer the first element, then require the rest to unify to it. An
        # element-type hint (annotation/param/return) flows into every element so
        # `[1, 2, 3]: [uint8]` adopts `uint8` (integer-literal flexibility).
        elem_t = self._expect_value(expr.elems[0], scope, exp_elem)
        for e in expr.elems[1:]:
            et = self._expect_value(e, scope, elem_t)
            elem_t = self._unify(expr.elems[0], elem_t, e, et)
        t = ListType(elem_t)
        expr.resolved_type = t
        return t

    def _infer_index(self, expr: ast.Index, scope: _Scope) -> Type:
        base = self._expect_value(expr.target, scope, None)
        if isinstance(base, MapType):
            self._expect_type(expr.index, scope, base.key, "map key")
            expr.resolved_type = base.value
            return base.value
        if isinstance(base, StrType):
            it = self._expect_value(expr.index, scope, INT)
            if not isinstance(it, IntType):
                raise TypeCheckError(
                    f"string index must be an integer, found '{type_name(it)}'",
                    expr.index.line, expr.index.column,
                )
            expr.resolved_type = BYTE      # `s[i]` is the byte at index i
            return BYTE
        if not isinstance(base, ListType):
            raise TypeCheckError(
                f"type '{type_name(base)}' is not a list and cannot be indexed "
                f"with `[...]`",
                expr.line, expr.column,
            )
        it = self._expect_value(expr.index, scope, INT)
        if not isinstance(it, IntType):
            raise TypeCheckError(
                f"list index must be an integer, found '{type_name(it)}'",
                expr.index.line, expr.index.column,
            )
        expr.resolved_type = base.elem
        return base.elem

    def _infer_map_lit(self, expr: ast.MapLit, scope: _Scope,
                       expected: Type | None) -> Type:
        exp = expected if isinstance(expected, MapType) else None
        exp_k = exp.key if exp else None
        exp_v = exp.value if exp else None
        if not expr.entries:
            if exp is None:
                raise TypeCheckError(
                    "cannot infer the key/value types of an empty map `[:]`; "
                    "annotate it (e.g. `: [str: int]`)",
                    expr.line, expr.column,
                )
            expr.resolved_type = exp
            return exp
        k0, v0 = expr.entries[0]
        key_t = self._expect_value(k0, scope, exp_k)
        if not _is_map_key(key_t):
            raise TypeCheckError(
                f"map key type must be a primitive (integer, char, bool, or str), "
                f"found '{type_name(key_t)}'",
                k0.line, k0.column,
            )
        val_t = self._expect_value(v0, scope, exp_v)
        for k, v in expr.entries[1:]:
            kt = self._expect_value(k, scope, key_t)
            key_t = self._unify(k0, key_t, k, kt)
            vt = self._expect_value(v, scope, val_t)
            val_t = self._unify(v0, val_t, v, vt)
        t = MapType(key_t, val_t)
        expr.resolved_type = t
        return t

    # -- match ---------------------------------------------------------------

    def _infer_match(self, expr: ast.Match, scope: _Scope,
                     expected: Type | None) -> Type | None:
        st = self._expect_value(expr.scrutinee, scope, None)
        is_stmt = getattr(expr, "is_statement", False)

        bodies: list[tuple[Type | None, ast.Expr | None]] = []
        for arm in expr.arms:
            arm_scope = _Scope(scope)
            self._check_pattern(arm.pattern, st, arm_scope)
            if arm.guard is not None:
                self._expect_type(arm.guard, arm_scope, BOOL, "match guard")
            bodies.append(self._check_arm_body(arm.body, arm_scope, expected))

        self._check_exhaustive(expr, st)
        self._check_redundant(expr, st)

        if is_stmt:
            expr.resolved_type = None
            return None
        # Arms that definitely return (`=> { return ... }`) diverge — they yield
        # no value and so don't constrain the match's result type. This is what
        # makes `?` desugaring work, but it is a general rule.
        value_bodies = [(t, n) for (t, n) in bodies if t is not _DIVERGE]
        for vtype, vnode in value_bodies:
            if vtype is None:
                raise TypeCheckError(
                    "this match is used as a value, so every arm must produce one",
                    expr.line, expr.column,
                )
        if not value_bodies:
            raise TypeCheckError(
                "this match is used as a value, but every arm diverges",
                expr.line, expr.column,
            )
        result = self._unify_match_result(value_bodies)
        expr.resolved_type = result
        return result

    def _infer_try(self, expr: ast.Try, scope: _Scope) -> Type:
        ot = self._expect_value(expr.operand, scope, None)
        ret = self._current_ret
        # `?` returns from the innermost function or lambda (MYLA-72)
        where = "lambda" if self._lambda_stack else "function"
        if ret is None and self._lambda_stack:
            raise TypeCheckError(
                "'?' in a lambda needs the lambda's result type: pass the lambda "
                "where a function type is expected, or annotate the variable "
                "(e.g. 'let f: (int) -> Option<int> = …')",
                expr.line, expr.column,
            )
        if isinstance(ot, EnumType) and ot.name == "Result" and len(ot.args) == 2:
            ok_t, err_t = ot.args
            if not (isinstance(ret, EnumType) and ret.name == "Result"
                    and len(ret.args) == 2):
                raise TypeCheckError(
                    f"'?' on a Result requires the enclosing {where} to return a "
                    "Result", expr.line, expr.column,
                )
            if ret.args[1] != err_t:
                raise TypeCheckError(
                    f"'?' propagates an error of type '{type_name(err_t)}', but the "
                    f"{where} returns 'Result<_, {type_name(ret.args[1])}>' "
                    "(there is no error conversion in v0.2)",
                    expr.line, expr.column,
                )
            result_t, succ, fail, fail_payload = ok_t, "Ok", "Err", True
        elif isinstance(ot, EnumType) and ot.name == "Option" and len(ot.args) == 1:
            if not (isinstance(ret, EnumType) and ret.name == "Option"
                    and len(ret.args) == 1):
                raise TypeCheckError(
                    f"'?' on an Option requires the enclosing {where} to return an "
                    "Option", expr.line, expr.column,
                )
            result_t, succ, fail, fail_payload = ot.args[0], "Some", "None", False
        else:
            raise TypeCheckError(
                f"'?' can only be applied to an Option or Result, not "
                f"'{type_name(ot)}'", expr.line, expr.column,
            )
        expr.desugared = self._build_try_match(expr, succ, fail, fail_payload)
        self._infer_match(expr.desugared, scope, result_t)
        expr.resolved_type = result_t
        return result_t

    def _build_try_match(self, expr: ast.Try, succ: str, fail: str,
                         fail_payload: bool) -> ast.Match:
        """Synthesize the `match operand { Succ(v) => v, Fail(..) => { return
        Fail(..) } }` that `expr?` is equivalent to (carrier now known)."""
        ln, col = expr.line, expr.column
        n = self._try_counter
        self._try_counter += 1
        vname = f"__try_v{n}"

        def at(node):
            return node.at(ln, col)

        succ_arm = at(ast.MatchArm(
            at(ast.PatEnum(None, succ, [at(ast.PatBinding(vname))], True)),
            None, at(ast.Name(vname)),
        ))
        carrier = "Result" if fail_payload else "Option"
        if fail_payload:
            ename = f"__try_e{n}"
            fail_pat = at(ast.PatEnum(None, fail, [at(ast.PatBinding(ename))], True))
            fail_value: ast.Expr = at(ast.Call(
                at(ast.FieldAccess(at(ast.Name(carrier)), fail)),
                [at(ast.Name(ename))],
            ))
        else:
            fail_pat = at(ast.PatEnum(None, fail, [], False))
            fail_value = at(ast.FieldAccess(at(ast.Name(carrier)), fail))
        fail_arm = at(ast.MatchArm(
            fail_pat, None, at(ast.Block([at(ast.Return(fail_value))])),
        ))
        return at(ast.Match(expr.operand, [succ_arm, fail_arm]))

    def _check_arm_body(self, body, scope: _Scope,
                        expected: Type | None) -> tuple[object, ast.Expr | None]:
        if isinstance(body, ast.Block):
            bscope = _Scope(scope)
            stmts = body.statements
            for i, s in enumerate(stmts):
                if i == len(stmts) - 1 and isinstance(s, ast.ExprStmt):
                    t = self._infer(s.expr, bscope, expected)
                    if _is_diverging(s.expr):
                        return (_DIVERGE, None)
                    return (t, s.expr)
                self._check_stmt(s, bscope, self._current_ret)
            if _block_returns(body):
                return (_DIVERGE, None)
            return (None, None)
        t = self._infer(body, scope, expected)
        if _is_diverging(body):
            return (_DIVERGE, None)
        return (t, body)

    def _unify_match_result(self, bodies) -> Type:
        types = [t for t, _ in bodies]
        first = types[0]
        if all(t == first for t in types):
            return first
        if all(isinstance(t, IntType) for t in types):
            target = None
            for t, n in bodies:
                if not _is_flexible_int_lit(n):
                    target = t
                    break
            if target is None:
                target = INT
            for t, n in bodies:
                if t != target:
                    if _is_flexible_int_lit(n):
                        self._infer_int_lit(n, target)
                    else:
                        raise TypeCheckError(
                            f"match arms have incompatible types '{type_name(target)}' "
                            f"and '{type_name(t)}'",
                            n.line, n.column,
                        )
            return target
        for t, n in bodies:
            if t != first and n is not None:
                raise TypeCheckError(
                    f"match arms have incompatible types '{type_name(first)}' "
                    f"and '{type_name(t)}'",
                    n.line, n.column,
                )
        return first  # pragma: no cover

    # -- patterns ------------------------------------------------------------

    def _check_pattern(self, pat, t: Type, scope: _Scope) -> None:
        if isinstance(pat, ast.PatWildcard):
            return
        if isinstance(pat, ast.PatBinding):
            # a bare name equal to a no-payload variant of the scrutinee enum is
            # a variant test, not a binding (Rust-like).
            if isinstance(t, EnumType) and pat.name in self.enums[t.name]:
                payload = self.enums[t.name][pat.name]
                if payload:
                    raise TypeCheckError(
                        f"variant '{t.name}.{pat.name}' carries a payload; "
                        f"write '{pat.name}(...)' to match it",
                        pat.line, pat.column,
                    )
                pat.as_variant = (t.name, pat.name)
                return
            pat.resolved_type = t
            if not scope.define(pat.name, _Binding(t, mutable=False)):
                raise TypeCheckError(
                    f"'{pat.name}' is bound more than once in this pattern",
                    pat.line, pat.column,
                )
            return
        if isinstance(pat, ast.PatLiteral):
            hint = t if isinstance(t, (IntType, CharType)) else None
            lt = self._expect_value(pat.literal, scope, hint)
            if not isinstance(t, (IntType, CharType, BoolType, StrType)):
                raise TypeCheckError(
                    f"cannot match a literal against '{type_name(t)}'",
                    pat.line, pat.column,
                )
            if lt != t:
                raise TypeCheckError(
                    f"literal pattern of type '{type_name(lt)}' cannot match "
                    f"value of type '{type_name(t)}'",
                    pat.line, pat.column,
                )
            return
        if isinstance(pat, ast.PatEnum):
            self._check_enum_pattern(pat, t, scope)
            return
        if isinstance(pat, ast.PatTuple):
            if not isinstance(t, TupleType):
                raise TypeCheckError(
                    f"tuple pattern cannot match value of type '{type_name(t)}'",
                    pat.line, pat.column,
                )
            if len(pat.elems) != len(t.elems):
                raise TypeCheckError(
                    f"tuple pattern expects {len(t.elems)} element(s), "
                    f"got {len(pat.elems)}",
                    pat.line, pat.column,
                )
            for sub, et in zip(pat.elems, t.elems):
                self._check_pattern(sub, et, scope)
            return
        if isinstance(pat, ast.PatStruct):
            self._check_struct_pattern(pat, t, scope)
            return
        if isinstance(pat, ast.PatOr):
            self._check_or_pattern(pat, t, scope)
            return
        raise TypeCheckError(  # pragma: no cover - defensive
            "unsupported pattern", pat.line, pat.column
        )

    def _check_enum_pattern(self, pat: ast.PatEnum, t: Type, scope: _Scope) -> None:
        if not isinstance(t, EnumType):
            raise TypeCheckError(
                f"enum pattern cannot match value of type '{type_name(t)}'",
                pat.line, pat.column,
            )
        if pat.enum_name is not None and pat.enum_name != t.name:
            raise TypeCheckError(
                f"pattern names enum '{pat.enum_name}' but the value is '{t.name}'",
                pat.line, pat.column,
            )
        variants = self._enum_variant_types(t)
        if pat.variant not in variants:
            raise TypeCheckError(
                f"enum '{t.name}' has no variant '{pat.variant}'",
                pat.line, pat.column,
            )
        payload = variants[pat.variant]
        if pat.has_payload_syntax or pat.elems:
            if len(pat.elems) != len(payload):
                raise TypeCheckError(
                    f"variant '{t.name}.{pat.variant}' has {len(payload)} "
                    f"field(s), but the pattern binds {len(pat.elems)}",
                    pat.line, pat.column,
                )
            for sub, ft in zip(pat.elems, payload):
                self._check_pattern(sub, ft, scope)
        elif payload:
            raise TypeCheckError(
                f"variant '{t.name}.{pat.variant}' carries a payload; "
                f"write '{pat.variant}(...)' to match it",
                pat.line, pat.column,
            )
        pat.resolved_enum = t.name

    def _check_struct_pattern(self, pat: ast.PatStruct, t: Type, scope: _Scope) -> None:
        if not isinstance(t, StructType):
            raise TypeCheckError(
                f"struct pattern cannot match value of type '{type_name(t)}'",
                pat.line, pat.column,
            )
        if pat.type_name != t.name:
            raise TypeCheckError(
                f"pattern names struct '{pat.type_name}' but the value is '{t.name}'",
                pat.line, pat.column,
            )
        fields = self._struct_field_types(t)
        seen: set[str] = set()
        for fp in pat.fields:
            if fp.name in seen:
                raise TypeCheckError(
                    f"field '{fp.name}' bound more than once in struct pattern",
                    fp.line, fp.column,
                )
            seen.add(fp.name)
            if fp.name not in fields:
                raise TypeCheckError(
                    f"struct '{t.name}' has no field '{fp.name}'",
                    fp.line, fp.column,
                )
            self._check_pattern(fp.pattern, fields[fp.name], scope)

    def _check_or_pattern(self, pat: ast.PatOr, t: Type, scope: _Scope) -> None:
        name_maps: list[dict[str, Type]] = []
        for alt in pat.alts:
            tmp = _Scope()
            self._check_pattern(alt, t, tmp)
            name_maps.append({n: b.type for n, b in tmp.names.items()})
        base = name_maps[0]
        for m in name_maps[1:]:
            if m != base:
                raise TypeCheckError(
                    "all alternatives of an or-pattern must bind the same names "
                    "with the same types",
                    pat.line, pat.column,
                )
        for n, ty in base.items():
            if not scope.define(n, _Binding(ty, mutable=False)):
                raise TypeCheckError(
                    f"'{n}' is bound more than once in this pattern",
                    pat.line, pat.column,
                )

    # -- exhaustiveness & redundancy -----------------------------------------

    def _check_exhaustive(self, expr: ast.Match, st: Type) -> None:
        arms = [a for a in expr.arms if a.guard is None]
        if any(self._irrefutable(a.pattern, st) for a in arms):
            return
        if isinstance(st, EnumType):
            covered: set[str] = set()
            for a in arms:
                covered |= self._covered_variants(a.pattern, st)
            missing = [v for v in self.enums[st.name] if v not in covered]
            if missing:
                raise TypeCheckError(
                    f"non-exhaustive match on '{st.name}': missing variant(s) "
                    f"{', '.join(missing)} (add them or a '_' arm)",
                    expr.line, expr.column,
                )
            return
        if isinstance(st, BoolType):
            seen: set[bool] = set()
            for a in arms:
                if isinstance(a.pattern, ast.PatLiteral):
                    seen.add(bool(_const_bool(a.pattern.literal)))
            if {True, False} <= seen:
                return
            raise TypeCheckError(
                "non-exhaustive match on 'bool': cover both true and false "
                "(or add a '_' arm)",
                expr.line, expr.column,
            )
        raise TypeCheckError(
            f"non-exhaustive match on '{type_name(st)}': add a '_' arm",
            expr.line, expr.column,
        )

    def _covered_variants(self, pat, st: "EnumType") -> set[str]:
        if self._irrefutable(pat, st):
            return set(self.enums[st.name])
        if isinstance(pat, ast.PatOr):
            out: set[str] = set()
            for alt in pat.alts:
                out |= self._covered_variants(alt, st)
            return out
        if isinstance(pat, ast.PatBinding) and getattr(pat, "as_variant", None):
            return {pat.as_variant[1]}
        if isinstance(pat, ast.PatEnum):
            payload = self._enum_variant_types(st)[pat.variant]
            if all(self._irrefutable(sub, ft) for sub, ft in zip(pat.elems, payload)):
                return {pat.variant}
        return set()

    def _irrefutable(self, pat, t: Type) -> bool:
        if isinstance(pat, ast.PatWildcard):
            return True
        if isinstance(pat, ast.PatBinding):
            return getattr(pat, "as_variant", None) is None
        if isinstance(pat, ast.PatTuple) and isinstance(t, TupleType):
            return all(self._irrefutable(s, et) for s, et in zip(pat.elems, t.elems))
        if isinstance(pat, ast.PatStruct) and isinstance(t, StructType):
            fields = self._struct_field_types(t)
            return all(self._irrefutable(fp.pattern, fields[fp.name]) for fp in pat.fields)
        if isinstance(pat, ast.PatEnum) and isinstance(t, EnumType):
            if len(self.enums[t.name]) == 1:
                payload = self._enum_variant_types(t)[pat.variant]
                return all(self._irrefutable(s, ft) for s, ft in zip(pat.elems, payload))
        if isinstance(pat, ast.PatOr):
            return any(self._irrefutable(a, t) for a in pat.alts)
        return False

    def _check_redundant(self, expr: ast.Match, st: Type) -> None:
        saw_irrefutable = False
        covered: set[str] = set()
        for arm in expr.arms:
            if saw_irrefutable:
                raise TypeCheckError(
                    "unreachable match arm (a previous arm already matches "
                    "everything)",
                    arm.line, arm.column,
                )
            if arm.guard is not None:
                continue
            if isinstance(st, EnumType):
                vs = self._covered_variants(arm.pattern, st)
                if vs and vs <= covered:
                    raise TypeCheckError(
                        "unreachable match arm (its variant(s) are already covered)",
                        arm.line, arm.column,
                    )
                covered |= vs
            if self._irrefutable(arm.pattern, st):
                saw_irrefutable = True

    def _infer_int_lit(self, expr: ast.IntLit, expected: Type | None) -> Type:
        if expr.is_char:
            # A char literal defaults to `char` (D25), but an ASCII scalar stays
            # flexible to an integer type when one is expected (D42 byte compat).
            if isinstance(expected, IntType) and expr.value <= 0x7F:
                t = expected
            else:
                expr.resolved_type = CHAR
                return CHAR
        elif expr.suffix is not None:
            t = _SUFFIX_TYPES[expr.suffix]
        elif isinstance(expected, IntType):
            t = expected
        else:
            t = INT
        assert isinstance(t, IntType)
        if not int_fits(expr.value, t):
            raise TypeCheckError(
                f"integer literal {expr.value} does not fit in '{type_name(t)}'",
                expr.line, expr.column,
            )
        expr.resolved_type = t
        return t

    def _infer_float_lit(self, expr: ast.FloatLit, expected: Type | None) -> Type:
        if expr.suffix is not None:
            t = _FLOAT_SUFFIX_TYPES[expr.suffix]
        elif isinstance(expected, FloatType):
            t = expected
        else:
            t = FLOAT   # unsuffixed default: float32 (= `float`), D19/D56
        assert isinstance(t, FloatType)
        expr.resolved_type = t
        return t

    def _infer_name(self, expr: ast.Name, scope: _Scope,
                    expected: Type | None = None) -> Type:
        if expr.ident == "_":
            raise TypeCheckError(
                "'_' placeholder is only valid as a call argument",
                expr.line, expr.column,
            )
        binding = scope.lookup(expr.ident)
        if binding is None:
            if expr.ident in self._const_decls:
                info = self._ensure_const(expr.ident)
                expr.const_ref = expr.ident
                expr.resolved_type = info.type
                return info.type
            enum_name = _PRELUDE_VARIANTS.get(expr.ident)
            if enum_name is not None:
                return self._infer_bare_variant(expr, enum_name, expr.ident, expected)
            if expr.ident in self.functions and "." not in expr.ident:
                return self._infer_fun_value(expr, expected)
            if expr.ident in self.functions or expr.ident in _BUILTIN_FUNCS:
                raise TypeCheckError(
                    f"'{expr.ident}' cannot be used as a value here",
                    expr.line, expr.column,
                )
            raise TypeCheckError(f"unknown name '{expr.ident}'", expr.line, expr.column)
        self._record_capture(expr.ident, binding.type, scope)
        expr.resolved_type = binding.type
        return binding.type

    def _infer_fun_value(self, expr: ast.Name, expected: Type | None) -> Type:
        """A top-level `fun` referenced as a value becomes a function value with
        an empty environment (v0.4.2). Generic functions have no single concrete
        type, so they cannot be referenced this way."""
        sig = self.functions[expr.ident]
        if sig.type_params:
            raise TypeCheckError(
                f"generic function '{expr.ident}' cannot be used as a value "
                f"(its type parameters are unresolved)",
                expr.line, expr.column,
            )
        ft = FuncType(tuple(sig.params), sig.ret)
        expr.func_ref = expr.ident
        expr.resolved_type = ft
        return ft

    def _record_capture(self, name: str, t: Type, scope: _Scope) -> None:
        """If `name` resolves to a binding outside one or more enclosing lambdas,
        record it as a by-value capture for each such lambda (v0.4.2)."""
        if not self._lambda_stack:
            return
        def_scope = scope.lookup_scope(name)
        if def_scope is None:
            return
        for ctx in self._lambda_stack:
            if _is_strict_ancestor(def_scope, ctx.boundary):
                ctx.add(name, t)

    def _infer_bare_variant(self, expr: ast.Expr, enum_name: str, variant: str,
                            expected: Type | None) -> Type:
        """A bare prelude variant used as a value (`None`). Variants with a
        payload must be *called* (`Some(x)`), so reject them here."""
        payload = self.enums[enum_name][variant]
        if payload:
            raise TypeCheckError(
                f"variant '{variant}' carries a payload; call it like '{variant}(...)'",
                expr.line, expr.column,
            )
        params = self.enum_decls[enum_name].type_params
        if (isinstance(expected, EnumType) and expected.name == enum_name
                and len(expected.args) == len(params)):
            et: Type = expected
        else:
            raise TypeCheckError(
                f"cannot infer type argument(s) for '{variant}'; annotate the "
                f"binding (e.g. ': {enum_name}<...>')",
                expr.line, expr.column,
            )
        expr.enum_ctor = (enum_name, variant)
        expr.resolved_type = et
        return et

    def _infer_unary(self, expr: ast.Unary, scope: _Scope, expected: Type | None) -> Type:
        if expr.op == "-":
            t = self._expect_value(
                expr.operand, scope,
                expected if isinstance(expected, (IntType, FloatType)) else None)
            if not isinstance(t, (IntType, FloatType)):
                raise TypeCheckError(
                    "unary '-' requires a numeric operand", expr.line, expr.column)
            expr.resolved_type = t
            return t
        if expr.op == "!":
            self._expect_type(expr.operand, scope, BOOL, "operand of '!'")
            expr.resolved_type = BOOL
            return BOOL
        if expr.op == "~":
            t = self._expect_value(expr.operand, scope, expected if isinstance(expected, IntType) else None)
            if not isinstance(t, IntType):
                raise TypeCheckError("unary '~' requires an integer", expr.line, expr.column)
            expr.resolved_type = t
            return t
        raise TypeCheckError(f"unknown unary operator '{expr.op}'", expr.line, expr.column)

    def _infer_binary(self, expr: ast.Binary, scope: _Scope, expected: Type | None) -> Type:
        op = expr.op
        if op in ("&&", "||"):
            self._expect_type(expr.left, scope, BOOL, f"operand of '{op}'")
            self._expect_type(expr.right, scope, BOOL, f"operand of '{op}'")
            expr.resolved_type = BOOL
            return BOOL

        if op in ("==", "!="):
            lt = self._expect_value(expr.left, scope, None)
            # A struct/enum equality desugars to its `Eq::eq` method (D52, lifting
            # the v0.2 D37 restriction for types that implement `Eq`).
            if isinstance(lt, (StructType, EnumType)):
                return self._infer_operator_overload(expr, scope, op, lt)
            if isinstance(lt, TypeParam):
                return self._infer_bounded_op(expr, scope, op, lt)
            rt = self._expect_value(
                expr.right, scope,
                lt if isinstance(lt, (IntType, FloatType)) else None)
            common = self._unify(expr.left, lt, expr.right, rt)
            if not isinstance(common, (IntType, FloatType, CharType, BoolType, StrType)):
                raise TypeCheckError(
                    f"cannot compare values of type '{type_name(common)}'",
                    expr.line, expr.column,
                )
            expr.resolved_type = BOOL
            return BOOL

        if op in ("<", "<=", ">", ">="):
            lt = self._expect_value(expr.left, scope, None)
            if isinstance(lt, (StructType, EnumType)):
                return self._infer_operator_overload(expr, scope, op, lt)
            if isinstance(lt, TypeParam):
                return self._infer_bounded_op(expr, scope, op, lt)
            rt = self._expect_value(
                expr.right, scope,
                lt if isinstance(lt, (IntType, FloatType)) else None)
            common = self._unify(expr.left, lt, expr.right, rt)
            if not isinstance(common, (IntType, FloatType, CharType)):
                raise TypeCheckError(
                    "comparison requires numeric or char operands",
                    expr.line, expr.column)
            expr.resolved_type = BOOL
            return BOOL

        if op in ("<<", ">>"):
            # The result takes the left operand's type; the shift amount is an
            # independent integer (any width), so the operands are not unified.
            hint = expected if isinstance(expected, IntType) else None
            lt = self._expect_value(expr.left, scope, hint)
            # `>>` is operand-typed (D24): two function values compose; otherwise
            # it is the integer right shift.
            if op == ">>" and isinstance(lt, FuncType):
                return self._infer_compose(expr, scope, lt)
            if not isinstance(lt, IntType):
                raise TypeCheckError(
                    f"operator '{op}' requires an integer left operand",
                    expr.line, expr.column,
                )
            rt = self._expect_value(expr.right, scope, None)
            if not isinstance(rt, IntType):
                raise TypeCheckError(
                    f"shift amount for '{op}' must be an integer",
                    expr.right.line, expr.right.column,
                )
            amount = _const_int(expr.right)
            if amount is not None and not (0 <= amount < lt.width):
                raise TypeCheckError(
                    f"shift amount {amount} is out of range for "
                    f"'{type_name(lt)}' (valid range is 0..{lt.width - 1})",
                    expr.right.line, expr.right.column,
                )
            expr.resolved_type = lt
            return lt

        # string concatenation: `str + str -> str` (D41). Allocates a fresh,
        # immutable string; checked before the integer-arithmetic path below.
        if op == "+":
            lt = self._expect_value(
                expr.left, scope,
                expected if isinstance(expected, (IntType, FloatType)) else None)
            if isinstance(lt, (StructType, EnumType)):
                return self._infer_operator_overload(expr, scope, op, lt)
            if isinstance(lt, TypeParam):
                return self._infer_bounded_op(expr, scope, op, lt)
            if isinstance(lt, StrType):
                rt = self._expect_value(expr.right, scope, None)
                if not isinstance(rt, StrType):
                    raise TypeCheckError(
                        f"cannot concatenate 'str' with '{type_name(rt)}'",
                        expr.line, expr.column,
                    )
                expr.resolved_type = STR
                return STR
            rt = self._expect_value(
                expr.right, scope,
                lt if isinstance(lt, (IntType, FloatType)) else None)
            common = self._unify(expr.left, lt, expr.right, rt)
            if not isinstance(common, (IntType, FloatType)):
                raise TypeCheckError(
                    f"operator '+' requires numeric or string operands",
                    expr.line, expr.column,
                )
            expr.resolved_type = common
            return common

        # arithmetic & bitwise: - * / %  and  & | ^
        hint = expected if isinstance(expected, (IntType, FloatType)) else None
        lt = self._expect_value(expr.left, scope, hint)
        # `- * / %` overload on user types (the bitwise `& | ^` do not, D52).
        if op in _ARITH_OP_TRAITS and isinstance(lt, (StructType, EnumType)):
            return self._infer_operator_overload(expr, scope, op, lt)
        if op in _ARITH_OP_TRAITS and isinstance(lt, TypeParam):
            return self._infer_bounded_op(expr, scope, op, lt)
        rt = self._expect_value(
            expr.right, scope,
            lt if isinstance(lt, (IntType, FloatType)) else hint)
        common = self._unify(expr.left, lt, expr.right, rt)
        if isinstance(common, FloatType):
            # Floats support `+ - * / %` (D56) but not the bitwise operators.
            if op not in _ARITH_OP_TRAITS:
                raise TypeCheckError(
                    f"operator '{op}' is not defined for floats", expr.line, expr.column
                )
            expr.resolved_type = common
            return common
        if not isinstance(common, IntType):
            raise TypeCheckError(
                f"operator '{op}' requires integer operands", expr.line, expr.column
            )
        expr.resolved_type = common
        return common

    def _infer_compose(self, expr: ast.Binary, scope: _Scope,
                       lt: "FuncType") -> Type:
        """`a >> b` composes two one-argument function values left-to-right
        (D24): it desugars to `(x) => b(a(x))`. With `a: (A) -> B` and
        `b: (B) -> C` the result is `(A) -> C`; `a` and `b` are captured by
        value (inlined into the lambda body)."""
        if len(lt.params) != 1:
            raise TypeCheckError(
                f"composition with '>>' needs a one-argument function on the "
                f"left, found '{type_name(lt)}'",
                expr.line, expr.column,
            )
        rt = self._expect_value(expr.right, scope, None)
        if not isinstance(rt, FuncType):
            raise TypeCheckError(
                f"cannot compose a function with a value of type "
                f"'{type_name(rt)}' (both operands of '>>' must be functions, or "
                f"both integers)",
                expr.line, expr.column,
            )
        if len(rt.params) != 1:
            raise TypeCheckError(
                f"composition with '>>' needs a one-argument function on the "
                f"right, found '{type_name(rt)}'",
                expr.line, expr.column,
            )
        if lt.ret != rt.params[0]:
            raise TypeCheckError(
                f"cannot compose '{type_name(lt)}' with '{type_name(rt)}': the "
                f"left result '{type_name(lt.ret)}' must match the right "
                f"parameter '{type_name(rt.params[0])}'",
                expr.line, expr.column,
            )
        ln, col = expr.line, expr.column
        x = ast.Name("__x").at(ln, col)
        inner = ast.Call(expr.left, [x]).at(ln, col)
        body = ast.Call(expr.right, [inner]).at(ln, col)
        ann = _type_to_typeexpr(lt.params[0])
        lam = ast.Lambda([ast.Param("__x", ann).at(ln, col)], body).at(ln, col)
        ft = self._infer_lambda(lam, scope, None)
        expr.desugared = lam
        expr.resolved_type = ft
        return ft

    def _infer_operator_overload(self, expr: ast.Binary, scope: _Scope,
                                 op: str, lt: Type) -> Type:
        """Desugar `a OP b` on a user type `lt` to its operator-trait method
        (D52). `+ - * / %` → `a.add(b)` etc. (result `Self`); `== !=` →
        `a.eq(b)` (negated for `!=`); `< <= > >=` → `a.cmp(b) OP 0`. The
        operand type must implement the backing trait and both operands must
        share the type (D4)."""
        if op in ("==", "!="):
            trait, method, kind = "Eq", "eq", "eq"
        elif op in ("<", "<=", ">", ">="):
            trait, method, kind = "Ord", "cmp", "ord"
        else:
            trait, method = _ARITH_OP_TRAITS[op]
            kind = "arith"
        if not self._type_implements(lt, trait):
            hint = " (or '#derive(Eq)')" if trait == "Eq" else ""
            raise TypeCheckError(
                f"operator '{op}' is not defined for '{type_name(lt)}': it needs "
                f"'impl {trait} for {type_name(lt)}'{hint}",
                expr.line, expr.column,
            )
        rt = self._expect_value(expr.right, scope, None)
        if lt != rt:
            raise TypeCheckError(
                f"operator '{op}' requires both operands to have the same type, "
                f"found '{type_name(lt)}' and '{type_name(rt)}'",
                expr.line, expr.column,
            )
        ln, col = expr.line, expr.column
        call = ast.Call(
            ast.FieldAccess(expr.left, method).at(ln, col), [expr.right]
        ).at(ln, col)
        if kind == "arith":
            ret = self._infer_call(call, scope)
            expr.desugared = call
            expr.resolved_type = ret
            return ret
        if kind == "eq":
            self._infer_call(call, scope)  # `eq` returns bool
            if op == "==":
                node: ast.Expr = call
            else:
                node = ast.Unary("!", call).at(ln, col)
                node.resolved_type = BOOL
            expr.desugared = node
            expr.resolved_type = BOOL
            return BOOL
        # ord: compare the sign of `a.cmp(b)` against 0 with the same operator
        self._infer_call(call, scope)  # `cmp` returns int
        node = ast.Binary(op, call, ast.IntLit(0).at(ln, col)).at(ln, col)
        self._infer_binary(node, scope, None)
        expr.desugared = node
        expr.resolved_type = BOOL
        return BOOL

    def _infer_bounded_op(self, expr: ast.Binary, scope: _Scope,
                          op: str, lt: TypeParam) -> Type:
        """An overloadable operator on a type-parameter value (X9): allowed only
        if the parameter carries the backing trait bound. The node is *not*
        desugared — the interpreter dispatches at runtime on the erased value,
        and monomorphization re-checks the concrete body (where the operand is a
        real type and the operator desugars normally)."""
        if op in ("==", "!="):
            trait, result = "Eq", BOOL
        elif op in ("<", "<=", ">", ">="):
            trait, result = "Ord", BOOL
        else:
            trait, result = _ARITH_OP_TRAITS[op][0], lt
        if trait not in self._type_param_bounds.get(lt.name, frozenset()):
            raise TypeCheckError(
                f"operator '{op}' on a value of type parameter '{lt.name}' "
                f"requires the bound '{lt.name}: {trait}'",
                expr.line, expr.column,
            )
        rt = self._expect_value(expr.right, scope, None)
        if lt != rt:
            raise TypeCheckError(
                f"operator '{op}' requires both operands to have the same type, "
                f"found '{type_name(lt)}' and '{type_name(rt)}'",
                expr.line, expr.column,
            )
        expr.resolved_type = result
        return result

    def _infer_cast(self, expr: ast.Cast, scope: _Scope) -> Type:
        target = self._resolve(expr.target)
        # Don't hint the operand with the target: `300 as uint8` should infer the
        # source as its natural type (int32) and then wrap, not reject 300.
        src = self._expect_value(expr.operand, scope, None)
        # `as` converts between numeric scalars: int↔int (wrap), int↔float (round /
        # truncate-toward-zero), float↔float (widen / round) — D26/D56 — plus
        # `char`↔integer (codepoint), but not `char`↔float directly (D25).
        scalar = (IntType, FloatType, CharType)
        if not isinstance(src, scalar) or not isinstance(target, scalar):
            raise TypeCheckError(
                f"cannot cast from '{type_name(src)}' to '{type_name(target)}' "
                "('as' converts between numeric and char types only)",
                expr.line, expr.column,
            )
        if ((isinstance(src, CharType) and isinstance(target, FloatType))
                or (isinstance(src, FloatType) and isinstance(target, CharType))):
            raise TypeCheckError(
                "cannot cast directly between 'char' and a float "
                "(go through an integer type)",
                expr.line, expr.column,
            )
        expr.resolved_type = target
        return target

    def _unify(self, ln: ast.Expr, lt: Type, rn: ast.Expr, rt: Type) -> Type:
        if lt == rt:
            return lt
        # An ASCII char literal that defaulted to `char` can still adopt an
        # integer type for byte comparisons like `'a' == s[i]` (D42).
        if isinstance(rt, IntType) and _is_flexible_char_lit(ln) and ln.value <= 0x7F:
            lt = self._infer_int_lit(ln, rt)
        elif isinstance(lt, IntType) and _is_flexible_char_lit(rn) and rn.value <= 0x7F:
            rt = self._infer_int_lit(rn, lt)
        if lt == rt:
            return lt
        if isinstance(lt, IntType) and isinstance(rt, IntType):
            if _is_flexible_int_lit(ln):
                lt = self._infer_int_lit(ln, rt)  # adopt rt
            elif _is_flexible_int_lit(rn):
                rt = self._infer_int_lit(rn, lt)  # adopt lt
            if lt == rt:
                return lt
        if isinstance(lt, FloatType) and isinstance(rt, FloatType):
            if _is_flexible_float_lit(ln):
                lt = self._infer_float_lit(ln, rt)  # adopt rt
            elif _is_flexible_float_lit(rn):
                rt = self._infer_float_lit(rn, lt)  # adopt lt
            if lt == rt:
                return lt
        raise TypeCheckError(
            f"type mismatch: '{type_name(lt)}' vs '{type_name(rt)}' "
            "(no implicit conversion between numeric types)",
            ln.line, ln.column,
        )

    def _infer_intrinsic(self, expr: ast.Call, name: str,
                         scope: _Scope) -> Type | None:
        """`assert(cond[, msg])`, `panic(msg)`, `unreachable()` (D-, §7).

        All produce no value; `panic`/`unreachable` additionally diverge (handled
        by `_is_diverging`, so they satisfy a missing return / match arm)."""
        if name == "assert":
            if len(expr.args) not in (1, 2):
                raise TypeCheckError(
                    "assert() takes a condition and an optional message",
                    expr.line, expr.column,
                )
            self._expect_type(expr.args[0], scope, BOOL, "assert condition")
            if len(expr.args) == 2:
                self._expect_type(expr.args[1], scope, STR, "assert message")
        elif name == "panic":
            if len(expr.args) != 1:
                raise TypeCheckError("panic() takes exactly one message",
                                     expr.line, expr.column)
            self._expect_type(expr.args[0], scope, STR, "panic message")
        else:  # unreachable
            if expr.args:
                raise TypeCheckError("unreachable() takes no arguments",
                                     expr.line, expr.column)
        expr.resolved_type = None
        return None

    def _infer_list_mutation(self, expr: ast.Call, name: str,
                             scope: _Scope) -> Type | None:
        """`push(xs, v)` / `pop(xs)`: the first argument must be a mutable list
        lvalue (W3/D40). Returns `()` for push and the element type for pop."""
        nargs = 2 if name == "push" else 1
        if len(expr.args) != nargs:
            raise TypeCheckError(
                f"{name}() takes {nargs} argument(s)", expr.line, expr.column)
        lst_t, mutable = self._check_lvalue(expr.args[0], scope)
        if not isinstance(lst_t, ListType):
            raise TypeCheckError(
                f"{name}() requires a list, found '{type_name(lst_t)}'",
                expr.args[0].line, expr.args[0].column,
            )
        if not mutable:
            raise TypeCheckError(
                f"{name}() needs a mutable list (declare it with 'var')",
                expr.args[0].line, expr.args[0].column,
            )
        if name == "push":
            self._expect_type(expr.args[1], scope, lst_t.elem, "push value")
            expr.resolved_type = None
            return None
        expr.resolved_type = lst_t.elem
        return lst_t.elem

    def _infer_map_builtin(self, expr: ast.Call, name: str,
                           scope: _Scope) -> Type | None:
        """`contains(m, k) -> bool`, `keys(m) -> [K]`, `remove(m, k)`. `remove`
        mutates, so its map must be a mutable lvalue (W3/D40)."""
        nargs = 1 if name == "keys" else 2
        if len(expr.args) != nargs:
            raise TypeCheckError(
                f"{name}() takes {nargs} argument(s)", expr.line, expr.column)
        if name == "remove":
            map_t, mutable = self._check_lvalue(expr.args[0], scope)
        else:
            map_t = self._expect_value(expr.args[0], scope, None)
            mutable = True
        if not isinstance(map_t, MapType):
            raise TypeCheckError(
                f"{name}() requires a map, found '{type_name(map_t)}'",
                expr.args[0].line, expr.args[0].column,
            )
        if name == "keys":
            t = ListType(map_t.key)
            expr.resolved_type = t
            return t
        self._expect_type(expr.args[1], scope, map_t.key, "map key")
        if name == "contains":
            expr.resolved_type = BOOL
            return BOOL
        if not mutable:                       # remove
            raise TypeCheckError(
                "remove() needs a mutable map (declare it with 'var')",
                expr.args[0].line, expr.args[0].column,
            )
        expr.resolved_type = None
        return None

    def _infer_format(self, expr: ast.Call, scope: _Scope) -> Type:
        """`format(fmt, args…) -> str`: `fmt` must be a string literal so the
        placeholder count is checked at compile time (`{}` is a hole, `{{`/`}}`
        are literal braces). Each argument is rendered by its type's `print`
        form, so it must be an int/bool/str."""
        if not expr.args:
            raise TypeCheckError(
                "format() needs a string literal format and its arguments",
                expr.line, expr.column,
            )
        fmt = expr.args[0]
        if not isinstance(fmt, ast.StrLit):
            raise TypeCheckError(
                "format()'s first argument must be a string literal",
                fmt.line, fmt.column,
            )
        holes = _count_format_holes(fmt.value, fmt.line, fmt.column)
        rest = expr.args[1:]
        if holes != len(rest):
            raise TypeCheckError(
                f"format() has {holes} placeholder(s) but {len(rest)} "
                f"argument(s)",
                expr.line, expr.column,
            )
        for arg in rest:
            at = self._expect_value(arg, scope, None)
            if not isinstance(at, (IntType, FloatType, CharType, BoolType, StrType)):
                raise TypeCheckError(
                    f"format() cannot render a value of type '{type_name(at)}'",
                    arg.line, arg.column,
                )
        expr.resolved_type = STR
        return STR

    def _infer_string_builder(self, expr: ast.Call, name: str,
                              scope: _Scope) -> Type | None:
        """The `StringBuilder` toolkit (D41): `StringBuilder()` makes an empty
        buffer; `append(sb, s)` / `append_byte(sb, b)` mutate it (so `sb` must be
        a mutable lvalue); `build(sb) -> str` snapshots it as an immutable
        string."""
        if name == "StringBuilder":
            if expr.args:
                raise TypeCheckError("StringBuilder() takes no arguments",
                                     expr.line, expr.column)
            expr.resolved_type = STRING_BUILDER
            return STRING_BUILDER
        if name == "build":
            if len(expr.args) != 1:
                raise TypeCheckError("build() takes exactly one argument",
                                     expr.line, expr.column)
            at = self._expect_value(expr.args[0], scope, None)
            if not isinstance(at, StringBuilderType):
                raise TypeCheckError(
                    f"build() requires a StringBuilder, found '{type_name(at)}'",
                    expr.args[0].line, expr.args[0].column,
                )
            expr.resolved_type = STR
            return STR
        # append / append_byte: mutate the builder in place
        if len(expr.args) != 2:
            raise TypeCheckError(f"{name}() takes 2 argument(s)",
                                 expr.line, expr.column)
        sb_t, mutable = self._check_lvalue(expr.args[0], scope)
        if not isinstance(sb_t, StringBuilderType):
            raise TypeCheckError(
                f"{name}() requires a StringBuilder, found '{type_name(sb_t)}'",
                expr.args[0].line, expr.args[0].column,
            )
        if not mutable:
            raise TypeCheckError(
                f"{name}() needs a mutable StringBuilder (declare it with 'var')",
                expr.args[0].line, expr.args[0].column,
            )
        if name == "append":
            self._expect_type(expr.args[1], scope, STR, "append value")
        else:  # append_byte
            self._expect_type(expr.args[1], scope, BYTE, "append_byte value")
        expr.resolved_type = None
        return None

    def _infer_method_call(self, expr: ast.Call, scope: _Scope,
                           expected: Type | None = None) -> Type | None:
        """Resolve `recv.method(args)` (v0.4.1). The receiver becomes the hidden
        `self` argument; the call node is annotated with the lowered function name
        and the receiver mutability so the backends can dispatch it."""
        callee = expr.callee
        recv = callee.target
        recv_type = self._expect_value(recv, scope, None)
        key = self._method_key(recv_type)
        table = self.methods.get(key) if key is not None else None
        sig = table.get(callee.field_name) if table else None
        if sig is None:
            # Fallback: a struct field holding a function value, called directly
            # (`obj.callback(x)`); treat it as an indirect call (v0.4.2).
            if (isinstance(recv_type, StructType)
                    and callee.field_name in self.structs.get(recv_type.name, {})):
                field_t = self._struct_field_types(recv_type).get(callee.field_name)
                if isinstance(field_t, FuncType):
                    return self._infer_indirect_call(expr, scope)
            raise TypeCheckError(
                f"type '{type_name(recv_type)}' has no method "
                f"'{callee.field_name}'",
                expr.line, expr.column,
            )
        is_var_self = (sig.decl.receiver == "var self")
        if is_var_self:
            if not _is_lvalue_shape(recv):
                raise TypeCheckError(
                    f"method '{callee.field_name}' mutates its receiver ('var "
                    "self'); it needs a mutable variable (or one of its "
                    "fields/elements), not a temporary",
                    expr.line, expr.column,
                )
            _, mutable = self._check_lvalue(recv, scope)
            if not mutable:
                raise TypeCheckError(
                    f"cannot call the mutating method '{callee.field_name}' on an "
                    "immutable receiver (declare it with 'var')",
                    expr.line, expr.column,
                )
        nargs = len(sig.params) - 1
        if len(expr.args) != nargs:
            raise TypeCheckError(
                f"method '{callee.field_name}' expects {nargs} argument(s), "
                f"got {len(expr.args)}",
                expr.line, expr.column,
            )
        expr.method_func = f"{key}.{callee.field_name}"
        expr.method_is_var_self = is_var_self
        if sig.type_params:
            return self._infer_generic_method(expr, sig, recv_type, scope)
        for arg, ptype in zip(expr.args, sig.params[1:]):
            at = self._expect_value(arg, scope, ptype)
            if at != ptype:
                raise TypeCheckError(
                    f"argument type mismatch in call to '{callee.field_name}': "
                    f"expected '{type_name(ptype)}', found '{type_name(at)}'",
                    arg.line, arg.column,
                )
        expr.resolved_type = sig.ret
        return sig.ret

    def _infer_generic_method(self, expr: ast.Call, sig: FuncSig,
                              recv_type: Type, scope: _Scope) -> Type | None:
        """Infer a generic method's type arguments (D45 + D34): solve the impl's
        (and method's) type parameters from the receiver type and the arguments,
        then record them in `expr.type_args` for monomorphization."""
        method = expr.callee.field_name
        subst: dict[str, Type] = {}
        # The receiver pins the impl's type parameters (e.g. `Box<int>` → T=int).
        self._unify_param(sig.params[0], recv_type, subst)
        arg_types: list[Type] = []
        for arg, ptype in zip(expr.args, sig.params[1:]):
            want = self._subst_type(ptype, subst)
            hint = want if not self._contains_type_param(want) else None
            at = self._expect_value(arg, scope, hint)
            arg_types.append(at)
            self._unify_param(ptype, at, subst)
        missing = [tp for tp in sig.type_params if tp not in subst]
        if missing:
            raise TypeCheckError(
                f"cannot infer type parameter(s) {', '.join(missing)} for method "
                f"'{method}'; add a type annotation to guide inference",
                expr.line, expr.column,
            )
        for arg, ptype, at in zip(expr.args, sig.params[1:], arg_types):
            want = self._subst_type(ptype, subst)
            if at != want:
                if isinstance(want, IntType) and _is_flexible_int_lit(arg):
                    self._infer_int_lit(arg, want)
                else:
                    raise TypeCheckError(
                        f"argument type mismatch in call to '{method}': expected "
                        f"'{type_name(want)}', found '{type_name(at)}'",
                        arg.line, arg.column,
                    )
        expr.type_args = tuple(subst[tp] for tp in sig.type_params)
        self._check_call_bounds(sig, subst, expr)
        ret = self._subst_type(sig.ret, subst) if sig.ret is not None else None
        expr.resolved_type = ret
        return ret

    def _infer_call(self, expr: ast.Call, scope: _Scope,
                    expected: Type | None = None) -> Type | None:
        # A call carrying `_` holes is a partial application (X7): it desugars to
        # a lambda over the holes, with the filled arguments captured by value.
        if any(isinstance(a, ast.Hole) for a in expr.args):
            return self._infer_partial(expr, scope)
        callee = expr.callee
        # A local binding shadows any global function and is called as a value.
        if isinstance(callee, ast.Name) and scope.lookup(callee.ident) is not None:
            return self._infer_indirect_call(expr, scope)
        # `Enum.Variant(args...)` variant construction, else a method call (with
        # a fallback to calling a function-typed field as a value).
        if isinstance(callee, ast.FieldAccess):
            enum_name = self._enum_name_ref(callee.target, scope)
            if enum_name is not None:
                return self._infer_variant_ctor(expr, enum_name, callee.field_name,
                                                scope, expected)
            return self._infer_method_call(expr, scope, expected)
        # Any other expression callee (`get_fn()(x)`, `fns[0](x)`, a lambda
        # applied in place) is an indirect call through a function value.
        if not isinstance(callee, ast.Name):
            return self._infer_indirect_call(expr, scope)
        name = callee.ident
        if name == "print":
            if len(expr.args) != 1:
                raise TypeCheckError("print() takes exactly one argument",
                                     expr.line, expr.column)
            at = self._expect_value(expr.args[0], scope, None)
            if not isinstance(at, (IntType, FloatType, CharType, BoolType, StrType)):
                raise TypeCheckError(
                    f"print() cannot print a value of type '{type_name(at)}'",
                    expr.line, expr.column,
                )
            expr.resolved_type = None
            return None
        if name == "__write":
            if len(expr.args) != 2:
                raise TypeCheckError("__write() takes (fd: int32, s: str)",
                                     expr.line, expr.column)
            fd_t = self._expect_value(expr.args[0], scope, INT)
            if not isinstance(fd_t, IntType):
                raise TypeCheckError(
                    f"__write() fd must be an integer, found '{type_name(fd_t)}'",
                    expr.line, expr.column,
                )
            s_t = self._expect_value(expr.args[1], scope, STR)
            if not isinstance(s_t, StrType):
                raise TypeCheckError(
                    f"__write() expects a string, found '{type_name(s_t)}'",
                    expr.line, expr.column,
                )
            expr.resolved_type = None
            return None
        if name == "__exit":
            if len(expr.args) != 1:
                raise TypeCheckError("__exit() takes exactly one argument",
                                     expr.line, expr.column)
            code_t = self._expect_value(expr.args[0], scope, INT)
            if not isinstance(code_t, IntType):
                raise TypeCheckError(
                    f"__exit() code must be an integer, found "
                    f"'{type_name(code_t)}'",
                    expr.line, expr.column,
                )
            expr.resolved_type = None
            return None
        if name == "__args":
            if expr.args:
                raise TypeCheckError("__args() takes no arguments",
                                     expr.line, expr.column)
            t = ListType(STR)
            expr.resolved_type = t
            return t
        if name == "__read_file":
            if len(expr.args) != 1:
                raise TypeCheckError("__read_file() takes exactly one argument",
                                     expr.line, expr.column)
            p_t = self._expect_value(expr.args[0], scope, STR)
            if not isinstance(p_t, StrType):
                raise TypeCheckError(
                    f"__read_file() expects a string path, found "
                    f"'{type_name(p_t)}'",
                    expr.line, expr.column,
                )
            expr.resolved_type = STR
            return STR
        if name == "__io_errno":
            if expr.args:
                raise TypeCheckError("__io_errno() takes no arguments",
                                     expr.line, expr.column)
            expr.resolved_type = INT
            return INT
        if name == "__write_file":
            if len(expr.args) != 2:
                raise TypeCheckError(
                    "__write_file() takes (path: str, contents: str)",
                    expr.line, expr.column)
            p_t = self._expect_value(expr.args[0], scope, STR)
            if not isinstance(p_t, StrType):
                raise TypeCheckError(
                    f"__write_file() path must be a string, found "
                    f"'{type_name(p_t)}'",
                    expr.line, expr.column,
                )
            c_t = self._expect_value(expr.args[1], scope, STR)
            if not isinstance(c_t, StrType):
                raise TypeCheckError(
                    f"__write_file() contents must be a string, found "
                    f"'{type_name(c_t)}'",
                    expr.line, expr.column,
                )
            expr.resolved_type = None
            return None
        if name == "__run":
            if len(expr.args) != 2:
                raise TypeCheckError(
                    "__run() takes (program: str, argv: [str])",
                    expr.line, expr.column)
            p_t = self._expect_value(expr.args[0], scope, STR)
            if not isinstance(p_t, StrType):
                raise TypeCheckError(
                    f"__run() program must be a string, found "
                    f"'{type_name(p_t)}'",
                    expr.line, expr.column,
                )
            a_t = self._expect_value(expr.args[1], scope, ListType(STR))
            if not (isinstance(a_t, ListType) and isinstance(a_t.elem, StrType)):
                raise TypeCheckError(
                    f"__run() argv must be a [str], found '{type_name(a_t)}'",
                    expr.line, expr.column,
                )
            t = ListType(BYTE)
            expr.resolved_type = t
            return t
        if name == "__run_stderr":
            if expr.args:
                raise TypeCheckError("__run_stderr() takes no arguments",
                                     expr.line, expr.column)
            t = ListType(BYTE)
            expr.resolved_type = t
            return t
        if name in ("__run_exit_code", "__run_signal", "__run_errno"):
            if expr.args:
                raise TypeCheckError(f"{name}() takes no arguments",
                                     expr.line, expr.column)
            expr.resolved_type = INT
            return INT
        if name == "len":
            if len(expr.args) != 1:
                raise TypeCheckError("len() takes exactly one argument",
                                     expr.line, expr.column)
            at = self._expect_value(expr.args[0], scope, None)
            if not isinstance(at, (ListType, MapType, StrType, StringBuilderType)):
                raise TypeCheckError(
                    f"len() requires a list, map, string, or StringBuilder, found "
                    f"'{type_name(at)}'",
                    expr.line, expr.column,
                )
            expr.resolved_type = INT
            return INT
        if name == "chars":
            if len(expr.args) != 1:
                raise TypeCheckError("chars() takes exactly one argument",
                                     expr.line, expr.column)
            at = self._expect_value(expr.args[0], scope, None)
            if not isinstance(at, StrType):
                raise TypeCheckError(
                    f"chars() requires a string, found '{type_name(at)}'",
                    expr.line, expr.column,
                )
            t = ListType(CHAR)
            expr.resolved_type = t
            return t
        if name in ("push", "pop"):
            return self._infer_list_mutation(expr, name, scope)
        if name in ("contains", "remove", "keys"):
            return self._infer_map_builtin(expr, name, scope)
        if name == "format":
            return self._infer_format(expr, scope)
        if name in ("StringBuilder", "append", "append_byte", "build"):
            return self._infer_string_builder(expr, name, scope)
        if name in _BUILTIN_FUNCS:  # assert / panic / unreachable
            return self._infer_intrinsic(expr, name, scope)
        sig = self.functions.get(name)
        if sig is None:
            enum_name = _PRELUDE_VARIANTS.get(name)
            if enum_name is not None and scope.lookup(name) is None:
                return self._infer_variant_ctor(expr, enum_name, name, scope, expected)
            raise TypeCheckError(f"unknown function '{name}'", expr.line, expr.column)
        if sig.type_params:
            return self._infer_generic_call(expr, name, sig, scope)
        if len(expr.args) != len(sig.params):
            raise TypeCheckError(
                f"function '{name}' expects {len(sig.params)} argument(s), "
                f"got {len(expr.args)}",
                expr.line, expr.column,
            )
        for arg, ptype in zip(expr.args, sig.params):
            at = self._expect_value(arg, scope, ptype)
            if at != ptype:
                raise TypeCheckError(
                    f"argument type mismatch in call to '{name}': expected "
                    f"'{type_name(ptype)}', found '{type_name(at)}'",
                    arg.line, arg.column,
                )
        expr.resolved_type = sig.ret
        return sig.ret

    def _infer_indirect_call(self, expr: ast.Call, scope: _Scope) -> Type | None:
        """Call a function value `f(args)` (v0.4.2): `f` is any expression of a
        function type (a `let`-bound lambda, a `fun` reference, a parameter, a
        returned function value, …)."""
        ft = self._expect_value(expr.callee, scope, None)
        if not isinstance(ft, FuncType):
            raise TypeCheckError(
                f"cannot call a value of type '{type_name(ft)}'",
                expr.line, expr.column,
            )
        if len(expr.args) != len(ft.params):
            raise TypeCheckError(
                f"this function value expects {len(ft.params)} argument(s), "
                f"got {len(expr.args)}",
                expr.line, expr.column,
            )
        for arg, ptype in zip(expr.args, ft.params):
            at = self._expect_value(arg, scope, ptype)
            if at != ptype:
                raise TypeCheckError(
                    f"argument type mismatch: expected '{type_name(ptype)}', "
                    f"found '{type_name(at)}'",
                    arg.line, arg.column,
                )
        expr.indirect_call = True
        expr.resolved_type = ft.ret
        return ft.ret

    # -- partial application (`_` holes, X7) ---------------------------------

    def _infer_partial(self, expr: ast.Call, scope: _Scope) -> Type:
        """Desugar a call with `_` holes into a lambda over the holes (X7).

        `f(a, _, c, _)` becomes `(h0, h1) => f(a, h0, c, h1)`; the hole
        parameters take the callee's parameter types at those positions, and the
        filled arguments are captured by value (they are inlined into the lambda
        body, which the capture analysis snapshots, D48). Works for free
        functions, function values, and methods (the receiver is captured)."""
        param_types, _ret_t = self._partial_target(expr, scope)
        if len(expr.args) != len(param_types):
            raise TypeCheckError(
                f"partial application must list every argument position "
                f"({len(param_types)} expected, found {len(expr.args)}); write "
                f"'_' for each one to leave open (no implicit currying)",
                expr.line, expr.column,
            )
        lam_params: list[ast.Param] = []
        new_args: list[ast.Expr] = []
        for i, a in enumerate(expr.args):
            if isinstance(a, ast.Hole):
                pname = f"__hole{len(lam_params)}"
                ann = _type_to_typeexpr(param_types[i])
                lam_params.append(ast.Param(pname, ann).at(a.line, a.column))
                new_args.append(ast.Name(pname).at(a.line, a.column))
            else:
                new_args.append(a)
        body = ast.Call(expr.callee, new_args).at(expr.line, expr.column)
        lam = ast.Lambda(lam_params, body).at(expr.line, expr.column)
        ft = self._infer_lambda(lam, scope, None)
        expr.desugared = lam
        expr.resolved_type = ft
        return ft

    def _partial_target(self, expr: ast.Call,
                        scope: _Scope) -> tuple[list[Type], Type | None]:
        """The (argument parameter types, return type) of a partial-application
        callee — for a function value, a named function, or a method."""
        callee = expr.callee
        # function value through a local binding (`f(_, 2)` where `f` is local)
        if isinstance(callee, ast.Name) and scope.lookup(callee.ident) is not None:
            ft = scope.lookup(callee.ident).type
            if not isinstance(ft, FuncType):
                raise TypeCheckError(
                    f"cannot partially apply a value of type '{type_name(ft)}'",
                    expr.line, expr.column,
                )
            return list(ft.params), ft.ret
        # method `recv.m(_, …)` (or a function-typed field), receiver captured
        if isinstance(callee, ast.FieldAccess):
            recv_type = self._expect_value(callee.target, scope, None)
            key = self._method_key(recv_type)
            table = self.methods.get(key) if key is not None else None
            sig = table.get(callee.field_name) if table else None
            if sig is not None:
                if sig.type_params:
                    raise TypeCheckError(
                        f"cannot partially apply the generic method "
                        f"'{callee.field_name}'",
                        expr.line, expr.column,
                    )
                return list(sig.params[1:]), sig.ret
            if (isinstance(recv_type, StructType)
                    and callee.field_name in self.structs.get(recv_type.name, {})):
                field_t = self._struct_field_types(recv_type).get(callee.field_name)
                if isinstance(field_t, FuncType):
                    return list(field_t.params), field_t.ret
            raise TypeCheckError(
                f"type '{type_name(recv_type)}' has no method "
                f"'{callee.field_name}'",
                expr.line, expr.column,
            )
        # named free function
        if isinstance(callee, ast.Name):
            sig = self.functions.get(callee.ident)
            if sig is None or "." in callee.ident:
                raise TypeCheckError(
                    f"cannot partially apply '{callee.ident}' with '_' "
                    f"(only functions, methods, and function values are supported)",
                    expr.line, expr.column,
                )
            if sig.type_params:
                raise TypeCheckError(
                    f"cannot partially apply the generic function "
                    f"'{callee.ident}'",
                    expr.line, expr.column,
                )
            return list(sig.params), sig.ret
        raise TypeCheckError(
            "'_' partial application requires a function, method, or function "
            "value", expr.line, expr.column,
        )

    # -- generic call inference (D34) ----------------------------------------

    def _infer_generic_call(self, expr: ast.Call, name: str, sig: FuncSig,
                            scope: _Scope) -> Type | None:
        if len(expr.args) != len(sig.params):
            raise TypeCheckError(
                f"function '{name}' expects {len(sig.params)} argument(s), "
                f"got {len(expr.args)}",
                expr.line, expr.column,
            )
        # Solve left-to-right, growing the substitution as we go: each argument
        # is typed with its parameter type as a hint once that type is fully
        # concrete (so e.g. `prepend(x, List.Nil)` solves `T` from `x` first,
        # then types the otherwise-ambiguous `List.Nil` as `List<T>`).
        subst: dict[str, Type] = {}
        arg_types: list[Type] = []
        for arg, ptype in zip(expr.args, sig.params):
            want = self._subst_type(ptype, subst)
            hint = want if not self._contains_type_param(want) else None
            at = self._expect_value(arg, scope, hint)
            arg_types.append(at)
            self._unify_param(ptype, at, subst)
        missing = [tp for tp in sig.type_params if tp not in subst]
        if missing:
            raise TypeCheckError(
                f"cannot infer type parameter(s) {', '.join(missing)} for '{name}' "
                "from the arguments; add a type annotation to guide inference",
                expr.line, expr.column,
            )
        # Verify each argument against its now-concrete parameter type, allowing
        # an unsuffixed integer literal to adopt the solved type.
        for arg, ptype, at in zip(expr.args, sig.params, arg_types):
            want = self._subst_type(ptype, subst)
            if at != want:
                if isinstance(want, IntType) and _is_flexible_int_lit(arg):
                    self._infer_int_lit(arg, want)
                else:
                    raise TypeCheckError(
                        f"argument type mismatch in call to '{name}': expected "
                        f"'{type_name(want)}', found '{type_name(at)}'",
                        arg.line, arg.column,
                    )
        expr.type_args = tuple(subst[tp] for tp in sig.type_params)
        self._check_call_bounds(sig, subst, expr)
        ret = self._subst_type(sig.ret, subst) if sig.ret is not None else None
        expr.resolved_type = ret
        return ret

    def _contains_type_param(self, t: Type | None) -> bool:
        if isinstance(t, TypeParam):
            return True
        if isinstance(t, TupleType):
            return any(self._contains_type_param(e) for e in t.elems)
        if isinstance(t, ListType):
            return self._contains_type_param(t.elem)
        if isinstance(t, MapType):
            return (self._contains_type_param(t.key)
                    or self._contains_type_param(t.value))
        if isinstance(t, (StructType, EnumType)):
            return any(self._contains_type_param(a) for a in t.args)
        if isinstance(t, FuncType):
            return (any(self._contains_type_param(p) for p in t.params)
                    or self._contains_type_param(t.ret))
        return False

    def _subst_type(self, t: Type | None, subst: dict[str, Type]) -> Type | None:
        if isinstance(t, TypeParam):
            return subst.get(t.name, t)
        if isinstance(t, TupleType):
            return TupleType(tuple(self._subst_type(e, subst) for e in t.elems))
        if isinstance(t, ListType):
            return ListType(self._subst_type(t.elem, subst))
        if isinstance(t, MapType):
            return MapType(self._subst_type(t.key, subst),
                           self._subst_type(t.value, subst))
        if isinstance(t, StructType) and t.args:
            return StructType(t.name, tuple(self._subst_type(a, subst) for a in t.args))
        if isinstance(t, EnumType) and t.args:
            return EnumType(t.name, tuple(self._subst_type(a, subst) for a in t.args))
        if isinstance(t, FuncType):
            return FuncType(
                tuple(self._subst_type(p, subst) for p in t.params),
                self._subst_type(t.ret, subst),
            )
        return t

    def _unify_param(self, ptype: Type, at: Type, subst: dict[str, Type]) -> bool:
        if isinstance(ptype, TypeParam):
            if ptype.name in subst:
                return subst[ptype.name] == at
            subst[ptype.name] = at
            return True
        if isinstance(ptype, TupleType):
            if not isinstance(at, TupleType) or len(ptype.elems) != len(at.elems):
                return False
            return all(self._unify_param(p, a, subst)
                       for p, a in zip(ptype.elems, at.elems))
        if isinstance(ptype, ListType):
            return isinstance(at, ListType) \
                and self._unify_param(ptype.elem, at.elem, subst)
        if isinstance(ptype, MapType):
            return isinstance(at, MapType) \
                and self._unify_param(ptype.key, at.key, subst) \
                and self._unify_param(ptype.value, at.value, subst)
        if isinstance(ptype, StructType) and ptype.args:
            if not isinstance(at, StructType) or at.name != ptype.name \
                    or len(at.args) != len(ptype.args):
                return False
            return all(self._unify_param(p, a, subst)
                       for p, a in zip(ptype.args, at.args))
        if isinstance(ptype, EnumType) and ptype.args:
            if not isinstance(at, EnumType) or at.name != ptype.name \
                    or len(at.args) != len(ptype.args):
                return False
            return all(self._unify_param(p, a, subst)
                       for p, a in zip(ptype.args, at.args))
        if isinstance(ptype, FuncType):
            if not isinstance(at, FuncType) or len(ptype.params) != len(at.params):
                return False
            if not all(self._unify_param(p, a, subst)
                       for p, a in zip(ptype.params, at.params)):
                return False
            if ptype.ret is None or at.ret is None:
                return ptype.ret is None and at.ret is None
            return self._unify_param(ptype.ret, at.ret, subst)
        return ptype == at

    # -- generic aggregate instantiation -------------------------------------

    def _struct_field_types(self, t: StructType) -> dict[str, Type]:
        """Field types of struct instance `t`, with type arguments substituted."""
        fields = self.structs[t.name]
        params = self.struct_decls[t.name].type_params
        if not params:
            return fields
        sub = dict(zip(params, t.args))
        return {n: self._subst_type(ft, sub) for n, ft in fields.items()}

    def _enum_variant_types(self, t: EnumType) -> dict[str, list[Type]]:
        """Variant payloads of enum instance `t`, with type arguments substituted."""
        variants = self.enums[t.name]
        params = self.enum_decls[t.name].type_params
        if not params:
            return variants
        sub = dict(zip(params, t.args))
        return {v: [self._subst_type(pt, sub) for pt in payload]
                for v, payload in variants.items()}

    def _enum_name_ref(self, expr: ast.Expr, scope: _Scope) -> str | None:
        """If `expr` names an enum type (not shadowed by a binding), return it."""
        if isinstance(expr, ast.Name) and expr.ident in self.enums:
            if scope.lookup(expr.ident) is None:
                return expr.ident
        return None

    def _infer_type_args(self, params, template_types, nodes, scope,
                         expected_args, expr, label) -> tuple[Type, ...]:
        """Solve `params` by unifying each template type against the inferred
        type of the matching value node (seeding from an expected instance's
        args). Mirrors generic-call inference; returns the solved argument
        tuple in `params` order."""
        subst: dict[str, Type] = {}
        if expected_args is not None and len(expected_args) == len(params):
            subst.update(zip(params, expected_args))
        value_types: list[Type] = []
        for node, tt in zip(nodes, template_types):
            hint_t = self._subst_type(tt, subst)
            hint = hint_t if not self._contains_type_param(hint_t) else None
            vt = self._expect_value(node, scope, hint)
            value_types.append(vt)
            self._unify_param(tt, vt, subst)
        missing = [p for p in params if p not in subst]
        if missing:
            raise TypeCheckError(
                f"cannot infer type parameter(s) {', '.join(missing)}; "
                "add a type annotation to guide inference", expr.line, expr.column)
        for node, tt, vt in zip(nodes, template_types, value_types):
            want = self._subst_type(tt, subst)
            if vt != want:
                if isinstance(want, IntType) and _is_flexible_int_lit(node):
                    self._infer_int_lit(node, want)
                else:
                    raise TypeCheckError(
                        f"{label}: expected '{type_name(want)}', found '{type_name(vt)}'",
                        node.line, node.column)
        return tuple(subst[p] for p in params)

    def _infer_variant_ctor(self, expr: ast.Call, enum_name: str, variant: str,
                            scope: _Scope, expected: Type | None = None) -> Type:
        variants = self.enums[enum_name]
        if variant not in variants:
            raise TypeCheckError(
                f"enum '{enum_name}' has no variant '{variant}'",
                expr.line, expr.column,
            )
        payload = variants[variant]
        if len(expr.args) != len(payload):
            raise TypeCheckError(
                f"variant '{enum_name}.{variant}' expects {len(payload)} "
                f"argument(s), got {len(expr.args)}",
                expr.line, expr.column,
            )
        params = self.enum_decls[enum_name].type_params
        if not params:
            for arg, pt in zip(expr.args, payload):
                at = self._expect_value(arg, scope, pt)
                if at != pt:
                    raise TypeCheckError(
                        f"variant '{enum_name}.{variant}': expected "
                        f"'{type_name(pt)}', found '{type_name(at)}'",
                        arg.line, arg.column,
                    )
            et: Type = EnumType(enum_name)
        else:
            exp_args = (expected.args if isinstance(expected, EnumType)
                        and expected.name == enum_name else None)
            args_t = self._infer_type_args(
                params, payload, expr.args, scope, exp_args, expr,
                f"variant '{enum_name}.{variant}'")
            et = EnumType(enum_name, args_t)
        expr.enum_ctor = (enum_name, variant)
        expr.resolved_type = et
        return et

    def _infer_field(self, expr: ast.FieldAccess, scope: _Scope,
                     expected: Type | None = None) -> Type:
        enum_name = self._enum_name_ref(expr.target, scope)
        if enum_name is not None:
            variants = self.enums[enum_name]
            if expr.field_name not in variants:
                raise TypeCheckError(
                    f"enum '{enum_name}' has no variant '{expr.field_name}'",
                    expr.line, expr.column,
                )
            payload = variants[expr.field_name]
            if payload:
                raise TypeCheckError(
                    f"variant '{enum_name}.{expr.field_name}' takes "
                    f"{len(payload)} argument(s); call it like "
                    f"'{enum_name}.{expr.field_name}(...)'",
                    expr.line, expr.column,
                )
            params = self.enum_decls[enum_name].type_params
            if not params:
                et: Type = EnumType(enum_name)
            elif (isinstance(expected, EnumType) and expected.name == enum_name
                  and len(expected.args) == len(params)):
                et = expected
            else:
                raise TypeCheckError(
                    f"cannot infer type argument(s) for '{enum_name}.{expr.field_name}'; "
                    f"annotate the binding (e.g. ': {enum_name}<...>')",
                    expr.line, expr.column,
                )
            expr.enum_ctor = (enum_name, expr.field_name)
            expr.resolved_type = et
            return et

        base = self._expect_value(expr.target, scope, None)
        if not isinstance(base, StructType):
            raise TypeCheckError(
                f"type '{type_name(base)}' has no fields", expr.line, expr.column
            )
        fields = self._struct_field_types(base)
        if expr.field_name not in fields:
            raise TypeCheckError(
                f"struct '{base.name}' has no field '{expr.field_name}'",
                expr.line, expr.column,
            )
        ft = fields[expr.field_name]
        expr.resolved_type = ft
        return ft

    def _infer_struct_lit(self, expr: ast.StructLit, scope: _Scope,
                          expected: Type | None = None) -> Type:
        if expr.type_name not in self.structs:
            raise TypeCheckError(f"unknown struct '{expr.type_name}'", expr.line, expr.column)
        template = self.structs[expr.type_name]
        provided: dict[str, ast.FieldInit] = {}
        for init in expr.fields:
            if init.name in provided:
                raise TypeCheckError(
                    f"duplicate field '{init.name}' in struct literal", init.line, init.column
                )
            if init.name not in template:
                raise TypeCheckError(
                    f"struct '{expr.type_name}' has no field '{init.name}'",
                    init.line, init.column,
                )
            provided[init.name] = init
        missing = [n for n in template if n not in provided]
        if missing:
            raise TypeCheckError(
                f"missing field(s) in '{expr.type_name}' literal: {', '.join(missing)}",
                expr.line, expr.column,
            )
        params = self.struct_decls[expr.type_name].type_params
        if not params:
            for init in expr.fields:
                vt = self._expect_value(init.value, scope, template[init.name])
                if vt != template[init.name]:
                    raise TypeCheckError(
                        f"field '{init.name}': expected '{type_name(template[init.name])}', "
                        f"found '{type_name(vt)}'",
                        init.line, init.column,
                    )
            st: Type = StructType(expr.type_name)
        else:
            ordered = list(template.keys())
            nodes = [provided[n].value for n in ordered]
            ttypes = [template[n] for n in ordered]
            exp_args = (expected.args if isinstance(expected, StructType)
                        and expected.name == expr.type_name else None)
            args_t = self._infer_type_args(
                params, ttypes, nodes, scope, exp_args, expr,
                f"struct '{expr.type_name}'")
            st = StructType(expr.type_name, args_t)
        expr.resolved_type = st
        return st


def _is_strict_ancestor(anc: "_Scope", node: "_Scope") -> bool:
    """Whether scope `anc` strictly encloses scope `node` (for capture analysis)."""
    s = node.parent
    while s is not None:
        if s is anc:
            return True
        s = s.parent
    return False


def _block_returns(block: ast.Block) -> bool:
    """Whether `block` is guaranteed to return on every path.

    Conservative: loops are assumed possibly-skipped, so only `return` and
    fully-covered `if`/`else` chains count. Statements after a definite return
    are unreachable but harmless here.
    """
    return any(_stmt_returns(s) for s in block.statements)


def _is_diverging(expr: ast.Expr) -> bool:
    """Whether `expr` is a call to a diverging builtin (`panic`/`unreachable`),
    which never returns — so the checker treats it like a `return`."""
    return (isinstance(expr, ast.Call) and isinstance(expr.callee, ast.Name)
            and expr.callee.ident in _DIVERGING_BUILTINS)


def _stmt_returns(stmt: ast.Stmt) -> bool:
    if isinstance(stmt, ast.Return):
        return True
    if isinstance(stmt, ast.ExprStmt) and _is_diverging(stmt.expr):
        return True
    if isinstance(stmt, ast.If):
        if not _block_returns(stmt.then):
            return False
        if isinstance(stmt.otherwise, ast.If):
            return _stmt_returns(stmt.otherwise)
        if isinstance(stmt.otherwise, ast.Block):
            return _block_returns(stmt.otherwise)
        return False  # no else branch
    return False


def _is_flexible_int_lit(node: ast.Expr) -> bool:
    """An unsuffixed integer literal can still adopt another integer type. An
    ASCII char literal counts too (it may stand in for a byte/integer, D42); a
    multi-byte char literal is `char`-only."""
    if not isinstance(node, ast.IntLit) or node.suffix is not None:
        return False
    return (not node.is_char) or node.value <= 0x7F


def _is_flexible_char_lit(node: ast.Expr) -> bool:
    """A char literal `'a'` that may still adopt an integer type when ASCII."""
    return isinstance(node, ast.IntLit) and node.is_char


def _is_flexible_float_lit(node: ast.Expr) -> bool:
    """An unsuffixed float literal can still adopt another float type."""
    return isinstance(node, ast.FloatLit) and node.suffix is None


def _is_lvalue_shape(expr: ast.Expr) -> bool:
    """Whether `expr` is a place expression (a variable or one of its
    fields/elements) — the receiver shape a `var self` method requires."""
    if isinstance(expr, ast.Name):
        return True
    if isinstance(expr, (ast.FieldAccess, ast.Index)):
        return _is_lvalue_shape(expr.target)
    return False


def _count_format_holes(fmt: str, line: int, col: int) -> int:
    """Count `{}` placeholders in a `format` string, validating that every `{`
    or `}` is either a placeholder or an escaped literal brace (`{{` / `}}`).
    Shared shape with the interpreter and native renderers."""
    holes = 0
    i = 0
    n = len(fmt)
    while i < n:
        c = fmt[i]
        if c == "{":
            if i + 1 < n and fmt[i + 1] == "{":
                i += 2
                continue
            if i + 1 < n and fmt[i + 1] == "}":
                holes += 1
                i += 2
                continue
            raise TypeCheckError(
                "format(): a single '{' must be a '{}' placeholder or an "
                "escaped '{{'",
                line, col,
            )
        if c == "}":
            if i + 1 < n and fmt[i + 1] == "}":
                i += 2
                continue
            raise TypeCheckError(
                "format(): a single '}' must close a '{}' placeholder or be an "
                "escaped '}}'",
                line, col,
            )
        i += 1
    return holes


def _const_bool(literal: ast.Expr) -> bool:
    """The boolean value of a `bool` literal pattern."""
    return bool(getattr(literal, "value", False))


def _prelude_decls() -> list[ast.Decl]:
    # Parsed fresh each call so the returned nodes are never shared between
    # programs (the checker annotates nodes in place). Lazy imports avoid a
    # lexer/parser <-> types import cycle.
    from .lexer import tokenize
    from .parser import parse
    return parse(tokenize(_PRELUDE_SRC)).decls


def _source_path(decl: ast.Node) -> str | None:
    """The file a declaration was loaded from (stamped by the loader), for
    attributing errors to it (MYLA-10); None for the prelude or a program that
    didn't come through the loader."""
    return getattr(decl, "source_path", None)


def check(program: ast.Program, with_prelude: bool = True) -> Checker:
    """Type-check `program`, returning the populated Checker (raises on error).

    With `with_prelude` (the default), the `Option`/`Result` prelude (D16) is
    injected first. After checking, `?` (`ast.Try`) nodes are rewritten to their
    desugared `match`, so the interpreter and compiler only ever see `match`.
    The monomorphizer re-checks an already-desugared, prelude-free program with
    `with_prelude=False`.
    """
    if with_prelude:
        program = ast.Program(_prelude_decls() + list(program.decls))
    checker = Checker(program).check()
    _desugar(program)
    return checker


def _desugar(program: ast.Program) -> None:
    """Rewrite every node the checker desugared (its replacement recorded on a
    `desugared` attribute) out of the tree, so the interpreter and compiler see
    only the lowered form: `?` (`ast.Try`) becomes a `match`, `a >> b`
    composition and `f(_, …)` partial application become lambdas (v0.4.3)."""
    for decl in program.decls:
        if isinstance(decl, ast.FunDecl):
            _desugar_node(decl.body)
        elif isinstance(decl, ast.ImplDecl):
            for m in decl.methods:
                _desugar_node(m.body)
        elif isinstance(decl, ast.ConstDecl):
            decl.value = _desugar_value(decl.value)


def _desugar_node(node: ast.Node) -> None:
    for f in dataclasses.fields(node):
        setattr(node, f.name, _desugar_value(getattr(node, f.name)))


def _desugar_value(val):
    if isinstance(val, ast.Node):
        repl = getattr(val, "desugared", None)
        if repl is not None:
            _desugar_node(repl)
            return repl
        _desugar_node(val)
        return val
    if isinstance(val, list):
        return [_desugar_value(v) for v in val]
    if isinstance(val, tuple):
        return tuple(_desugar_value(v) for v in val)
    return val
