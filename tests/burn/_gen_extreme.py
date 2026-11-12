"""The review's extreme-argument generator (2026-11-12, `repro-r5/std/gen.py`
with `harness.py`, D184): one call per case of the standard library's
functions and methods with boundary values (0, ±1, the int32 and int64
limits, 2^30, 2^31 - 1, widths and radixes out of range, huge exponents,
strings of digits past every limit), in five groups: `num` (radix and float
text, `ldexp`, digits, char arithmetic), `int` (std.int's methods on four
widths), `time` (durations and dates), `cont` (deque, grid, bitset,
union-find, cache, graph, iter, btree, heap) and `seq` (lists, slices,
strings, text, random, fmt, bigint, io). Each case returns a text; the
runners must agree on it, or on the runtime error it ends with (D184: a
function given an argument it can't take reports it, the same in `myla run`,
`--checked` and a plain build)."""
from __future__ import annotations

MIN = "(-2147483647 - 1)"
V = ["0", "-1", "1", "2", "3", "63", "64", "65", "1000", "65536", "1073741823", "1073741824", "1073741825",
     "2147483646", "2147483647", MIN, "-2147483647", "-1073741824"]
VH = {"1073741823", "1073741824", "1073741825", "2147483646", "2147483647"}
VS = ["0", "-1", "1", "5", "1073741824", "2147483647", MIN]          # short list for products
MIN64 = "(-9223372036854775807i64 - 1i64)"
W = ["0i64", "-1i64", "1i64", "1000i64", "2147483647i64", "2147483648i64", "4294967296i64", "4611686018427387904i64",
     "9223372036854775806i64", "9223372036854775807i64", MIN64, "-9223372036854775807i64"]
WS = ["0i64", "-1i64", "1i64", "2i64", "9223372036854775807i64", MIN64]
U = ["0u64", "1u64", "255u64", "4294967295u64", "9223372036854775807u64", "9223372036854775808u64", "18446744073709551615u64"]

HELPERS = r'''
fun sz(s: str) -> str {
    if s.len() <= 70 { return s }
    return f"len={s.len()} head={s[:16]} tail={s[s.len() - 8:]}"
}
fun oi(o: Option<int>) -> str {
    return match o { Some(v) => f"Some({v})", None => "None" }
}
fun ol(o: Option<int64>) -> str {
    return match o { Some(v) => f"Some({v})", None => "None" }
}
fun ou(o: Option<uint64>) -> str {
    return match o { Some(v) => f"Some({v})", None => "None" }
}
fun li(xs: [int]) -> str {
    var h = 0u64
    for x in xs { h = h.wrapping_mul(31).wrapping_add((x as int64) as uint64) }
    var head = ""
    var i = 0
    while i < xs.len() && i < 6 { head = head + f"{xs[i]} "; i += 1 }
    return f"n={xs.len()} h={h} [{head}]"
}
fun ll(xs: [int64]) -> str {
    var head = ""
    var i = 0
    while i < xs.len() && i < 6 { head = head + f"{xs[i]} "; i += 1 }
    return f"n={xs.len()} [{head}]"
}
fun lli(xs: [[int]]) -> str {
    var head = ""
    var i = 0
    while i < xs.len() && i < 4 { head = head + li(xs[i]) + ";"; i += 1 }
    return f"N={xs.len()} {head}"
}
fun ls(xs: [str]) -> str {
    var head = ""
    var i = 0
    while i < xs.len() && i < 5 { head = head + "<" + sz(xs[i]) + ">"; i += 1 }
    return f"n={xs.len()} {head}"
}
fun lp(xs: [(int, int)]) -> str {
    var head = ""
    var i = 0
    while i < xs.len() && i < 9 { let (a, b) = xs[i]; head = head + f"({a},{b})"; i += 1 }
    return f"n={xs.len()} {head}"
}
fun pp(p: (int, int)) -> str {
    let (a, b) = p
    return f"({a},{b})"
}
'''

MAIN = r'''
fun main() {
    let a = process.args()
    var start = 0
    if a.len() > 1 { start = num.parse_int(a[a.len() - 1]).unwrap_or(0) as int }
    for i in start..NCASES {
        println(f"{i}|{run(i)}")
    }
}
'''

groups = {}

def group(name, imports, extra=""):
    groups[name] = {"imports": imports, "extra": extra, "cases": []}
    def add(label, body):
        """body: Myla statements; the last must return a str"""
        groups[name]["cases"].append((label, body))
    def ex(label, expr):
        add(label, "return " + expr)
    return add, ex

# ---------------------------------------------------------------- num
add, ex = group("num", "import std.num as num\nimport std.math as math\nimport std.char as chr\n")
for u in U:
    for v in V:
        if v in VH and u != U[2]: continue
        ex(f"to_hex({u},{v})", f"sz(num.to_hex({u}, {v}))")
        ex(f"to_binary({u},{v})", f"sz(num.to_binary({u}, {v}))")
for w in W:
    for v in ["0", "1", "2", "10", "16", "36", "37", "-1", "2147483647", MIN]:
        ex(f"to_radix({w},{v})", f"sz(num.to_radix({w}, {v}))")
for u in U:
    for v in ["0", "1", "2", "36", "37", "-1", "2147483647", MIN]:
        ex(f"to_radix_u64({u},{v})", f"sz(num.to_radix_u64({u}, {v}))")
STRS = ['""', '"0"', '"-0"', '"+5"', '"zz"', '"9223372036854775807"', '"9223372036854775808"', '"-9223372036854775808"',
        '"-9223372036854775809"', '"18446744073709551615"', '"18446744073709551616"', '"2147483647"', '"2147483648"',
        '"-2147483648"', '"-2147483649"', '"99999999999999999999999999999999999999"', '"-"', '"1_0"', '" 1"', '"7fffffffffffffff"',
        '"8000000000000000"', '"-8000000000000000"', '"ffffffffffffffff"', '"10000000000000000"']
