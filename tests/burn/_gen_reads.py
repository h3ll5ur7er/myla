"""The review's generator of reads beside a mutation (2026-11-12,
`repro-r5/native/gen_rd.py`, MYLA-543's B2): an expression reads a value
from a container (a list's element, a map's value, a field, a nested list, a
struct in a list, a closure in a list) and a later operand of the same
expression calls a `var self` method that replaces every container. The read
must be the old value: 90 forms (binary operators, comparisons, calls,
method calls, indexes, slices, f-string holes, literals, `match`
scrutinees, pipes, partial applications, `&&`, casts, …)."""
from __future__ import annotations

PRE = '''from std.io import println

enum E { V(str, str), W([str], int) }
struct P { a: str, b: str }
struct In { xs: [str], name: str }

struct H {
    xs: [str], m: [int: str], g: [[str]], ins: [In], name: str, inn: In,
    fs: [(int) -> str], o: Option<str>, n: int,
}

fun mk(n: int) -> str { return f"s{n}" }

fun fresh() -> H {
    return H {
        xs: [mk(10), mk(11), mk(12)], m: [0: mk(20), 1: mk(21)], g: [[mk(30), mk(31)], [mk(32), mk(33)]],
        ins: [In { xs: [mk(40), mk(41)], name: mk(42) }, In { xs: [mk(43), mk(44)], name: mk(45) }],
        name: mk(50), inn: In { xs: [mk(51), mk(52)], name: mk(53) },
        fs: [(i: int) => mk(60 + i), (i: int) => mk(70 + i)], o: Some(mk(80)), n: 0,
    }
}

fun shl(xs: [str]) -> str {
    var sb = StringBuilder()
    for x in xs {
        sb.append(x)
        sb.append(",")
    }
    return sb.build()
}

impl H {
    fun repl(var self) {
        self.xs = [mk(110), mk(111), mk(112)]
        self.m = [0: mk(120), 1: mk(121)]
        self.g = [[mk(130), mk(131)], [mk(132), mk(133)]]
        self.ins = [In { xs: [mk(140), mk(141)], name: mk(142) }, In { xs: [mk(143), mk(144)], name: mk(145) }]
        self.name = mk(150)
        self.inn = In { xs: [mk(151), mk(152)], name: mk(153) }
        self.fs = [(i: int) => mk(160 + i), (i: int) => mk(170 + i)]
        self.o = Some(mk(180))
        self.n += 1
    }
    fun k(var self) -> int { self.repl(); return 1 }
    fun s(var self) -> str { self.repl(); return "!" }
    fun l(var self) -> [str] { self.repl(); return ["L"] }
    fun b(var self) -> bool { self.repl(); return true }
    fun peek(self) -> str { return self.xs[0] }
}

fun cat(a: str, b: str) -> str { return a + "+" + b }
fun cat3(a: str, b: str, c: str) -> str { return a + "+" + b + "+" + c }
fun catl(a: [str], b: str) -> str { return shl(a) + "+" + b }
fun catli(a: [str], i: int) -> str { return shl(a) + f"+{i}" }
fun pick(a: [str], i: int) -> str { return a[i] }
fun idl(a: [str]) -> [str] { return a }
fun ids(a: str) -> str { return a }

impl str {
    fun with(self, o: str) -> str { return self + "~" + o }
}
impl [str] {
    fun withl(self, o: str) -> str { return shl(self) + "~" + o }
    fun at(self, i: int) -> str { return self[i] }
}
impl In {
    fun nm(self, o: str) -> str { return self.name + "~" + o + "~" + shl(self.xs) }
}
'''
cases = []
def add(n, body): cases.append((n, body))
# r: expression giving str printed
E = [
 ('bin_l', 'h.xs[0] + h.s()'),
 ('bin_m', 'h.m[0] + h.s()'),
 ('bin_g', 'h.g[0][0] + h.s()'),
 ('bin_f', 'h.name + h.s()'),
 ('bin_inn', 'h.inn.name + h.s()'),
 ('bin_ins', 'h.ins[0].name + h.s()'),
 ('bin_3', 'h.xs[0] + h.xs[1] + h.s()'),
 ('bin_par', 'h.xs[0] + (h.xs[1] + h.s())'),
 ('bin_local', '{ let a = h.xs[0]; a + h.s() }'),
 ('cmp_eq', 'f"{h.xs[0] == h.s()}"'),
 ('cmp_lt', 'f"{h.xs[0] < h.s()}"'),
 ('cmp_leq', 'f"{h.xs == h.l()}"'),
 ('call2', 'cat(h.xs[0], h.s())'),
 ('call3', 'cat3(h.xs[0], h.m[1], h.s())'),
 ('call_l', 'catl(h.xs, h.s())'),
 ('call_gl', 'catl(h.g[0], h.s())'),
 ('call_li', 'catli(h.xs, h.k())'),
 ('call_gli', 'catli(h.g[0], h.k())'),
 ('call_innl', 'catl(h.inn.xs, h.s())'),
 ('call_insl', 'catl(h.ins[0].xs, h.s())'),
 ('pick', 'pick(h.xs, h.k())'),
 ('pickg', 'pick(h.g[1], h.k())'),
 ('meth_s', 'h.xs[0].with(h.s())'),
 ('meth_l', 'h.xs.withl(h.s())'),
 ('meth_gl', 'h.g[0].withl(h.s())'),
 ('meth_at', 'h.xs.at(h.k())'),
 ('meth_gat', 'h.g[0].at(h.k())'),
 ('meth_in', 'h.ins[0].nm(h.s())'),
 ('meth_inn', 'h.inn.nm(h.s())'),
 ('idx', 'h.xs[h.k()]'),
 ('idx_g', 'h.g[0][h.k()]'),
 ('idx_g2', 'h.g[h.k()][0]'),
 ('idx_m', 'h.m[h.k()]'),
 ('idx_ins', 'h.ins[0].xs[h.k()]'),
 ('idx_ins2', 'h.ins[h.k()].name'),
 ('idx_bytes', 'f"{h.xs[0][h.k()]}"'),
 ('slice', 'shl(h.xs[h.k():])'),
 ('slice_g', 'shl(h.g[0][h.k():])'),
 ('slice_s', 'h.xs[0][h.k():]'),
 ('fstr', 'f"{h.xs[0]}{h.s()}"'),
 ('fstr2', 'f"{h.xs[0]}{h.s()}{h.xs[0]}"'),
 ('fstr_g', 'f"{h.g[0][0]}{h.s()}"'),
 ('fmt', 'format("{}{}", h.xs[0], h.s())'),
 ('listlit', 'shl([h.xs[0], h.s()])'),
 ('listlit_g', 'shl([h.g[0][1], h.m[0], h.s()])'),
 ('tuplit', '{ let t = (h.xs[0], h.s()); t.0 + t.1 }'),
 ('tuplit_l', '{ let t = (h.xs, h.s()); shl(t.0) + t.1 }'),
 ('tuplit_g', '{ let t = (h.g[0], h.s()); shl(t.0) + t.1 }'),
 ('structlit', '{ let p = P { a: h.xs[0], b: h.s() }; p.a + p.b }'),
 ('structlit_in', '{ let p = In { xs: h.xs, name: h.s() }; shl(p.xs) + p.name }'),
 ('structlit_g', '{ let p = In { xs: h.g[0], name: h.s() }; shl(p.xs) + p.name }'),
 ('enumlit', 'match E.V(h.xs[0], h.s()) { V(a, b) => a + b, W(l, i) => "w" }'),
 ('enumlit_w', 'match E.W(h.xs, h.k()) { V(a, b) => a + b, W(l, i) => shl(l) }'),
 ('enumlit_gw', 'match E.W(h.g[0], h.k()) { V(a, b) => a + b, W(l, i) => shl(l) }'),
 ('maplit', '{ let m = [h.xs[0]: h.s()]; var q = ""; for k in m { q = q + k + m[k] }; q }'),
 ('maplit2', '{ let m = [1: h.xs[0], 2: h.s()]; m[1] + m[2] }'),
 ('some', 'match (Some(h.xs[0]), h.s()) { (Some(a), b) => a + b, (None, b) => b }'),
 ('opt', 'match (h.o, h.s()) { (Some(a), b) => a + b, (None, b) => b }'),
 ('fcall', 'h.fs[0](h.k())'),
 ('fcall2', '{ let f = h.fs[0]; f(h.k()) }'),
 ('pipe', 'h.xs[0] |> cat(h.s())'),
 ('pipe_l', 'h.xs |> catl(h.s())'),
 ('partial', '{ let p = cat(h.xs[0], _); let z = h.s(); p(z) }'),
 ('and', 'f"{h.xs[0] == "s10" && h.b()}{h.xs[0]}"'),
 ('match_scrut', 'match h.xs[0] + h.s() { "s10!" => "ok", _ => "bad" }'),
 ('len_bin', 'f"{h.xs[0].len() + h.k()}"'),
 ('concat', 'shl(h.xs.concat(h.l()))'),
 ('concat_g', 'shl(h.g[0].concat(h.l()))'),
 ('unwrap_or', 'h.o.unwrap_or(h.s())'),
 ('get_or', 'h.m.get_or(0, h.s())'),
 ('get_or2', 'h.m.get_or(h.k(), "d")'),
 ('contains', 'f"{h.xs.contains(h.s())}"'),
 ('peek', 'h.peek() + h.s()'),
 ('idc', 'ids(h.xs[0]) + h.s()'),
 ('idlc', 'shl(idl(h.xs)) + h.s()'),
 ('idlc_g', 'shl(idl(h.g[0])) + h.s()'),
 ('nested_call', 'cat(cat(h.xs[0], h.xs[1]), h.s())'),
 ('nested_call2', 'cat(h.xs[0], cat(h.xs[1], h.s()))'),
 ('if_e', 'h.xs[0] + (if h.b() { "T" } else { "F" })'),
 ('if_e_g', 'catl(h.g[0], if h.b() { "T" } else { "F" })'),
 ('match_e', 'h.xs[0] + match h.b() { true => "T", false => "F" }'),
 ('cast_bin', 'f"{h.xs[0].len() as int64 + h.k() as int64}"'),
 ('join', '[h.xs[0], h.name].join(h.s())'),
 ('split', 'shl(h.xs[0].split(h.s()))'),
 ('starts', 'f"{h.xs[0].starts_with(h.s())}"'),
 ('sbuild', '{ var sb = StringBuilder(); sb.append(h.xs[0]); sb.append(h.s()); sb.append(h.xs[0]); sb.build() }'),
 ('sbuild3', '{ var sb = StringBuilder(); sb.append(h.xs[0], 0, h.k()); sb.build() }'),
 ('push_l', '{ var out: [str] = []; out.push(h.xs[0] + h.s()); shl(out) }'),
 ('ret_field', 'h.inn.name.with(h.inn.xs[0]).with(h.s())'),
]
for n, e in E:
    if e.startswith('{'):
        # block: last expr is the value; turn into statements
        inner = e[1:-1].strip()
        parts = [p.strip() for p in inner.split(';')]
        body = '\n    '.join(parts[:-1]) + f'\n    let r = {parts[-1]}'
    else:
        body = f'let r = {e}'
    add(n, body)


def driver_cases(names: list[str] | None = None) -> tuple[list[str], list[tuple[str, str]]]:
    """The case names and the driver cases, of `names` only if given."""
    chosen = [c for c in cases if names is None or c[0] in set(names)]
    return [n for n, _ in chosen], [
        (f'fun c_{n}() {{\n    var h = fresh()\n    {body}\n    println("{n} " + r + " | " + h.xs[0] + f" {{h.n}}")\n}}\n',
         f"c_{n}()")
        for n, body in chosen]
