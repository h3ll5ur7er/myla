"""The review's generator of generic code per width (2026-11-12,
`repro-r5/interp/gen.py`): generic functions, methods, impls of the operator
traits, closures, iterators, trait functions without `self` and tail calls,
instantiated with each integer width and both float widths (and a second
type beside it), at each type's limits. The safe statements must print the
same under `myla run`, `--checked` and a plain build; each of the trap
statements (an integer type's limit passed) must be the runtime error
`integer overflow`, the same under `myla run` and `--checked`."""
from __future__ import annotations

INTS = {
    "int8": (8, True, "i8"), "int16": (16, True, "i16"), "int32": (32, True, "i32"), "int64": (64, True, "i64"),
    "uint8": (8, False, "u8"), "uint16": (16, False, "u16"), "uint32": (32, False, "u32"), "uint64": (64, False, "u64"),
}
FLOATS = {"float32": "f32", "float64": "f64"}

def is_int(ty): return ty in INTS
def rng(ty):
    b, s, _ = INTS[ty]
    return (-(1 << (b - 1)), (1 << (b - 1)) - 1) if s else (0, (1 << b) - 1)
def lit(v, ty):
    if is_int(ty):
        lo, hi = rng(ty)
        assert lo <= v <= hi, (v, ty)
        suf = INTS[ty][2]
        if v == lo and lo < 0:
            return f"({v + 1}{suf} - 1{suf})"
        if v < 0: return f"({v}{suf})"
        return f"{v}{suf}"
    return f"{v}{FLOATS[ty]}"
def tag(ty): return ty