for s in STRS:
    ex(f"parse_int({s})", f"ol(num.parse_int({s}))")
    ex(f"parse_int32({s})", f'match num.parse_int32({s}) {{ Ok(v) => f"Ok({{v}})", Err(e) => f"Err({{e}})" }}')
    ex(f"parse_uint64({s})", f'match num.parse_uint64({s}) {{ Ok(v) => f"Ok({{v}})", Err(e) => f"Err({{e}})" }}')
    for v in ["0", "1", "2", "10", "16", "36", "37", "-1", "2147483647", MIN]:
        ex(f"parse_int_radix({s},{v})", f'match num.parse_int_radix({s}, {v}) {{ Ok(v) => f"Ok({{v}})", Err(e) => f"Err({{e}})" }}')
        ex(f"parse_uint64_radix({s},{v})", f'match num.parse_uint64_radix({s}, {v}) {{ Ok(v) => f"Ok({{v}})", Err(e) => f"Err({{e}})" }}')
FL = ["1.5", "0.0", "-0.0", "1e300", "-1e300", "5e-324", "1.7976931348623157e308", "math.infinity()", "math.nan()", "0.5", "2.5", "999999.9999995"]
for x in FL:
    for v in ["0", "1", "2", "17", "20", "340", "1000", "-1", MIN]:
        ex(f"format_fixed({x},{v})", f"sz(num.format_fixed({x}, {v}))")
    ex(f"format_float({x})", f"sz(num.format_float({x}))")
for v in V + ["-1022", "-1023", "-1074", "-1075", "1023", "1024", "-65536"]:
    ex(f"pow2({v})", f'f"{{num.pow2({v})}}"')
    ex(f"ldexp(1.5,{v})", f'f"{{math.ldexp(1.5, {v})}}"')
    ex(f"ldexp(5e-324,{v})", f'f"{{math.ldexp(5e-324, {v})}}"')
    ex(f"ldexp(1e308,{v})", f'f"{{math.ldexp(1e308, {v})}}"')
for u in U:
    ex(f"float_from_bits({u})", f'f"{{num.float_from_bits({u})}}"')
    ex(f"f32_round_bits({u})", f'f"{{num.f32_round_bits({u})}}"')
for s in ['"1e999999999999"', '"1e-999999999999"', '"1e2147483648"', '"0.000000000000000000000000000001e2147483647"', '"1e+2147483647"',
          '"123456789012345678901234567890123456789012345678901234567890e-2147483648"', '"1e"', '""', '"."', '"0x10"', '"inf"', '"nan"', '"-"',
          '"1e9223372036854775807"', '"1e-9223372036854775808"', '"1e18446744073709551616"']:
    ex(f"parse_float({s})", f'match num.parse_float({s}) {{ Some(v) => f"Some({{v}})", None => "None" }}')
for v in V:
    for c in ["'7'", "'z'", "'Z'", "' '"]:
        ex(f"to_digit({c},{v})", f"oi({c}.to_digit({v}))")
    for d in ["0", "9", "35", "36", "-1", "2147483647", MIN]:
        ex(f"from_digit({d},{v})", f'match chr.from_digit({d}, {v}) {{ Some(c) => f"Some({{c}})", None => "None" }}')
for v in V + ["55295", "55296", "57343", "57344", "1114111", "1114112", "-97"]:
    ex(f"'a'+{v}", f'f"{{(\'a\' + {v}) as int}}"')
    ex(f"'a'-{v}", f'f"{{(\'a\' - {v}) as int}}"')

# ---------------------------------------------------------------- int
add, ex = group("int", "", extra=r'''
fun t32(p: (int, bool)) -> str { let (a, b) = p; return f"{a},{b}" }
fun t64(p: (int64, bool)) -> str { let (a, b) = p; return f"{a},{b}" }
fun t8(p: (int8, bool)) -> str { let (a, b) = p; return f"{a},{b}" }
fun tu(p: (uint64, bool)) -> str { let (a, b) = p; return f"{a},{b}" }
fun o8(o: Option<int8>) -> str { return match o { Some(v) => f"Some({v})", None => "None" } }
''')
TY = {
    "int": (["0", "1", "-1", "2", "2147483647", MIN, "-2147483647", "46341"], "t32", "oi"),
    "int64": (["0i64", "1i64", "-1i64", "2i64", "9223372036854775807i64", MIN64, "3037000500i64"], "t64", "ol"),
    "int8": (["0i8", "-1i8", "2i8", "127i8", "(-127i8 - 1i8)", "12i8"], "t8", "o8"),
    "uint64": (["0u64", "1u64", "2u64", "18446744073709551615u64", "9223372036854775808u64", "4294967296u64"], "tu", "ou"),
}
EXPS = ["0u32", "1u32", "2u32", "31u32", "63u32", "64u32", "4294967295u32"]
for ty, (vals, tup, opt) in TY.items():
    signed = ty != "uint64"
    un = (["abs", "signum"] if signed else []) + ["count_ones", "leading_zeros", "trailing_zeros"]
    for a in vals:
        A = f"({a})"
        for m in un:
            ex(f"{ty} {a}.{m}()", f'f"{{{A}.{m}()}}"')
        ex(f"{ty} {a}.checked_neg()", f"{opt}({A}.checked_neg())")
        if signed:
            ex(f"{ty} {a}.checked_abs()", f"{opt}({A}.checked_abs())")
        ex(f"{ty} {a}.overflowing_neg()", f"{tup}({A}.overflowing_neg())")
        for e in EXPS:
            for m in ["pow", "wrapping_pow", "saturating_pow"]:
                ex(f"{ty} {a}.{m}({e})", f'f"{{{A}.{m}({e})}}"')
            ex(f"{ty} {a}.checked_pow({e})", f"{opt}({A}.checked_pow({e}))")
            ex(f"{ty} {a}.overflowing_pow({e})", f"{tup}({A}.overflowing_pow({e}))")
        for b in vals:
            B = f"({b})"
            for m in ["min", "max", "gcd", "lcm", "div_euclid", "rem_euclid", "saturating_add", "saturating_sub", "saturating_mul"]:
                ex(f"{ty} {a}.{m}({b})", f'f"{{{A}.{m}({B})}}"')
            for m in ["checked_add", "checked_sub", "checked_mul", "checked_div", "checked_rem"]:
                ex(f"{ty} {a}.{m}({b})", f"{opt}({A}.{m}({B}))")
            for m in ["overflowing_add", "overflowing_sub", "overflowing_mul"]:
                ex(f"{ty} {a}.{m}({b})", f"{tup}({A}.{m}({B}))")
            ex(f"{ty} {a}.modinv({b})", f"{opt}({A}.modinv({B}))")
            for c in [vals[0], vals[1], vals[3], vals[4]]:
                C = f"({c})"
                ex(f"{ty} {a}.clamp({b},{c})", f'f"{{{A}.clamp({B}, {C})}}"')
                ex(f"{ty} {a}.mulmod({b},{c})", f'f"{{{A}.mulmod({B}, {C})}}"')
                ex(f"{ty} {a}.powmod({b},{c})", f'f"{{{A}.powmod({B}, {C})}}"')

