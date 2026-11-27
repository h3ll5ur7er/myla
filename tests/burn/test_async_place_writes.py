"""Burn test: a write to a place in async code against its sync twin (H5, M11
of the review of 2026-11-17, MYLA-791, MYLA-809).

Every runner agreed on the wrong answer here, so runners compared with each
other never saw it: in an async function, a mutating method on a place
(`g[i + 1].push(await f())`, `c.rows[await f()].push(x)`) changed a copy of
the place, as std.anf's `Norm.callee` put a receiver that wasn't a name or
`name[literal]` into a temporary when the call had an `await` (26 of the
review's 36 forms differed). The expectation is the twin: the same statement
in a function that isn't async, with the awaited calls plain ones. Each form
is run both ways in one program, which prints `same <form>` when the two
leave the same state, and that program must print the same interpreted and
natively (`MYLA_TEST_TARGET` picks the target).

The forms are the review's (`repro-r6/native/generators/mkaw.py`), with a
place counted from the end, an order the twin records (`c.tick`) and the
awaited slice bounds of M11.
"""
from __future__ import annotations

import tempfile
import unittest

from ._native import CAN_BUILD_NATIVE, SKIP_REASON, Program, build_and_run_full, selfhost_run, write_program

# (name, statement): `{i0}`, `{i1}` an index, `{v}` an int and `{s}` a str
# value, awaited in the async twin
FORMS = [
    ('local_1', 'g[{i1}].push(9)'), ('field_1', 'c.g[{i1}].push(9)'), ('local_lit_aw', 'gg[0][{i1}].push(9)'),
    ('local_aw_lit', 'gg[{i1}][0].push(9)'), ('local_aw_aw', 'gg[{i0}][{i1}].push(9)'), ('field_put', 'c.g[{i1}].put(9)'),
    ('field_struct_method', 'c.ins[{i1}].set(9)'), ('field_struct_field_push', 'c.ins[{i1}].xs.push(9)'),
    ('map_elem', 'c.m[{i1}].push(9)'), ('local_map_elem', 'm[{i1}].push(9)'), ('sb', 'c.sb[{i1}].append("x")'),
    ('assign', 'c.g[{i1}][0] = 9'), ('cmpd', 'c.g[{i1}][0] += 9'), ('cmpd_local', 'g[{i1}][0] += 9'),
    ('iter', 'let z = c.it[{i1}].next()'), ('enum', 'c.e[{i1}].flip(9)'), ('str_bump', 'c.ss[{i1}].bump("x")'),
    ('str_cmpd', 'c.ss[{i1}] += "x"'), ('arg_aw_place', 'c.g[1].push({v})'), ('arg_aw_expr_index', 'c.g[one + 0].push({v})'),
    ('arg_aw_local_expr_index', 'g[one + 0].push({v})'), ('arg_aw_len_index', 'g[g.len() - 1].push({v})'),
    ('arg_aw_put', 'c.g[one + 0].put({v})'), ('arg_aw_struct', 'c.ins[one + 0].set({v})'),
    ('arg_aw_map', 'c.m[one + 0].push({v})'), ('arg_aw_sb', 'c.sb[one + 0].append({s})'),
    ('arg_aw_name_index', 'g[one].push({v})'), ('arg_aw_insert', 'g[one + 0].insert(0, {v})'),
    ('arg_aw_extend', 'g[one + 0].extend([{v}])'), ('arg_aw_enum', 'c.e[one + 0].flip({v})'),
    ('arg_aw_nested_field', 'c.ins[one + 0].xs.push({v})'), ('pop', 'let z = c.g[{i1}].pop()'),
    ('remove', 'c.mm[{i1}].remove(0)'), ('local_pop_expr', 'let z = gg[0][{i1}].pop()'),
    ('field_len_only', 'let z = c.g[{i1}].len()'), ('method_on_call_index', 'g[idx(one)].push({v})'),
    # a place counted from the end (D142)
    ('from_end_index', 'g[^{i1}].push(9)'), ('from_end_arg', 'c.g[^(one + 0)].push({v})'),
    # the place's indices first, left to right, then the arguments (D193)
    ('order_index_arg', 'c.g[c.tick(1)].push({v})'), ('order_index_index', 'gg[c.tick(1)][{i0}].push(c.tick(2))'),
    ('order_assign', 'gg[c.tick(1)][{i1}] = [c.tick(3)]'), ('order_map_key', 'c.m[c.tick(1)].push({v})'),
    # an awaited slice bound or step (M11)
    ('slice_step', 'g[0] = g[1][::{i1}]'), ('slice_step_neg', 'g[0] = g[1][::0 - {i1}]'),
    ('slice_bounds', 'g[0] = g[1][{i0}:{i1}]'), ('slice_from_end', 'g[0] = g[1][:^{i1}]'),
    ('slice_read', 'c.g[0].push(g[1][{i0}:][0])'),
]