GENERIC = r'''
import std.iter as iter

trait Zero { fun zero() -> Self }
trait Wrap { fun wadd(self, o: Self) -> Self }

fun add<T: Add>(a: T, b: T) -> T { return a + b }
fun sub<T: Sub>(a: T, b: T) -> T { return a - b }
fun mul<T: Mul>(a: T, b: T) -> T { return a * b }
fun div<T: Div>(a: T, b: T) -> T { return a / b }
fun rem<T: Rem>(a: T, b: T) -> T { return a % b }
fun lt<T: Ord>(a: T, b: T) -> bool { return a < b }
fun le<T: Ord>(a: T, b: T) -> bool { return a <= b }
fun gt<T: Ord>(a: T, b: T) -> bool { return a > b }
fun ge<T: Ord>(a: T, b: T) -> bool { return a >= b }
fun eq<T: Eq>(a: T, b: T) -> bool { return a == b }
fun ne<T: Eq>(a: T, b: T) -> bool { return a != b }
fun show<T: Format>(v: T) -> str { return f"{v}" }
fun show_w<T: Format>(v: T) -> str { return f"[{v:>24}]" }
fun show_opt<T: Format>(o: Option<T>) -> str {
    return match o {
        Some(v) => f"S{v}"
        None => "N"
    }
}
fun show_pair<T: Format, U: Format>(p: (T, U)) -> str { return f"({p.0}, {p.1})" }
fun acc<T: Add + Sub + Mul>(a: T, b: T) -> T {
    var s = a
    s += b
    s -= b
    s *= b
    return s
}
fun twice<T: Add>(a: T) -> T { return add(a, a) }
fun quad<T: Add>(a: T) -> T { return twice(twice(a)) }
fun via<T: Add>(a: T, b: T) -> T { return add(a, b) }
fun via2<T: Add, U: Add>(a: T, b: T, c: U, d: U) -> (T, U) { return (add(a, b), add(c, d)) }
fun flip2<T: Add, U: Add>(a: T, b: T, c: U, d: U) -> (U, T) { return via2(c, d, a, b) }
fun ping<T: Add + Ord>(a: T, lim: T, step: T) -> T {
    if !(a < lim) { return a }
    return pong(a + step, lim, step)
}
fun pong<T: Add + Ord>(a: T, lim: T, step: T) -> T {
    if !(a < lim) { return a }
    return ping(a + step, lim, step)
}
fun count_up<T: Add + Ord>(a: T, lim: T, step: T) -> T {
    if !(a < lim) { return a }
    become count_up(a + step, lim, step)
}
fun with_default<T: Add>(a: T, b: T, again: bool = true) -> T {
    if again { return a + b + b }
    return a + b
}
fun pair_lt<T: Ord>(p: (T, T)) -> bool { return p.0 < p.1 }
fun opt_add<T: Add>(a: Option<T>, b: T) -> Option<T> { return a.map((x) => x + b) }
fun largest<T: Ord>(xs: [T]) -> T {
    var m = xs[0]
    for x in xs { if x > m { m = x } }
    return m
}

struct Cell<T> { v: T }
impl<T: Add + Sub + Mul + Ord + Format> Cell<T> {
    fun plus(self, w: T) -> Cell<T> { return Cell { v: self.v + w } }
    fun bump(var self, w: T) { self.v = self.v + w }
    fun bump_get(var self, w: T) -> T {
        self.v += w
        return self.v
    }
    fun below(self, w: T) -> bool { return self.v < w }
    fun text(self) -> str { return f"<{self.v}>" }
    fun conv<U: Add>(self, a: U, b: U) -> U { return a + b }
    fun chain(self, w: T) -> T { return self.plus(w).plus(w).v }
    fun rec(self, n: int, w: T) -> T {
        if n == 0 { return self.v }
        return self.plus(w).rec(n - 1, w)
    }
    fun tail(var self, n: int, w: T) -> T {
        if n == 0 { return self.v }
        self.v = self.v + w
        become self.tail(n - 1, w)
    }
}
impl<T: Add> Add for Cell<T> { fun add(self, other: Cell<T>) -> Cell<T> { return Cell { v: self.v + other.v } } }
impl<T: Ord> Ord for Cell<T> {
    fun cmp(self, other: Cell<T>) -> int {
        if self.v < other.v { return -1 }
        if other.v < self.v { return 1 }
        return 0
    }
}
impl<T: Eq> Eq for Cell<T> { fun eq(self, other: Cell<T>) -> bool { return self.v == other.v } }
impl<T: Format> Format for Cell<T> { fun format(self, spec: str) -> str { return f"C({self.v})" } }

enum Tree<T> { Leaf(T), Node(Tree<T>, Tree<T>) }
fun tsum<T: Add>(t: Tree<T>) -> T {
    return match t {
        Leaf(v) => v
        Node(a, b) => tsum(a) + tsum(b)
    }
}
fun tmax<T: Ord>(t: Tree<T>) -> T {
    return match t {
        Leaf(v) => v
        Node(a, b) => {
            let x = tmax(a)
            let y = tmax(b)
            if x < y { y } else { x }
        }
    }
}

impl<T: Add + Ord> [T] {
    fun total2(self, z: T) -> T {
        var s = z
        for x in self { s = s + x }
        return s
    }
    fun biggest(self) -> T {
        var m = self[0]
        for x in self { if m < x { m = x } }
        return m
    }
    fun add_all(var self, k: T) {
        var i = 0
        while i < self.len() {
            self[i] = self[i] + k
            i += 1
        }
    }
}
impl<K: Eq + Hash, V: Add + Ord> [K: V] {
    fun sumv(self, z: V) -> V {
        var s = z
        for k in self.keys() { s = s + self[k] }
        return s
    }
    fun maxv(self, z: V) -> V {
        var m = z
        for k in self.keys() { if m < self[k] { m = self[k] } }
        return m
    }
}

fun adder<T: Add>(k: T) -> (T) -> T { return (x: T) => x + k }
fun below_fn<T: Ord>(k: T) -> (T) -> bool { return (x: T) => x < k }
fun nested<T: Add>(k: T) -> () -> (T) -> T { return () => (x: T) => x + k }
fun map_add<T: Add>(xs: [T], k: T) -> [T] { return xs.map((x) => x + k) }
fun fold_add<T: Add>(xs: [T], z: T) -> T { return xs.fold(z, (a, x) => a + x) }
fun sort_desc<T: Ord>(xs: [T]) -> [T] { return xs.sorted_by((a, b) => b < a) }
fun sort_shift<T: Ord + Sub>(xs: [T], k: T) -> [T] {
    var ys = xs
    ys.sort_by((a, b) => a - k < b - k)
    return ys
}
fun filter_lt<T: Ord>(xs: [T], k: T) -> [T] { return xs.filter((x) => x < k) }
fun join<T: Format>(xs: [T]) -> str {
    var s = ""
    for x in xs { s = s + f"{x} " }
    return s
}
fun sumz<T: Zero + Add>(xs: [T]) -> T {
    var s = T.zero()
    for x in xs { s = s + x }
    return s
}
fun wsum<T: Wrap>(a: T, b: T) -> T { return a.wadd(b) }

struct Steps<T> { cur: T, step: T, left: int }
impl<T: Add> Iterator<T> for Steps<T> {
    fun next(var self) -> Option<T> {
        if self.left == 0 { return None }
        self.left -= 1
        self.cur = self.cur + self.step
        return Some(self.cur)
    }
}
fun run_steps<T: Add + Format>(c: T, s: T, n: int) -> str {
    var out = ""
    for x in (Steps { cur: c, step: s, left: n }) { out = out + f"{x} " }
    return out
}
fun lazy_sum<T: Add>(xs: [T], k: T, z: T) -> T {
    return xs.iter() |> iter.map((x) => x + k) |> iter.sum(z)
}
fun lazy_fold<T: Add + Ord>(xs: [T], k: T, z: T) -> T {
    return xs.iter() |> iter.filter((x) => x < k) |> iter.fold(z, (a, x) => a + x)
}
// a closure made in one generic function, invoked in another whose own
// type parameter is bound to something else
fun invoke_in<U: Add + Format, R: Format>(f: () -> R, u: U) -> str { return f"{add(u, u)} {f()} {add(u, u)}" }
fun thunk_add<T: Add>(a: T, b: T) -> () -> T { return () => add(a, b) }
fun thunk_op<T: Add>(a: T, b: T) -> () -> T { return () => a + b }
'''