# ---------------------------------------------------------------- time
add, ex = group("time", "import std.time as time\nfrom std.time import Duration, DateTime\n", extra=r'''
fun dt(r: Result<DateTime, time.TimeError>) -> str {
    return match r { Ok(t) => f"Ok({t})", Err(e) => f"Err({e})" }
}
fun mk(y: int, mo: int, d: int, h: int, mi: int, s: int, ns: int) -> DateTime {
    return DateTime { year: y, month: mo, day: d, hour: h, minute: mi, second: s, nanosecond: ns }
}
''')
CONS = ["nanos", "micros", "millis", "seconds", "minutes", "hours"]
WT = W + ["9223372036854775i64", "9223372036854776i64", "-9223372036854776i64", "9223372036i64", "9223372037i64", "-9223372037i64",
          "153722867i64", "153722868i64", "2562047i64", "2562048i64", "-2562048i64", "-2562049i64"]
for c in CONS:
    for w in WT:
        ex(f"time.{c}({w})", f'f"{{time.{c}({w})}}"')
DS = ["time.nanos(0i64)", "time.nanos(1i64)", "time.nanos(-1i64)", "time.nanos(9223372036854775807i64)", f"time.nanos({MIN64})",
      "time.seconds(1i64)", "time.nanos(-9223372036854775807i64)", "time.hours(2562047i64)", "time.nanos(4611686018427387904i64)"]
for d in DS:
    for m in ["as_nanos", "as_micros", "as_millis", "as_secs", "as_secs_f64", "abs"]:
        ex(f"{d}.{m}()", f'f"{{{d}.{m}()}}"')
    for w in W:
        ex(f"{d}.mul_int({w})", f'f"{{{d}.mul_int({w})}}"')
        ex(f"{d}.div_int({w})", f'f"{{{d}.div_int({w})}}"')
    for e in DS:
        ex(f"{d}+{e}", f'f"{{{d} + {e}}}"')
        ex(f"{d}-{e}", f'f"{{{d} - {e}}}"')
        ex(f"{d}<{e}", f'f"{{{d} < {e}}}"')
    for sp in ['""', '">30"', '"<40"', '"^5"']:
        ex(f"{d}.format({sp})", f'{d}.format({sp})')
    add(f"now.add({d})", f'let i = time.now().add({d})\nreturn "ok"')
    ex(f"from_unix_ns(0).add({d})", f'dt(time.from_unix_ns(0i64).add({d}))')
    ex(f"from_unix_ns(MAX).add({d})", f'dt(time.from_unix_ns(9223372036854775807i64).add({d}))')
    ex(f"from_unix_ns(MIN).add({d})", f'dt(time.from_unix_ns({MIN64}).add({d}))')
    ex(f"date(9999,12,31).add({d})", f'match time.date(9999, 12, 31) {{ Ok(t) => dt(t.add({d})), Err(e) => "Err" }}')
    ex(f"date(1,1,1).add({d})", f'match time.date(1, 1, 1) {{ Ok(t) => dt(t.add({d})), Err(e) => "Err" }}')
    ex(f"date(0,1,1).add({d})", f'match time.date(0, 1, 1) {{ Ok(t) => dt(t.add({d})), Err(e) => "Err" }}')