PRELUDE = '''from std.io import println
import std.task as task
struct In { xs: [int], n: int }
enum En { A(int), B([int]) }
struct Ctr { i: int }
impl Iterator<int> for Ctr {
    fun next(var self) -> Option<int> {
        self.i += 1
        return Some(self.i)
    }
}
struct C { g: [[int]], m: [int: [int]], mm: [int: [int: int]], sb: [StringBuilder], ins: [In], e: [En], ss: [str], it: [Ctr], k: int }
fun fresh() -> C {
    return C { g: [[1, 2], [3, 4]], m: [0: [1], 1: [2]], mm: [0: [0: 1], 1: [0: 2, 1: 3]], sb: [StringBuilder(), StringBuilder()],
        ins: [In { xs: [1], n: 1 }, In { xs: [2], n: 2 }], e: [En.A(1), En.B([2])], ss: ["a", "b"], it: [Ctr { i: 0 }, Ctr { i: 5 }], k: 0 }
}
fun idx(i: int) -> int { return i }
fun li(xs: [int]) -> str {
    var sb = StringBuilder()
    for x in xs { sb.append(f"{x},") }
    return sb.build()
}
fun lli(g: [[int]]) -> str {
    var sb = StringBuilder()
    for x in g { sb.append(li(x) + ";") }
    return sb.build()
}
impl [int] {
    fun put(var self, v: int) { self.push(v) }
}
impl str {
    fun bump(var self, o: str) { self = self + o }
}
impl In {
    fun set(var self, v: int) { self.n = v }
}
impl C {
    // the order of the calls, as digits
    fun tick(var self, i: int) -> int {
        self.k = self.k * 10 + i
        return i % 2
    }
}
impl En {
    fun flip(var self, v: int) {
        match self {
            A(n) => { self = En.B([n, v]) }
            B(l) => { self = En.A(l.len() + v) }
        }
    }
}
fun dump(c: C, g: [[int]], gg: [[[int]]], m: [int: [int]]) -> str {
    var sbs = ""
    for b in c.sb {
        var x = b
        sbs = sbs + x.build() + ";"
    }
    var es = ""
    for x in c.e {
        es = es + match x {
            A(n) => f"A{n};"
            B(l) => "B" + li(l) + ";"
        }
    }
    var ins = ""
    for x in c.ins { ins = ins + li(x.xs) + f"/{x.n};" }
    var its = ""
    for x in c.it { its = its + f"{x.i};" }
    return f"c.g={lli(c.g)} c.m={li(c.m[0])}|{li(c.m[1])} c.mm={c.mm[0].len()}|{c.mm[1].len()} sb={sbs} ins={ins} e={es} ss={c.ss.join(",")} it={its} k={c.k} g={lli(g)} gg={lli(gg[0])}|{lli(gg[1])} m={li(m[0])}|{li(m[1])}"
}
fun at(i: int) -> int { return i }
fun val(v: int) -> int { return v }
fun sval(s: str) -> str { return s }
async fun aat(i: int) -> int {
    await task.yield()
    return i
}
async fun aval(v: int) -> int {
    await task.yield()
    return v
}
async fun asval(s: str) -> str {
    await task.yield()
    return s
}
'''

TWINS = (
    ('sync', dict(i0='at(0)', i1='at(1)', v='val(9)', s='sval("x")')),
    ('async', dict(i0='await aat(0)', i1='await aat(1)', v='await aval(9)', s='await asval("x")')),
)


def program() -> str:
    out = [PRELUDE]
    calls = []
    for name, form in FORMS:
        for kind, sub in TWINS:
            a = 'async ' if kind == 'async' else ''
            out.append(f'''{a}fun {kind}_{name}() -> str {{
    var c = fresh()
    var g = [[1, 2], [3, 4]]
    var gg = [[[1, 2], [3, 4]], [[5], [6]]]
    var m = [0: [1], 1: [2]]
    let one = 1
    {form.format(**sub)}
    return dump(c, g, gg, m)
}}''')
        calls.append(f'''    if true {{
        let s = sync_{name}()
        let a = await async_{name}()
        if s == a {{ println("same {name}") }} else {{
            println("DIFFERENT {name}")
            println("    sync  " + s)
            println("    async " + a)
        }}
    }}''')
    out.append('#main\nasync fun main() {\n' + '\n'.join(calls) + '\n}')
    return '\n'.join(out) + '\n'


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class AsyncPlaceWrites(unittest.TestCase):
    def test_every_form_leaves_what_its_sync_twin_leaves(self):
        want = "".join(f"same {name}\n" for name, _ in FORMS)
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, program())
            interp = selfhost_run(path)
            native = build_and_run_full(Program(path))
        self.assertEqual(interp, (want, "", 0))
        self.assertEqual(native, (want, "", 0))

    def test_an_awaited_slice_step(self):
        # M11: `xs[::await one()]` had length 1 interpreted, and was `main
        # can't be lowered to the IR` at build
        src = ("import std.task as task\n\nasync fun one() -> int {\n    await task.yield()\n    return 1\n}\n\n"
               "#main\nasync fun main() {\n    let xs = [1, 2, 3]\n    print(xs[::await one()].len())\n"
               "    print(xs[::0 - await one()][0])\n    print(xs[^(await one() + 1):][0])\n}\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, src)
            self.assertEqual(selfhost_run(path), ("3\n3\n2\n", "", 0))
            self.assertEqual(build_and_run_full(Program(path)), ("3\n3\n2\n", "", 0))


if __name__ == "__main__":
    unittest.main()