def concrete(ty):
    t = tag(ty)
    zero = "0" if is_int(ty) else "0.0"
    w = f"impl Wrap for {ty} {{ fun wadd(self, o: {ty}) -> {ty} {{ return self.wrapping_add(o) }} }}" if is_int(ty) else \
        f"impl Wrap for {ty} {{ fun wadd(self, o: {ty}) -> {ty} {{ return self + o }} }}"
    return f'''
impl Zero for {ty} {{ fun zero() -> {ty} {{ return {zero} }} }}
{w}
struct M_{t} {{ c: {ty} }}
impl Add for M_{t} {{ fun add(self, other: M_{t}) -> M_{t} {{ return M_{t} {{ c: self.c + other.c }} }} }}
impl Ord for M_{t} {{ fun cmp(self, other: M_{t}) -> int {{ if self.c < other.c {{ return -1 }}; if self.c > other.c {{ return 1 }}; return 0 }} }}
impl Format for M_{t} {{ fun format(self, spec: str) -> str {{ return f"M({{self.c}})" }} }}
struct Holder_{t} {{ f: ({ty}) -> {ty}, g: ({ty}) -> bool }}
fun call_holder_{t}(h: Holder_{t}, x: {ty}) -> str {{ return f"{{h.f(x)}} {{h.g(x)}}" }}
fun use_in_other_{t}<U: Add + Format>(f: ({ty}) -> {ty}, x: {ty}, u: U) -> str {{ return f"{{f(x)}} {{add(u, u)}}" }}
'''