for v in V + ["1900", "2000", "2024", "9999", "10000", "-9999", "-400", "400"]:
    ex(f"is_leap_year({v})", f'f"{{time.is_leap_year({v})}}"')
    for mo in ["0", "1", "2", "12", "13", "-1", "2147483647", MIN]:
        ex(f"days_in_month({v},{mo})", f'f"{{time.days_in_month({v}, {mo})}}"')
    ex(f"date({v},1,1)", f"dt(time.date({v}, 1, 1))")
    ex(f"date(2024,{v},1)", f"dt(time.date(2024, {v}, 1))")
    ex(f"date(2024,2,{v})", f"dt(time.date(2024, 2, {v}))")
    ex(f"datetime h={v}", f"dt(time.datetime(2024, 2, 29, {v}, 59, 59, 999999999))")
    ex(f"datetime mi={v}", f"dt(time.datetime(2024, 2, 29, 23, {v}, 59, 999999999))")
    ex(f"datetime s={v}", f"dt(time.datetime(2024, 2, 29, 23, 59, {v}, 999999999))")
    ex(f"datetime ns={v}", f"dt(time.datetime(2024, 2, 29, 23, 59, 59, {v}))")
    ex(f"datetime y={v}", f"dt(time.datetime({v}, 12, 31, 23, 59, 59, 999999999))")
    # hand-built
    for fld, call in [("y", f"mk({v}, 1, 1, 0, 0, 0, 0)"), ("mo", f"mk(2024, {v}, 1, 0, 0, 0, 0)"), ("d", f"mk(2024, 1, {v}, 0, 0, 0, 0)"),
                      ("h", f"mk(2024, 1, 1, {v}, 0, 0, 0)"), ("mi", f"mk(2024, 1, 1, 0, {v}, 0, 0)"), ("s", f"mk(2024, 1, 1, 0, 0, {v}, 0)"),
                      ("ns", f"mk(2024, 1, 1, 0, 0, 0, {v})")]:
        ex(f"hand {fld}={v} to_unix", f'f"{{{call}.to_unix()}}"')
        ex(f"hand {fld}={v} to_unix_ns", f'match {call}.to_unix_ns() {{ Ok(n) => f"Ok({{n}})", Err(e) => f"Err({{e}})" }}')
        ex(f"hand {fld}={v} diff", f'f"{{{call}.diff(mk(1970, 1, 1, 0, 0, 0, 0))}}"')
        ex(f"hand {fld}={v} rdiff", f'f"{{mk(1970, 1, 1, 0, 0, 0, 0).diff({call})}}"')
        ex(f"hand {fld}={v} weekday", f'f"{{{call}.weekday()}}"')
        ex(f"hand {fld}={v} day_of_year", f'f"{{{call}.day_of_year()}}"')
        ex(f"hand {fld}={v} fmt", f'time.format_rfc3339({call})')
        ex(f"hand {fld}={v} fmtms", f'time.format_rfc3339_millis({call})')
        ex(f"hand {fld}={v} basic", f'time.format_iso8601_basic({call})')
        ex(f"hand {fld}={v} add", f'dt({call}.add(time.seconds(1i64)))')
        ex(f"hand {fld}={v} cmp", f'f"{{{call} < mk(1970, 1, 1, 0, 0, 0, 0)}}"')
for w in WT + ["253402300799i64", "253402300800i64", "-62167219200i64", "-62167219201i64", "-62135596800i64", "-62135596801i64"]:
    for n in ["0i64", "999999999i64", "1000000000i64", "-1i64", "9223372036854775807i64", MIN64]:
        ex(f"from_unix({w},{n})", f"dt(time.from_unix({w}, {n}))")
    ex(f"from_unix_ns({w})", f'f"{{time.from_unix_ns({w})}}"')
    ex(f"from_unix_ns({w}).to_unix_ns", f'match time.from_unix_ns({w}).to_unix_ns() {{ Ok(n) => f"Ok({{n}})", Err(e) => f"Err({{e}})" }}')
    ex(f"from_unix_ns({w}).diff(0)", f'f"{{time.from_unix_ns({w}).diff(time.from_unix_ns(0i64))}}"')
    ex(f"0.diff(from_unix_ns({w}))", f'f"{{time.from_unix_ns(0i64).diff(time.from_unix_ns({w}))}}"')
    ex(f"MAX.diff(from_unix_ns({w}))", f'f"{{time.from_unix_ns(9223372036854775807i64).diff(time.from_unix_ns({w}))}}"')
for s in ['"99999999999-01-01T00:00:00Z"', '"2024-01-01T00:00:00.999999999999999999999Z"', '"2024-01-01T00:00:00+99:99"', '"2024-01-01T00:00:00-23:59"',
          '"9999-12-31T23:59:59.999999999-23:59"', '"0000-01-01T00:00:00+23:59"', '"2024-01-01T00:00:60Z"', '"2024-13-01T00:00:00Z"',
          '"2024-02-30T00:00:00Z"', '"2147483648-01-01T00:00:00Z"', '"2024-01-01T24:00:00Z"', '"2024-01-01T00:00:00.Z"', '""',
          '"20240101T000000Z"', '"99991231T235959.999999999999999999-2359"', '"2024-01-01T00:00:00.123456789123456789+00:00"',
          '"0001-01-01T00:00:00+00:01"', '"9999-12-31T23:59:59-00:01"']:
    ex(f"parse_rfc3339({s})", f"dt(time.parse_rfc3339({s}))")
    ex(f"parse_iso8601({s})", f"dt(time.parse_iso8601({s}))")

# ---------------------------------------------------------------- containers
add, ex = group("cont", """import std.deque as deque
from std.deque import Deque
import std.heap as heap
import std.btree as btree
import std.grid as grid
import std.bitset as bitset
import std.unionfind as uf
import std.cache as cache
import std.graph as graph
import std.set as set
import std.iter as iter
""", extra=r'''
fun g32() -> grid.Grid<int> {
    var g = grid.new(3, 2, 0)
    g.set((0, 0), 1); g.set((1, 0), 2); g.set((2, 0), 3); g.set((0, 1), 4); g.set((1, 1), 5); g.set((2, 1), 6)
    return g
}
fun ring(n: int) -> (int) -> [int] {
    return (x: int) => [(x + 1) % 5]
}
''')
for v in V:
    add(f"deque.with_capacity({v})", f'var d: Deque<int> = deque.with_capacity({v})\nd.push_back(1)\nd.push_front(2)\nreturn f"{{d.len()}} {{li(d.items())}}"')
    add(f"deque.get({v})", f'var d: Deque<int> = deque.of([1, 2, 3])\nd.push_front(0)\nreturn oi(d.get({v}))')
    add(f"deque.set({v})", f'var d: Deque<int> = deque.of([1, 2, 3])\nd.push_front(0)\nd.set({v}, 9)\nreturn li(d.items())')
    add(f"empty deque.get({v})", f'let d: Deque<int> = deque.new()\nreturn oi(d.get({v}))')
    add(f"empty deque.set({v})", f'var d: Deque<int> = deque.new()\nd.set({v}, 9)\nreturn li(d.items())')
    # grid
    for h in VS:
        add(f"grid.new({v},{h})", f'let g = grid.new({v}, {h}, 0u8)\nreturn f"{{g.width}}x{{g.height}} {{g.cells.len()}}"')
        add(f"grid.at(({v},{h}))", f'return oi(g32().at(({v}, {h})))')
        add(f"grid.in_bounds(({v},{h}))", f'return f"{{g32().in_bounds(({v}, {h}))}}"')
        add(f"grid.set(({v},{h}))", f'var g = g32()\ng.set(({v}, {h}), 9)\nreturn li(g.cells)')
        add(f"grid.n4(({v},{h}))", f'return lp(g32().neighbours4(({v}, {h})))')
        add(f"grid.n8(({v},{h}))", f'return lp(g32().neighbours8(({v}, {h})))')
        add(f"grid.index(({v},{h}))", f'return f"{{g32().index(({v}, {h}))}}"')
        add(f"grid.n4(({h},{v}))", f'return lp(g32().neighbours4(({h}, {v})))')
        add(f"grid.n8(({h},{v}))", f'return lp(g32().neighbours8(({h}, {v})))')
        add(f"grid.index(({h},{v}))", f'return f"{{g32().index(({h}, {v}))}}"')
        add(f"grid.at(({h},{v}))", f'return oi(g32().at(({h}, {v})))')
    add(f"grid.pos({v})", f'return pp(g32().pos({v}))')
    add(f"grid.row({v})", f'return li(g32().row({v}))')
    add(f"grid.column({v})", f'return li(g32().column({v}))')
    add(f"empty grid.pos({v})", f'let g = grid.new(0, 0, 0)\nreturn pp(g.pos({v}))')
    add(f"empty grid.row({v})", f'let g = grid.new(0, 5, 0)\nreturn li(g.row({v}))')
    add(f"empty grid.column({v})", f'let g = grid.new(5, 0, 0)\nreturn li(g.column({v}))')
    add(f"empty grid.n8(({v},0))", f'let g = grid.new(0, 0, 0)\nreturn lp(g.neighbours8(({v}, 0)))')
    # bitset
    add(f"bitset.fixed({v})", f'var b = bitset.fixed({v})\nreturn f"{{b.capacity()}} {{b.popcount()}} {{b.insert(0)}}"')
    add(f"bitset.fixed({v}).insert(n-1)", f'var b = bitset.fixed({v})\nlet r = b.insert({v} - 1)\nreturn f"{{r}} {{b.contains({v} - 1)}} {{oi(b.next_from(0))}}"')
    for m in ["insert", "remove", "toggle", "contains"]:
        add(f"bitset.new.{m}({v})", f'var b = bitset.new()\nlet r = b.{m}({v})\nreturn f"{{r}} {{b.popcount()}} {{b.capacity()}} {{li(b.items())}}"')
        add(f"bitset.fixed(100).{m}({v})", f'var b = bitset.fixed(100)\nlet r = b.{m}({v})\nreturn f"{{r}} {{b.popcount()}} {{b.capacity()}}"')
        add(f"bitset.of(3).{m}({v})", f'var b = bitset.of([1, 64, 200])\nlet r = b.{m}({v})\nreturn f"{{r}} {{b.popcount()}} {{b.capacity()}} {{li(b.items())}}"')
    add(f"bitset.next_from({v})", f'let b = bitset.of([1, 64, 200])\nreturn oi(b.next_from({v}))')
    add(f"bitset.fixed.next_from({v})", f'var b = bitset.fixed(100)\nlet r = b.insert(99)\nreturn oi(b.next_from({v}))')
    add(f"bitset.of([{v}])", f'let b = bitset.of([{v}])\nreturn f"{{b.popcount()}} {{b.capacity()}} {{li(b.items())}}"')
    add(f"bitset.of([{v}]) ops", f'let b = bitset.of([{v}])\nlet c = bitset.of([1, 2])\nreturn f"{{b.union(c).popcount()}} {{b.intersection(c).popcount()}} {{b.difference(c).popcount()}} {{c.difference(b).popcount()}} {{b.is_disjoint(c)}} {{b.is_subset(c)}} {{c.is_subset(b)}} {{b == c}}"')
    add(f"bitset.of([{v}]) next_from(MAX)", f'let b = bitset.of([{v}])\nreturn oi(b.next_from(2147483647)) + oi(b.next_from({v}))')
    # unionfind
    add(f"uf.new({v})", f'var u = uf.new({v})\nreturn f"{{u.len()}} {{u.sets()}} {{u.add()}}"')
    for m in ["find", "size_of"]:
        add(f"uf.{m}({v})", f'var u = uf.new(3)\nreturn f"{{u.{m}({v})}}"')
    for m in ["union", "same"]:
        add(f"uf.{m}({v},0)", f'var u = uf.new(3)\nreturn f"{{u.{m}({v}, 0)}}"')
        add(f"uf.{m}(0,{v})", f'var u = uf.new(3)\nreturn f"{{u.{m}(0, {v})}}"')
    # cache
    add(f"cache.new({v})", f'var c: cache.Lru<int, int> = cache.new({v})\nlet a = c.put(1, 1)\nlet b = c.put(2, 2)\nlet e = c.put(3, 3)\nreturn f"{{c.len()}} {{c.capacity()}} {{li(c.keys())}} {{oi(c.get(1))}}"')
    # graph dense
    for s in VS:
        if v in VH and s not in ("0", "-1", "2147483647"): continue
        add(f"bfs_dense({v},{s})", f'return li(graph.bfs_dense({v}, {s}, (x: int) => [(x + 1) % 5]))')
        add(f"dijkstra_dense({v},{s})", f'return ll(graph.dijkstra_dense({v}, {s}, (x: int) => [((x + 1) % 5, 1i64)]))')
    add(f"bfs_dense next->{v}", f'return li(graph.bfs_dense(5, 0, (x: int) => [{v}]))')
    add(f"dijkstra_dense next->{v}", f'return ll(graph.dijkstra_dense(5, 0, (x: int) => [({v}, 1i64)]))')
    # iter
    for s in VS:
        add(f"iter.range({v},{s})", f'return li(iter.range({v}, {s}) |> iter.take(3) |> iter.to_list())')
        add(f"iter.range({s},{v})", f'return li(iter.range({s}, {v}) |> iter.take(3) |> iter.to_list())')
    add(f"iter.take({v})", f'return li(iter.range(0, 5) |> iter.take({v}) |> iter.to_list())')
    add(f"iter.skip({v})", f'return li(iter.range(0, 5) |> iter.skip({v}) |> iter.to_list())')
    add(f"iter.skip({v}) take", f'return li(iter.range(0, 2147483647) |> iter.skip({v}) |> iter.take(2) |> iter.to_list())' if v not in ("2147483646","2147483647","1073741823","1073741824","1073741825") else 'return "skipped (slow)"')
    add(f"iter.repeat.take({v}).count", f'return f"{{iter.repeat(1) |> iter.take({v}) |> iter.take(1000) |> iter.count()}}"')
    add(f"enumerate from range({v})", f'return lp(iter.range({v}, 2147483647) |> iter.enumerate() |> iter.take(2) |> iter.to_list())')
    add(f"iter.sum({v},MAX)", f'return f"{{[{v}, 2147483647].iter() |> iter.sum(0)}}"')
    add(f"list.sum({v},MAX)", f'return f"{{[{v}, 2147483647].sum(0)}}"')
    # btree with extreme keys
    add(f"btree key {v}", f'var m: btree.SortedMap<int, int> = btree.new()\nlet a = m.insert({v}, 1)\nlet b = m.insert(0, 2)\nreturn f"{{li(m.keys())}} {{oi(m.get({v}))}} {{m.range({v}, 2147483647).len()}} {{m.range(2147483647, {v}).len()}} {{m.floor({v}).is_some()}} {{m.ceiling({v}).is_some()}}"')