def vals(ty):
    """named values for a type: (hi, lo, near-hi a, small b, etc.)"""
    if is_int(ty):
        lo, hi = rng(ty)
        return dict(hi=hi, lo=lo, a=hi - 5, b=2, one=1, two=2, three=3, half=hi // 2, seven=7, q=hi // 4)
    return dict(hi=16777216.0, lo=-16777216.0, a=0.1, b=0.2, one=1.0, two=2.0, three=3.0, half=0.3, seven=7.0, q=1e10)

def safe_body(ty, other):
    """statements (each prints) that don't overflow"""
    v = vals(ty); L = lambda k: lit(v[k], ty)
    o = vals(other); OL = lambda k: lit(o[k], other)
    t = tag(ty)
    hi, lo, a, b, one, two, three, half, seven, q = (L(k) for k in "hi lo a b one two three half seven q".split())
    S = []
    P = lambda e: S.append(f"print({e})")
    P(f'"{ty}: " + show(add({a}, {b})) + " " + show(sub({hi}, {one})) + " " + show(mul({half}, {two})) + " " + show(div({hi}, {two})) + " " + show(div({hi}, {seven}))')
    if is_int(ty): P(f'show(rem({hi}, {seven})) + " " + show(rem({a}, {three}))')
    P(f'f"{{lt({lo}, {hi})}} {{lt({hi}, {lo})}} {{le({hi}, {hi})}} {{gt({hi}, {half})}} {{ge({lo}, {hi})}} {{eq({hi}, {hi})}} {{ne({hi}, {lo})}} {{eq({half}, {hi})}}"')
    P(f'show_w({hi}) + show_w({lo}) + show_opt(Some({hi})) + show_pair(({hi}, {OL("hi")})) + show_pair(({OL("lo")}, {lo}))')
    P(f'show(acc({q}, {two}))')
    P(f'show(twice({half})) + " " + show(quad({q})) + " " + show(via({a}, {b}))')
    P(f'show_pair(via2({a}, {b}, {OL("a")}, {OL("b")})) + show_pair(flip2({a}, {b}, {OL("a")}, {OL("b")}))')
    lim = hi if is_int(ty) else seven
    P(f'show(ping({a}, {lim}, {one})) + " " + show(count_up({a}, {lim}, {one})) + " " + show(with_default({q}, {one})) + " " + show(with_default({a}, {two}, false))')
    P(f'f"{{pair_lt(({lo}, {hi}))}} {{pair_lt(({hi}, {lo}))}} " + show_opt(opt_add(Some({a}), {b})) + " " + show(largest([{one}, {hi}, {lo}, {half}]))')
    S.append(f"var c_{t} = Cell {{ v: {a} }}")
    S.append(f"c_{t}.bump({one})")
    P(f'c_{t}.text() + " " + show(c_{t}.bump_get({one})) + " " + c_{t}.plus({one}).text() + f" {{c_{t}.below({hi})}} {{c_{t}.below({lo})}} " + show(c_{t}.conv({OL("a")}, {OL("b")})) + " " + show(Cell {{ v: {q} }}.chain({one})) + " " + show(Cell {{ v: {q} }}.rec(3, {one})) + " " + show(c_{t}.tail(2, {one}))')
    P(f'show(add(Cell {{ v: {a} }}, Cell {{ v: {b} }})) + f" {{lt(Cell {{ v: {lo} }}, Cell {{ v: {hi} }})}} {{Cell {{ v: {hi} }} < Cell {{ v: {lo} }}}} {{eq(Cell {{ v: {hi} }}, Cell {{ v: {hi} }})}} {{[Cell {{ v: {hi} }}] == [Cell {{ v: {lo} }}]}}" + show(add(Cell {{ v: Cell {{ v: {a} }} }}, Cell {{ v: Cell {{ v: {b} }} }}))')
    P(f'show(largest([Cell {{ v: {half} }}, Cell {{ v: {hi} }}, Cell {{ v: {lo} }}])) + join([Cell {{ v: {hi} }}, Cell {{ v: {lo} }}, Cell {{ v: {half} }}].sorted())')
    P(f'show(add(M_{t} {{ c: {a} }}, M_{t} {{ c: {b} }})) + f" {{lt(M_{t} {{ c: {lo} }}, M_{t} {{ c: {hi} }})}} " + show(add(Cell {{ v: M_{t} {{ c: {a} }} }}, Cell {{ v: M_{t} {{ c: {b} }} }}))')
    P(f'show(tsum(Tree.Node(Tree.Node(Tree.Leaf({q}), Tree.Leaf({q})), Tree.Leaf({one})))) + " " + show(tmax(Tree.Node(Tree.Node(Tree.Leaf({lo}), Tree.Leaf({hi})), Tree.Leaf({half}))))')
    S.append(f"var l_{t}: [{ty}] = [{q}, {one}, {two}]")
    S.append(f"l_{t}.add_all({one})")
    P(f'show(l_{t}.total2({one})) + " " + show([{half}, {hi}, {lo}].biggest()) + " " + join(l_{t}) + show(l_{t}.sum({one})) + " " + join([{hi}, {lo}, {half}].sorted()) + f"{{[{lo}, {hi}].is_sorted()}} " + show_opt([{hi}, {lo}, {half}].max_by((x, y) => x < y))')
    S.append(f'let m_{t}: [str: {ty}] = ["a": {q}, "b": {one}, "c": {hi}]')
    S.append(f'let m2_{t}: [str: {ty}] = ["a": {q}, "b": {one}]')
    P(f'show(m2_{t}.sumv({one})) + " " + show(m_{t}.maxv({lo}))')
    S.append(f"let ad_{t} = adder({b})")
    S.append(f"let bl_{t} = below_fn({half})")
    S.append(f"let h_{t} = Holder_{t} {{ f: ad_{t}, g: bl_{t} }}")
    P(f'show(ad_{t}({a})) + f" {{bl_{t}({hi})}} {{bl_{t}({lo})}} " + show(nested({b})()({a})) + " " + call_holder_{t}(h_{t}, {a}) + " " + use_in_other_{t}(ad_{t}, {a}, {OL("q")})')
    P(f'join(map_add([{q}, {one}], {two})) + show(fold_add([{q}, {one}, {two}], {one})) + " " + join(sort_desc([{half}, {hi}, {lo}])) + join(filter_lt([{half}, {hi}, {lo}], {half}))')
    P(f'join(sort_shift([{half}, {hi}, {a}], {one}))')
    P(f'show(sumz([{q}, {one}, {two}])) + " " + show(wsum({hi}, {one})) + " " + run_steps({q}, {one}, 3) + show(lazy_sum([{q}, {one}], {one}, {one})) + " " + show(lazy_fold([{q}, {hi}, {one}], {half}, {one}))')
    P(f'invoke_in(thunk_add({a}, {b}), {OL("q")}) + " " + invoke_in(thunk_op({a}, {b}), {OL("q")})')
    return S

def trap_stmts(ty):
    """(name, statements) each of which must trap with integer overflow"""
    v = vals(ty); L = lambda k: lit(v[k], ty)
    t = tag(ty)
    hi, lo, a, b, one, two, three, half, seven, q = (L(k) for k in "hi lo a b one two three half seven q".split())
    o64 = "100i64" if ty != "int64" else "100i8"
    T = []
    def P(name, e, pre=()): T.append((name, list(pre) + [f"print({e})"]))
    P("add", f"show(add({hi}, {one}))")
    P("sub", f"show(sub({lo}, {one}))")
    P("mul", f"show(mul({hi}, {two}))")
    if INTS[ty][1]:
        P("divmin", f"show(div({lo}, {lit(-1, ty)}))")
    P("acc", f"show(acc({hi}, {two}))")
    P("twice", f"show(twice({hi}))")
    P("quad", f"show(quad({half}))")
    P("via", f"show(via({hi}, {one}))")
    P("via2_first", f"show_pair(via2({hi}, {one}, {o64}, {o64}))")
    P("via2_second", f"show_pair(via2({o64}, {o64}, {hi}, {one}))")
    P("flip2", f"show_pair(flip2({o64}, {o64}, {hi}, {one}))")
    P("ping", f"show(ping({a}, {hi}, {seven}))")
    P("count_up", f"show(count_up({a}, {hi}, {seven}))")
    P("with_default", f"show(with_default({a}, {three}))")
    P("opt_add", f"show_opt(opt_add(Some({hi}), {one}))")
    P("cell_plus", f"Cell {{ v: {hi} }}.plus({one}).text()")
    P("cell_bump", f"c.text()", pre=[f"var c = Cell {{ v: {hi} }}", f"c.bump({one})"])
    P("cell_bump_get", f"show(c.bump_get({one}))", pre=[f"var c = Cell {{ v: {hi} }}"])
    P("cell_conv", f"show(Cell {{ v: {o64} }}.conv({hi}, {one}))")
    P("cell_chain", f"show(Cell {{ v: {a} }}.chain({three}))")
    P("cell_rec", f"show(Cell {{ v: {a} }}.rec(3, {three}))")
    P("cell_tail", f"show(c.tail(3, {three}))", pre=[f"var c = Cell {{ v: {a} }}"])
    P("cell_add", f"show(add(Cell {{ v: {hi} }}, Cell {{ v: {one} }}))")
    P("cell_op", f"show(Cell {{ v: {hi} }} + Cell {{ v: {one} }})")
    P("cell_cell_add", f"show(add(Cell {{ v: Cell {{ v: {hi} }} }}, Cell {{ v: Cell {{ v: {one} }} }}))")
    P("m_add", f"show(add(M_{t} {{ c: {hi} }}, M_{t} {{ c: {one} }}))")
    P("cell_m_add", f"show(add(Cell {{ v: M_{t} {{ c: {hi} }} }}, Cell {{ v: M_{t} {{ c: {one} }} }}))")
    P("tsum", f"show(tsum(Tree.Node(Tree.Node(Tree.Leaf({half}), Tree.Leaf({half})), Tree.Leaf({two}))))")
    P("total2", f"show([{hi}, {one}].total2({one}))")
    P("add_all", f"join(l)", pre=[f"var l: [{ty}] = [{one}, {hi}]", f"l.add_all({one})"])
    P("list_sum", f"show([{hi}, {one}].sum({one}))")
    P("sumv", f"show(m.sumv({one}))", pre=[f'let m: [str: {ty}] = ["a": {hi}, "b": {one}]'])
    P("adder", f"show(adder({one})({hi}))")
    P("nested", f"show(nested({one})()({hi}))")
    P("holder", f"call_holder_{t}(Holder_{t} {{ f: adder({one}), g: below_fn({one}) }}, {hi})")
    P("use_in_other", f"use_in_other_{t}(adder({one}), {hi}, {o64})")
    P("map_add", f"join(map_add([{one}, {hi}], {one}))")
    P("fold_add", f"show(fold_add([{hi}, {one}], {one}))")
    if not INTS[ty][1]:
        P("sort_shift", f"join(sort_shift([{one}, {two}, {three}], {two}))")
    else:
        P("sort_shift", f"join(sort_shift([{lo}, {two}, {three}], {two}))")
    P("sumz", f"show(sumz([{hi}, {one}]))")
    P("steps", f"run_steps({a}, {three}, 3)")
    P("lazy_sum", f"show(lazy_sum([{a}, {one}], {three}, {three}))")
    P("lazy_fold", f"show(lazy_fold([{half}, {half}, {one}], {hi}, {three}))")
    P("invoke_in_add", f"invoke_in(thunk_add({hi}, {one}), {o64})")
    P("invoke_in_op", f"invoke_in(thunk_op({hi}, {one}), {o64})")
    return T


def other_of(ty):
    return {"int64": "int8", "float32": "uint64", "float64": "float32"}.get(ty, "int64")


def _cases(cases):
    return [n for n, _ in cases], [
        (f"fun case_{n}() {{\n" + "\n".join("    " + s for s in stmts) + "\n}\n", f"case_{n}()") for n, stmts in cases]


def safe_cases(ty: str) -> tuple[str, list[str], list[tuple[str, str]]]:
    """The prelude, case names and driver cases of the safe program of `ty`:
    one case, `safe`, twice the safe statements of `ty` and its second type
    (the review's `safe_<ty>.my`)."""
    other = other_of(ty)
    body = ["for round in 0..2 {"] + ["    " + s for s in safe_body(ty, other) + safe_body(other, ty)] + ["}"]
    return (GENERIC + concrete(ty) + concrete(other), *_cases([("safe", body)]))


def trap_cases(ty: str, traps: list[str] | None = None) -> tuple[str, list[str], list[tuple[str, str]]]:
    """The prelude, case names and driver cases of the trap program of the
    integer type `ty`: a case per trap statement (those of `traps` if
    given), each after the safe statements of the second type (the review's
    `trap_<ty>_<name>.my`). Not for a plain build: there they wrap, and
    some never end."""
    other = other_of(ty)
    warm = safe_body(other, ty)
    return (GENERIC + concrete(ty) + concrete(other),
            *_cases([(name, warm + stmts) for name, stmts in trap_stmts(ty) if traps is None or name in traps]))


def trap_names(ty: str) -> list[str]:
    return [name for name, _ in trap_stmts(ty)] if is_int(ty) else []


TYPES = list(INTS) + list(FLOATS)