for w in W:
    add(f"keyed.push({w})", f'var h: heap.KeyedHeap<int> = heap.keyed_new()\nh.push({w}, 1)\nh.push(0i64, 2)\nh.push(9223372036854775807i64, 3)\nh.push({MIN64}, 4)\nvar s = ""\nwhile let Some((p, v)) = h.pop() {{ s = s + f"{{p}}:{{v}} " }}\nreturn s')
    for fn in ["dijkstra", ]:
        add(f"dijkstra w={w}", f'let d = graph.dijkstra(0, (x: int) => if x < 3 {{ [(x + 1, {w})] }} else {{ [] }})\nreturn f"{{d.len()}} {{d.get_or(3, -7i64)}}"')
    add(f"dijkstra_path w={w}", f'let p = graph.dijkstra_path(0, (x: int) => x == 3, (x: int) => if x < 3 {{ [(x + 1, {w})] }} else {{ [] }})\nreturn match p {{ Some(q) => f"{{q.cost}} {{li(q.nodes)}}", None => "None" }}')
    add(f"astar w={w}", f'let p = graph.astar(0, (x: int) => x == 3, (x: int) => if x < 3 {{ [(x + 1, {w})] }} else {{ [] }}, (x: int) => 0i64)\nreturn match p {{ Some(q) => f"{{q.cost}} {{li(q.nodes)}}", None => "None" }}')
    add(f"astar h={w}", f'let p = graph.astar(0, (x: int) => x == 3, (x: int) => if x < 3 {{ [(x + 1, 1i64)] }} else {{ [] }}, (x: int) => {w})\nreturn match p {{ Some(q) => f"{{q.cost}} {{li(q.nodes)}}", None => "None" }}')
    add(f"dijkstra_dense w={w}", f'return ll(graph.dijkstra_dense(4, 0, (x: int) => if x < 3 {{ [(x + 1, {w})] }} else {{ [] }}))')

# ---------------------------------------------------------------- sequences
add, ex = group("seq", """import std.list as list
import std.bytes as bytes
import std.text as text
import std.random as random
import std.fmt as fmt
import std.bigint as bigint
import std.io as io
from std.io import SeekFrom, Seek, Read
""")
for v in V:
    add(f"list.filled({v})", f'let xs = list.filled({v}, 7u8)\nreturn f"{{xs.len()}}"')
    add(f"insert({v})", f'var xs = [1, 2, 3]\nxs.insert({v}, 9)\nreturn li(xs)')
    add(f"remove_at({v})", f'var xs = [1, 2, 3]\nlet r = xs.remove_at({v})\nreturn f"{{r}} " + li(xs)')
    add(f"truncate({v})", f'var xs = [1, 2, 3]\nxs.truncate({v})\nreturn li(xs)')
    add(f"chunks({v})", f'return lli([1, 2, 3, 4, 5].chunks({v}))')
    add(f"windows({v})", f'return lli([1, 2, 3, 4, 5].windows({v}))')
    add(f"combinations({v})", f'return lli([1, 2, 3, 4, 5].combinations({v}))')
    add(f"empty.chunks({v})", f'let e: [int] = []\nreturn lli(e.chunks({v}))')
    add(f"empty.windows({v})", f'let e: [int] = []\nreturn lli(e.windows({v}))')
    add(f"empty.combinations({v})", f'let e: [int] = []\nreturn lli(e.combinations({v}))')
    add(f"xs[{v}]", f'let xs = [1, 2, 3]\nlet i = {v}\nreturn f"{{xs[i]}}"')
    add(f"xs[^{v}]", f'let xs = [1, 2, 3]\nlet i = {v}\nreturn f"{{xs[^i]}}"')
    add(f"s[{v}]", f'let s = "abc"\nlet i = {v}\nreturn f"{{s[i]}}"')
    for s in VS:
        add(f"swap({v},{s})", f'var xs = [1, 2, 3]\nxs.swap({v}, {s})\nreturn li(xs)')
        add(f"swap({s},{v})", f'var xs = [1, 2, 3]\nxs.swap({s}, {v})\nreturn li(xs)')
        add(f"xs[{v}:{s}]", f'let xs = [1, 2, 3, 4, 5]\nlet a = {v}\nlet b = {s}\nreturn li(xs[a:b])')
        add(f"xs[{s}:{v}]", f'let xs = [1, 2, 3, 4, 5]\nlet a = {s}\nlet b = {v}\nreturn li(xs[a:b])')
        add(f"xs[::{v}] from {s}", f'let xs = [1, 2, 3, 4, 5]\nlet a = {s}\nlet c = {v}\nreturn li(xs[a::c])')
        add(f"xs[:{s}:{v}]", f'let xs = [1, 2, 3, 4, 5]\nlet a = {s}\nlet c = {v}\nreturn li(xs[:a:c])')
        add(f"xs[^{v}:^{s}]", f'let xs = [1, 2, 3, 4, 5]\nlet a = {v}\nlet b = {s}\nreturn li(xs[^a:^b])')
        add(f"s[{v}:{s}]", f'let x = "hello"\nlet a = {v}\nlet b = {s}\nreturn x[a:b]')
        add(f"s[{s}:{v}]", f'let x = "hello"\nlet a = {s}\nlet b = {v}\nreturn x[a:b]')
        add(f"s[{s}::{v}]", f'let x = "hello"\nlet a = {s}\nlet c = {v}\nreturn x[a::c]')
        add(f"int_in({v},{s})", f'var r = random.seeded(1u64)\nlet x = r.int_in({v}, {s})\nreturn f"{{x >= {v} && x < {s}}}"')
        add(f"int_in({s},{v})", f'var r = random.seeded(1u64)\nlet x = r.int_in({s}, {v})\nreturn f"{{x >= {s} && x < {v}}}"')
        add(f"sb.append(s,{v},{s})", f'var sb = StringBuilder()\nsb.append("hello", {v}, {s})\nreturn sb.build()')
        add(f"sb.append(s,{s},{v})", f'var sb = StringBuilder()\nsb.append("hello", {s}, {v})\nreturn sb.build()')
        add(f"decode_char at {v} / {s}", f'let b = "aé€😀".bytes()\nreturn match bytes.decode_char(b, {v}) {{ Some((c, n)) => f"{{c as int}} {{n}}", None => "None" }}')
    # str
    add(f"find_from({v})", f'return oi("hello world".find_from("o", {v}))')
    add(f"find_from empty needle({v})", f'return oi("hello world".find_from("", {v}))')
    add(f"splitn({v})", f'return ls("a,b,c,d".splitn(",", {v}))')
    add(f"splitn empty sep({v})", f'return ls("abcd".splitn("", {v}))')
    add(f"repeat({v})", f'return sz("ab".repeat({v}))')
    add(f"empty.repeat({v})", f'return sz("".repeat({v}))')
    add(f"pad_start({v})", f'return sz("ab".pad_start({v}, \'*\'))')
    add(f"pad_end({v})", f'return sz("ab".pad_end({v}, \'*\'))')
    add(f"pad_start wide({v})", f'return sz("ab".pad_start({v}, \'€\'))')
    add(f"replacen({v})", f'return sz("a-b-c-d".replacen("-", "+", {v}))')
    add(f"replacen empty old({v})", f'return sz("abc".replacen("", "+", {v}))')
    add(f"wrap({v})", f'return ls(text.wrap("the quick brown fox jumps over the lazy dog", {v}))')
    add(f"fill({v})", f'return sz(text.fill("the quick brown fox jumps over the lazy dog", {v}))')
    add(f"wrap long word({v})", f'return ls(text.wrap("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa bb", {v}))')
    add(f"StringBuilder({v})", f'var sb = StringBuilder({v})\nsb.append("x")\nreturn sb.build()')
    # bigint
    add(f"bigint.shl({v})", f'let b = bigint.from_int(5i64).shl({v})\nreturn f"{{b.bit_len()}}"')
    add(f"bigint.shr({v})", f'let b = bigint.from_int(-5i64).shr({v})\nreturn f"{{b}}"')
    add(f"bigint.to_str_radix({v})", f'return bigint.from_int(-255i64).to_str_radix({v})')
    add(f"bigint.parse_radix({v})", f'return match bigint.parse_radix("-zz", {v}) {{ Ok(b) => f"Ok({{b}})", Err(e) => f"Err({{e}})" }}')
    # io
    add(f"mem.read({v})", f'var m = io.from_str("hello")\nreturn match m.read({v}) {{ Ok(b) => f"Ok({{b.len()}})", Err(e) => f"Err({{e}})" }}')
    add(f"mem.read_exact({v})", f'var m = io.buffered(io.from_str("hello"))\nreturn match m.read_exact({v}) {{ Ok(b) => f"Ok({{b.unwrap_or(\"none\")}})", Err(e) => f"Err({{e}})" }}')
for w in W:
    for kind in ["Start", "Current", "End"]:
        add(f"seek {kind}({w})", f'var m = io.from_str("hello")\nlet p = m.seek(SeekFrom.Start(3i64))\nreturn match m.seek(SeekFrom.{kind}({w})) {{ Ok(p) => f"Ok({{p}})", Err(e) => f"Err({{e}})" }}')
    for x in WS:
        add(f"int64_in({w},{x})", f'var r = random.seeded(1u64)\nlet v = r.int64_in({w}, {x})\nreturn f"{{v >= {w} && v < {x}}}"')
    add(f"bigint.from_int({w})", f'let b = bigint.from_int({w})\nreturn f"{{b}} {{ol(b.to_int64())}} {{ol(b.neg().to_int64())}} {{ol(b.abs().to_int64())}} {{ou(b.to_uint64())}} {{b.bit_len()}}"')
    for bits in ["8", "16", "32", "64"]:
        for sg in ["true", "false"]:
            for sp in ['""', '"x"', '"#b"', '"+08"', '"#o"', '"X"']:
                add(f"fmt_int({w},{bits},{sg},{sp})", f'return sz(fmt.fmt_int({w}, {bits}, {sg}, {sp}))')
for u in U:
    add(f"below({u})", f'var r = random.seeded(1u64)\nlet v = r.below({u})\nreturn f"{{v < {u}}}"')
    add(f"seeded({u})", f'var r = random.seeded({u})\nreturn f"{{r.next_u64()}} {{r.float() < 1.0}} {{r.int_in(0, 10) < 10}}"')
for sp in ['"9999999999"', '"1000000"', '"1000001"', '".1000000"', '".1000001"', '"99999999999999999999999999"', '".99999999999999999999999999"',
           '"2147483647"', '"2147483648"', '"4294967296"', '">1000000"', '"0>1000000"', '"-1"', '".-1"', '"€^9"', '"^^^"', '"01000000"', '"00000000000000000005"']:
    add(f"parse_spec({sp})", f'return match fmt.parse_spec({sp}) {{ Ok(s) => f"Ok(w={{s.width}} p={{s.prec}} a={{s.align}} z={{s.zero}})", Err(e) => f"Err({{e}})" }}')
    add(f"pad({sp})", f'return sz(fmt.pad("xy", {sp}))')
    add(f"fmt_text({sp})", f'return sz(fmt.fmt_text("xy", {sp}))')
    add(f"fmt_int({sp})", f'return sz(fmt.fmt_int(-5i64, 32, true, {sp}))')
    add(f"fmt_float({sp})", f'return sz(fmt.fmt_float(1.5, "1.5", {sp}))')
    add(f"Duration.format({sp})", f'return sz("ab".pad_start(3, \' \'))')
for s in ['"2147483647"', '"2147483648"', '"-2147483648"', '"-2147483649"', '"99999999999999999999"', '"9223372036854775807 9223372036854775808"',
          '"-9223372036854775808"', '"-9223372036854775809"', '"1 -2 +3"', '"x12y-34"', '"-"', '"00000000000000000000000000001"']:
    add(f"ints({s})", f'return match text.ints({s}) {{ Ok(v) => li(v), Err(e) => f"Err({{e}})" }}')
    add(f"longs({s})", f'return match text.longs({s}) {{ Ok(v) => ll(v), Err(e) => f"Err({{e}})" }}')
    add(f"scanner.int({s})", f'var sc = text.scanner({s})\nreturn match sc.int() {{ Ok(v) => f"Ok({{v}})", Err(e) => f"Err({{e}})" }}')
    add(f"scanner.long({s})", f'var sc = text.scanner({s})\nreturn match sc.long() {{ Ok(v) => f"Ok({{v}})", Err(e) => f"Err({{e}})" }}')
    add(f"bigint.parse({s})", f'return match bigint.parse({s}) {{ Ok(b) => f"Ok({{b}})", Err(e) => f"Err({{e}})" }}')


# a case made twice (`swap(0,0)` from both loops) is kept once
for _g in groups.values():
    _seen: set[str] = set()
    _g["cases"] = [c for c in _g["cases"] if not (c[0] in _seen or _seen.add(c[0]))]


def driver_cases(name: str, labels: list[str] | None = None) -> tuple[str, list[str], list[tuple[str, str]]]:
    """The prelude, the case names (the labels) and the driver cases of the
    group `name`, of `labels` only if given."""
    g = groups[name]
    prelude = "import std.process as process\nfrom std.io import println\n"
    if "import std.num as num" not in g["imports"]:
        prelude += "import std.num as num\n"
    prelude += g["imports"] + HELPERS + g["extra"]
    chosen = [(i, label, body) for i, (label, body) in enumerate(g["cases"]) if labels is None or label in set(labels)]
    return prelude, [label for _, label, _ in chosen], [
        (f"fun c{i}() -> str {{\n" + "\n".join("    " + line for line in body.split("\n")) + "\n}\n", f"println(c{i}())")
        for i, _, body in chosen]


GROUPS = list(groups)
