"""The review's generators of writes into containers (2026-11-12,
`repro-r5/native/gen_h4.py` and `gen_loc.py`, the H4 audit): evaluation order
against copy-on-write. Each case is one statement that writes an element (an
int, a str or a list) of a list, a map, a list of lists, a map of lists, a
struct's field or a list of structs, or a local of each of those, while an
index, the value or a `var self` method called in it snapshots, grows,
shrinks or replaces the container; then the whole state is printed. The
containers are a struct's fields (`containers`), or locals in a plain
function, an async function and a lambda (`locals`)."""
from __future__ import annotations

ELEMENTS = ["int", "str", "list"]
CONTEXTS = ["fun", "async", "lambda"]


def containers(ELT: str) -> tuple[str, list[tuple[str, str]]]:
    """The prelude and the cases (name, statement) of gen_h4.py for the
    element `ELT`."""
    if ELT == 'int':
        T = 'int'; MK = 'return n'; SH = 'return f"{x}"'; ADD = True
    elif ELT == 'str':
        T = 'str'; MK = 'return f"s{n}"'; SH = 'return x'; ADD = True
    else:
        T = '[int]'; MK = 'return [n, n + 1]'; SH = 'return f"<{x[0]}.{x.len()}>"'; ADD = False

    PRE = f'''from std.io import println

    fun mk(n: int) -> {T} {{ {MK} }}
    fun sh(x: {T}) -> str {{ {SH} }}

    fun shl(xs: [{T}]) -> str {{
        var sb = StringBuilder()
        sb.append("[")
        for x in xs {{
            sb.append(sh(x))
            sb.append(" ")
        }}
        sb.append("]")
        return sb.build()
    }}

    fun shm(m: [int: {T}]) -> str {{
        var sb = StringBuilder()
        sb.append("{{")
        for k in m {{
            sb.append(f"{{k}}:")
            sb.append(sh(m[k]))
            sb.append(" ")
        }}
        sb.append("}}")
        return sb.build()
    }}

    fun shg(g: [[{T}]]) -> str {{
        var sb = StringBuilder()
        for r in g {{ sb.append(shl(r)) }}
        return sb.build()
    }}

    fun shmg(g: [int: [{T}]]) -> str {{
        var sb = StringBuilder()
        for k in g {{
            sb.append(f"{{k}}=")
            sb.append(shl(g[k]))
        }}
        return sb.build()
    }}

    struct In {{ xs: [{T}], m: [int: {T}] }}

    struct H {{
        xs: [{T}], sxs: [{T}],
        m: [int: {T}], sm: [int: {T}],
        g: [[{T}]], sg: [[{T}]],
        mg: [int: [{T}]], smg: [int: [{T}]],
        inn: In, sinn: In,
        ins: [In], sins: [In],
        sb: StringBuilder, ssb: StringBuilder,
        n: int,
    }}

    fun fresh() -> H {{
        return H {{
            xs: [mk(10), mk(11), mk(12), mk(13)], sxs: [],
            m: [0: mk(20), 1: mk(21), 2: mk(22), 3: mk(23)], sm: [:],
            g: [[mk(30), mk(31), mk(32)], [mk(33), mk(34), mk(35)], [mk(36), mk(37), mk(38)]], sg: [],
            mg: [0: [mk(40), mk(41), mk(42)], 1: [mk(43), mk(44), mk(45)], 2: [mk(46), mk(47), mk(48)]], smg: [:],
            inn: In {{ xs: [mk(50), mk(51), mk(52)], m: [0: mk(53), 1: mk(54), 2: mk(55)] }},
            sinn: In {{ xs: [], m: [:] }},
            ins: [In {{ xs: [mk(60), mk(61), mk(62)], m: [0: mk(63), 1: mk(64)] }}, In {{ xs: [mk(65), mk(66), mk(67)], m: [0: mk(68), 1: mk(69)] }}],
            sins: [],
            sb: StringBuilder(), ssb: StringBuilder(),
            n: 0,
        }}
    }}

    fun dump(label: str, h: H) {{
        var sb = StringBuilder()
        sb.append(label)
        sb.append(" xs="); sb.append(shl(h.xs)); sb.append(" sxs="); sb.append(shl(h.sxs))
        sb.append(" m="); sb.append(shm(h.m)); sb.append(" sm="); sb.append(shm(h.sm))
        sb.append(" g="); sb.append(shg(h.g)); sb.append(" sg="); sb.append(shg(h.sg))
        sb.append(" mg="); sb.append(shmg(h.mg)); sb.append(" smg="); sb.append(shmg(h.smg))
        sb.append(" inn="); sb.append(shl(h.inn.xs)); sb.append(shm(h.inn.m))
        sb.append(" sinn="); sb.append(shl(h.sinn.xs)); sb.append(shm(h.sinn.m))
        sb.append(" ins=")
        for i in h.ins {{ sb.append(shl(i.xs)); sb.append(shm(i.m)) }}
        sb.append(" sins=")
        for i in h.sins {{ sb.append(shl(i.xs)); sb.append(shm(i.m)) }}
        var b1 = h.sb
        var b2 = h.ssb
        sb.append(" sb="); sb.append(b1.build()); sb.append(" ssb="); sb.append(b2.build())
        sb.append(f" n={{h.n}}")
        println(sb.build())
    }}

    impl H {{
        fun snap(var self) {{
            self.sxs = self.xs
            self.sm = self.m
            self.sg = self.g
            self.smg = self.mg
            self.sinn = self.inn
            self.sins = self.ins
            self.ssb = self.sb
            self.n += 1
        }}
        fun grow(var self) {{
            for i in 0..40 {{
                self.xs.push(mk(100 + i))
                self.m[100 + i] = mk(200 + i)
                self.g.push([mk(300 + i)])
                self.g[1].push(mk(400 + i))
                self.mg[100 + i] = [mk(500 + i)]
                self.mg[1].push(mk(600 + i))
                self.inn.xs.push(mk(700 + i))
                self.inn.m[100 + i] = mk(800 + i)
                self.ins.push(In {{ xs: [mk(900 + i)], m: [0: mk(950 + i)] }})
                self.ins[1].xs.push(mk(1000 + i))
                self.ins[1].m[100 + i] = mk(1100 + i)
                self.sb.append("gggggggggggggggggggggggggggggggg")
            }}
            self.n += 10
        }}
        fun shrink(var self) {{
            self.xs.truncate(2)
            self.m.remove(2)
            self.m.remove(3)
            self.m.remove(0)
            self.g.truncate(2)
            self.g[1].truncate(2)
            self.mg.remove(2)
            self.mg.remove(0)
            self.mg[1].truncate(2)
            self.inn.xs.truncate(2)
            self.inn.m.remove(2)
            self.inn.m.remove(0)
            self.ins[1].xs.truncate(2)
            self.ins[1].m.remove(0)
            self.n += 100
        }}
        fun repl(var self) {{
            self.xs = [mk(70), mk(71), mk(72)]
            self.m = [1: mk(73), 5: mk(74)]
            self.g = [[mk(75), mk(76)], [mk(77), mk(78)]]
            self.mg = [1: [mk(79), mk(80)], 7: [mk(81)]]
            self.inn = In {{ xs: [mk(82), mk(83)], m: [1: mk(84)] }}
            self.ins = [In {{ xs: [mk(85), mk(86)], m: [1: mk(87)] }}, In {{ xs: [mk(88), mk(89)], m: [1: mk(90)] }}]
            self.sb = StringBuilder()
            self.sb.append("R")
            self.n += 1000
        }}
        fun snapgrow(var self) {{ self.snap(); self.grow() }}
        fun k_plain(var self) -> int {{ return 1 }}
        fun k_snap(var self) -> int {{ self.snap(); return 1 }}
        fun k_grow(var self) -> int {{ self.grow(); return 1 }}
        fun k_shrink(var self) -> int {{ self.shrink(); return 1 }}
        fun k_repl(var self) -> int {{ self.repl(); return 1 }}
        fun k_snapgrow(var self) -> int {{ self.snap(); self.grow(); return 1 }}
        fun v_plain(var self) -> {T} {{ return mk(1) }}
        fun v_snap(var self) -> {T} {{ self.snap(); return mk(2) }}
        fun v_grow(var self) -> {T} {{ self.grow(); return mk(3) }}
        fun v_shrink(var self) -> {T} {{ self.shrink(); return mk(4) }}
        fun v_repl(var self) -> {T} {{ self.repl(); return mk(5) }}
        fun v_snapgrow(var self) -> {T} {{ self.snap(); self.grow(); return mk(6) }}
        fun l_plain(var self) -> [{T}] {{ return [mk(1), mk(7)] }}
        fun l_snap(var self) -> [{T}] {{ self.snap(); return [mk(2), mk(7)] }}
        fun l_grow(var self) -> [{T}] {{ self.grow(); return [mk(3), mk(7)] }}
        fun l_shrink(var self) -> [{T}] {{ self.shrink(); return [mk(4), mk(7)] }}
        fun l_repl(var self) -> [{T}] {{ self.repl(); return [mk(5), mk(7)] }}
        fun l_snapgrow(var self) -> [{T}] {{ self.snap(); self.grow(); return [mk(6), mk(7)] }}
        fun s_plain(var self) -> str {{ return "p" }}
        fun s_snap(var self) -> str {{ self.snap(); return "q" }}
        fun s_grow(var self) -> str {{ self.grow(); return "r" }}
        fun s_shrink(var self) -> str {{ self.shrink(); return "s" }}
        fun s_repl(var self) -> str {{ self.repl(); return "t" }}
        fun s_snapgrow(var self) -> str {{ self.snap(); self.grow(); return "u" }}
        fun put_at(var self, i: int, v: {T}) {{ self.xs[i] = v }}
        fun put_g(var self, i: int, j: int, v: {T}) {{ self.g[i][j] = v }}
        fun me(self) -> H {{ return self }}
        fun xs_copy(self) -> [{T}] {{ return self.xs }}
    }}

    impl [{T}] {{
        fun set_at(var self, i: int, v: {T}) {{ self[i] = v }}
        fun set2(var self, i: int, v: {T}, j: int, w: {T}) {{
            self[i] = v
            self[j] = w
        }}
    }}

    impl In {{
        fun set_x(var self, i: int, v: {T}) {{ self.xs[i] = v }}
        fun set_m(var self, i: int, v: {T}) {{ self.m[i] = v }}
    }}
    '''

    EFF = ['plain', 'snap', 'grow', 'shrink', 'repl', 'snapgrow']
    def K(e): return f'h.k_{e}()'
    def V(e): return f'h.v_{e}()'
    def L(e): return f'h.l_{e}()'
    def Sx(e): return f'h.s_{e}()'
    # block forms (an `if` expression assigning in its block)
    def KB(e): return 'if h.n >= 0 { h.%s(); 1 } else { 0 }' % e if e != 'plain' else '(if h.n >= 0 { 1 } else { 0 })'
    def VB(e): return ('if h.n >= 0 { h.%s(); mk(8) } else { mk(9) }' % e) if e != 'plain' else '(if h.n >= 0 { mk(8) } else { mk(9) })'
    # match forms
    def KM(e): return 'match h.n >= 0 { true => { h.%s(); 1 }, false => 0 }' % e if e != 'plain' else '1'
    # lambda-called forms can't mutate; skip

    cases = []
    def add(name, stmt):
        cases.append((name, stmt))

    for e in EFF:
        for kf, kn in ((K, 'k'), (KB, 'kb'), (KM, 'km')):
            k = kf(e)
            add(f'lset_{kn}_{e}', f'h.xs[{k}] = mk(1)')
            add(f'mset_{kn}_{e}', f'h.m[{k}] = mk(1)')
            add(f'mrem_{kn}_{e}', f'h.m.remove({k})')
            add(f'mrem2_{kn}_{e}', f'let r = h.m.remove({k})')
            add(f'lins_{kn}_{e}', f'h.xs.insert({k}, mk(1))')
            add(f'lrem_{kn}_{e}', f'let r = h.xs.remove_at({k})')
            add(f'lswap_{kn}_{e}', f'h.xs.swap({k}, 0)')
            add(f'lswap2_{kn}_{e}', f'h.xs.swap(0, {k})')
            add(f'ltrunc_{kn}_{e}', f'h.xs.truncate({k})')
            add(f'gset_{kn}_{e}', f'h.g[{k}][0] = mk(1)')
            add(f'gset2_{kn}_{e}', f'h.g[0][{k}] = mk(1)')
            add(f'gset3_{kn}_{e}', f'h.g[{k}][{k}] = mk(1)')
            add(f'gpush_{kn}_{e}', f'h.g[{k}].push(mk(1))')
            add(f'gtrunc_{kn}_{e}', f'h.g[{k}].truncate(1)')
            add(f'gswap_{kn}_{e}', f'h.g[1].swap(0, {k})')
            add(f'mgset_{kn}_{e}', f'h.mg[{k}][0] = mk(1)')
            add(f'mgset2_{kn}_{e}', f'h.mg[1][{k}] = mk(1)')
            add(f'mgpush_{kn}_{e}', f'h.mg[{k}].push(mk(1))')
            add(f'mgrem_{kn}_{e}', f'h.mg.remove({k})')
            add(f'mgasg_{kn}_{e}', f'h.mg[{k}] = [mk(1)]')
            add(f'innl_{kn}_{e}', f'h.inn.xs[{k}] = mk(1)')
            add(f'innm_{kn}_{e}', f'h.inn.m[{k}] = mk(1)')
            add(f'innr_{kn}_{e}', f'h.inn.m.remove({k})')
            add(f'insl_{kn}_{e}', f'h.ins[{k}].xs[0] = mk(1)')
            add(f'insl2_{kn}_{e}', f'h.ins[0].xs[{k}] = mk(1)')
            add(f'insm_{kn}_{e}', f'h.ins[{k}].m[0] = mk(1)')
            add(f'insm2_{kn}_{e}', f'h.ins[1].m[{k}] = mk(1)')
            add(f'insp_{kn}_{e}', f'h.ins[{k}].xs.push(mk(1))')
            add(f'inssx_{kn}_{e}', f'h.ins[{k}].set_x(0, mk(1))')
            add(f'inssx2_{kn}_{e}', f'h.ins[1].set_x({k}, mk(1))')
            add(f'inssm_{kn}_{e}', f'h.ins[1].set_m({k}, mk(1))')
            add(f'innsx_{kn}_{e}', f'h.inn.set_x({k}, mk(1))')
            add(f'put_{kn}_{e}', f'h.put_at({k}, mk(1))')
            add(f'putg_{kn}_{e}', f'h.put_g({k}, 0, mk(1))')
            add(f'putg2_{kn}_{e}', f'h.put_g(0, {k}, mk(1))')
            add(f'setat_{kn}_{e}', f'h.xs.set_at({k}, mk(1))')
            add(f'gsetat_{kn}_{e}', f'h.g[{k}].set_at(0, mk(1))')
            add(f'gsetat2_{kn}_{e}', f'h.g[1].set_at({k}, mk(1))')
            add(f'set2_{kn}_{e}', f'h.xs.set2(0, mk(1), {k}, mk(2))')
            add(f'mupd_{kn}_{e}', f'h.m.update({k}, mk(1), (v) => v)')
            add(f'sbapp_{kn}_{e}', f'h.sb.append("abcdef", {k}, 3)')
            if ADD:
                add(f'ladd_{kn}_{e}', f'h.xs[{k}] += mk(1)')
                add(f'madd_{kn}_{e}', f'h.m[{k}] += mk(1)')
                add(f'gadd_{kn}_{e}', f'h.g[{k}][{k}] += mk(1)')
                add(f'mgadd_{kn}_{e}', f'h.mg[{k}][0] += mk(1)')
                add(f'insadd_{kn}_{e}', f'h.ins[{k}].xs[0] += mk(1)')
                add(f'nadd_{kn}_{e}', f'h.n += {k}')
        for vf, vn in ((V, 'v'), (VB, 'vb')):
            v = vf(e)
            add(f'lset_{vn}_{e}', f'h.xs[1] = {v}')
            add(f'mset_{vn}_{e}', f'h.m[1] = {v}')
            add(f'mset9_{vn}_{e}', f'h.m[9] = {v}')
            add(f'lpush_{vn}_{e}', f'h.xs.push({v})')
            add(f'lins_{vn}_{e}', f'h.xs.insert(1, {v})')
            add(f'gset_{vn}_{e}', f'h.g[1][1] = {v}')
            add(f'gpush_{vn}_{e}', f'h.g[1].push({v})')
            add(f'gasg_{vn}_{e}', f'h.g[1] = [{v}]')
            add(f'mgset_{vn}_{e}', f'h.mg[1][1] = {v}')
            add(f'mgpush_{vn}_{e}', f'h.mg[1].push({v})')
            add(f'mgasg_{vn}_{e}', f'h.mg[1] = [{v}]')
            add(f'innl_{vn}_{e}', f'h.inn.xs[1] = {v}')
            add(f'innm_{vn}_{e}', f'h.inn.m[1] = {v}')
            add(f'innp_{vn}_{e}', f'h.inn.xs.push({v})')
            add(f'insl_{vn}_{e}', f'h.ins[1].xs[1] = {v}')
            add(f'insm_{vn}_{e}', f'h.ins[1].m[1] = {v}')
            add(f'insp_{vn}_{e}', f'h.ins[1].xs.push({v})')
            add(f'inssx_{vn}_{e}', f'h.ins[1].set_x(1, {v})')
            add(f'innsx_{vn}_{e}', f'h.inn.set_x(1, {v})')
            add(f'put_{vn}_{e}', f'h.put_at(1, {v})')
            add(f'putg_{vn}_{e}', f'h.put_g(1, 1, {v})')
            add(f'setat_{vn}_{e}', f'h.xs.set_at(1, {v})')
            add(f'gsetat_{vn}_{e}', f'h.g[1].set_at(1, {v})')
            add(f'set2_{vn}_{e}', f'h.xs.set2(0, {v}, 1, {v})')
            add(f'mupd_{vn}_{e}', f'h.m.update(1, {v}, (v) => v)')
            add(f'mupd9_{vn}_{e}', f'h.m.update(9, {v}, (v) => v)')
            add(f'insasg_{vn}_{e}', f'h.ins[1] = In {{ xs: [{v}], m: [:] }}')
            add(f'innasg_{vn}_{e}', f'h.inn = In {{ xs: [{v}], m: [:] }}')
            add(f'innxasg_{vn}_{e}', f'h.inn.xs = [{v}]')
            add(f'xsasg_{vn}_{e}', f'h.xs = [{v}]')
            if ADD:
                add(f'ladd_{vn}_{e}', f'h.xs[1] += {v}')
                add(f'madd_{vn}_{e}', f'h.m[1] += {v}')
                add(f'gadd_{vn}_{e}', f'h.g[1][1] += {v}')
                add(f'mgadd_{vn}_{e}', f'h.mg[1][1] += {v}')
                add(f'insadd_{vn}_{e}', f'h.ins[1].xs[1] += {v}')
                add(f'inmadd_{vn}_{e}', f'h.ins[1].m[1] += {v}')
                add(f'lplain_{vn}_{e}', f'h.xs[1] = h.xs[1] + {v}')
                add(f'mplain_{vn}_{e}', f'h.m[1] = h.m[1] + {v}')
        l = L(e)
        add(f'lext_{e}', f'h.xs.extend({l})')
        add(f'gext_{e}', f'h.g[1].extend({l})')
        add(f'gasgl_{e}', f'h.g[1] = {l}')
        add(f'gpushl_{e}', f'h.g.push({l})')
        add(f'ginsl_{e}', f'h.g.insert(1, {l})')
        add(f'mgext_{e}', f'h.mg[1].extend({l})')
        add(f'mgasgl_{e}', f'h.mg[1] = {l}')
        add(f'mgasgl9_{e}', f'h.mg[9] = {l}')
        add(f'xsasgl_{e}', f'h.xs = {l}')
        add(f'insext_{e}', f'h.ins[1].xs.extend({l})')
        add(f'innext_{e}', f'h.inn.xs.extend({l})')
        s = Sx(e)
        add(f'sbapp_{e}', f'h.sb.append({s})')
        add(f'sbapp3_{e}', f'h.sb.append({s}, 0, 1)')
        for e2 in EFF:
            if e == 'plain' and e2 == 'plain': continue
            add(f'lset_kv_{e}_{e2}', f'h.xs[{K(e)}] = {V(e2)}')
            add(f'mset_kv_{e}_{e2}', f'h.m[{K(e)}] = {V(e2)}')
            add(f'gset_kkv_{e}_{e2}', f'h.g[{K(e)}][{K(e2)}] = {V(e2)}')
            add(f'gset_kk_{e}_{e2}', f'h.g[{K(e)}][{K(e2)}] = mk(1)')
            add(f'mgset_kk_{e}_{e2}', f'h.mg[{K(e)}][{K(e2)}] = mk(1)')
            add(f'insm_kk_{e}_{e2}', f'h.ins[{K(e)}].m[{K(e2)}] = mk(1)')
            add(f'lins_kv_{e}_{e2}', f'h.xs.insert({K(e)}, {V(e2)})')
            add(f'lswap_kk_{e}_{e2}', f'h.xs.swap({K(e)}, {K(e2)})')
            add(f'put_kv_{e}_{e2}', f'h.put_at({K(e)}, {V(e2)})')
            add(f'setat_kv_{e}_{e2}', f'h.xs.set_at({K(e)}, {V(e2)})')
            add(f'gsetat_kkv_{e}_{e2}', f'h.g[{K(e)}].set_at({K(e2)}, {V(e2)})')
            add(f'mupd_kv_{e}_{e2}', f'h.m.update({K(e)}, {V(e2)}, (v) => v)')
            if ADD:
                add(f'ladd_kv_{e}_{e2}', f'h.xs[{K(e)}] += {V(e2)}')
                add(f'madd_kv_{e}_{e2}', f'h.m[{K(e)}] += {V(e2)}')
                add(f'gadd_kkv_{e}_{e2}', f'h.g[{K(e)}][{K(e2)}] += {V(e2)}')


    return PRE, cases


def containers_cases(ELT: str, names: list[str] | None = None) -> tuple[str, list[str], list[tuple[str, str]]]:
    """The prelude, the case names and the driver cases of `containers`, of
    `names` only if given."""
    pre, cases = containers(ELT)
    if names is not None:
        cases = [c for c in cases if c[0] in set(names)]
    return pre, [n for n, _ in cases], [
        (f"fun c_{name}() {{\n    var h = fresh()\n    {stmt}\n    dump(\"{name}\", h)\n}}\n", f"c_{name}()")
        for name, stmt in cases]


def locals_(ELT: str, CTX: str) -> tuple[str, str, str, list[tuple[str, str]]]:
    """The prelude, the locals' declarations, the dump and the cases of
    gen_loc.py for the element `ELT`."""
    if ELT == 'int':
        T = 'int'; MK = 'return n'; SH = 'return f"{x}"'; ADD = True
    elif ELT == 'str':
        T = 'str'; MK = 'return f"s{n}"'; SH = 'return x'; ADD = True
    else:
        T = '[int]'; MK = 'return [n, n + 1]'; SH = 'return f"<{x[0]}.{x.len()}>"'; ADD = False
    PRE = f'''from std.io import println

    fun mk(n: int) -> {T} {{ {MK} }}
    fun sh(x: {T}) -> str {{ {SH} }}
    fun shl(xs: [{T}]) -> str {{
        var sb = StringBuilder()
        sb.append("[")
        for x in xs {{
            sb.append(sh(x))
            sb.append(" ")
        }}
        sb.append("]")
        return sb.build()
    }}
    fun shm(m: [int: {T}]) -> str {{
        var sb = StringBuilder()
        sb.append("{{")
        for k in m {{
            sb.append(f"{{k}}:")
            sb.append(sh(m[k]))
            sb.append(" ")
        }}
        sb.append("}}")
        return sb.build()
    }}
    fun shg(g: [[{T}]]) -> str {{
        var sb = StringBuilder()
        for r in g {{ sb.append(shl(r)) }}
        return sb.build()
    }}
    fun shmg(g: [int: [{T}]]) -> str {{
        var sb = StringBuilder()
        for k in g {{
            sb.append(f"{{k}}=")
            sb.append(shl(g[k]))
        }}
        return sb.build()
    }}
    async fun tick() -> int {{ return 0 }}

    impl [{T}] {{
        fun kgrow(var self) -> int {{
            for i in 0..40 {{ self.push(mk(100 + i)) }}
            return 1
        }}
        fun kshrink(var self) -> int {{
            self.truncate(2)
            return 1
        }}
        fun krepl(var self) -> int {{
            self = [mk(70), mk(71), mk(72)]
            return 1
        }}
        fun vgrow(var self) -> {T} {{
            for i in 0..40 {{ self.push(mk(100 + i)) }}
            return mk(3)
        }}
        fun vrepl(var self) -> {T} {{
            self = [mk(70), mk(71), mk(72)]
            return mk(5)
        }}
        fun lgrow(var self) -> [{T}] {{
            for i in 0..40 {{ self.push(mk(100 + i)) }}
            return [mk(3)]
        }}
        fun lrepl(var self) -> [{T}] {{
            self = [mk(70), mk(71), mk(72)]
            return [mk(5)]
        }}
        fun set_at(var self, i: int, v: {T}) {{ self[i] = v }}
        fun self_set(var self) {{ self[self.kgrow()] = mk(1) }}
        fun self_set_r(var self) {{ self[self.krepl()] = mk(1) }}
        fun self_push(var self) {{ self.push(self.vgrow()) }}
        fun self_push_r(var self) {{ self.push(self.vrepl()) }}
        fun self_setv(var self) {{ self[1] = self.vrepl() }}
        fun self_ins(var self) {{ self.insert(self.kgrow(), self.vrepl()) }}
        fun self_ext(var self) {{ self.extend(self.lgrow()) }}
        fun self_ext_r(var self) {{ self.extend(self.lrepl()) }}
        fun self_ext_self(var self) {{ self.extend(self) }}
    }}
    impl [[{T}]] {{
        fun ggrow(var self) -> int {{
            for i in 0..40 {{
                self.push([mk(300 + i)])
                self[1].push(mk(400 + i))
            }}
            return 1
        }}
        fun gshrink(var self) -> int {{
            self.truncate(2)
            self[1].truncate(2)
            return 1
        }}
        fun grepl(var self) -> int {{
            self = [[mk(75), mk(76)], [mk(77), mk(78)]]
            return 1
        }}
        fun gvgrow(var self) -> {T} {{
            for i in 0..40 {{
                self.push([mk(300 + i)])
                self[1].push(mk(400 + i))
            }}
            return mk(3)
        }}
        fun gvrepl(var self) -> {T} {{
            self = [[mk(75), mk(76)], [mk(77), mk(78)]]
            return mk(5)
        }}
        fun self_gset(var self) {{ self[self.ggrow()][self.grepl()] = self.gvgrow() }}
        fun self_gpush(var self) {{ self[self.grepl()].push(self.gvgrow()) }}
    }}
    impl [int: {T}] {{
        fun mgrow(var self) -> int {{
            for i in 0..40 {{ self[100 + i] = mk(200 + i) }}
            return 1
        }}
        fun mshrink(var self) -> int {{
            self.remove(0)
            self.remove(2)
            self.remove(3)
            return 1
        }}
        fun mrepl(var self) -> int {{
            self = [1: mk(73), 5: mk(74)]
            return 1
        }}
        fun mvgrow(var self) -> {T} {{
            for i in 0..40 {{ self[100 + i] = mk(200 + i) }}
            return mk(3)
        }}
        fun mvrepl(var self) -> {T} {{
            self = [1: mk(73), 5: mk(74)]
            return mk(5)
        }}
        fun self_mset(var self) {{ self[self.mgrow()] = self.mvrepl() }}
        fun self_mset2(var self) {{ self[self.mrepl()] = self.mvgrow() }}
        fun self_mrem(var self) {{ self.remove(self.mgrow()) }}
        fun self_mrem2(var self) {{ self.remove(self.mrepl()) }}
    }}
    '''
    INIT = '''    var xs = [mk(10), mk(11), mk(12), mk(13)]
        var sxs: [T] = []
        var m = [0: mk(20), 1: mk(21), 2: mk(22), 3: mk(23)]
        var sm: [int: T] = [:]
        var g = [[mk(30), mk(31), mk(32)], [mk(33), mk(34), mk(35)], [mk(36), mk(37), mk(38)]]
        var sg: [[T]] = []
        var mg = [0: [mk(40), mk(41), mk(42)], 1: [mk(43), mk(44), mk(45)], 2: [mk(46), mk(47), mk(48)]]
        var smg: [int: [T]] = [:]
        var n = 0
    '''.replace('[T]', f'[{T}]').replace(': T]', f': {T}]').replace('[[T]]', f'[[{T}]]')
    DUMP = '    println("NAME xs=" + shl(xs) + " sxs=" + shl(sxs) + " m=" + shm(m) + " sm=" + shm(sm) + " g=" + shg(g) + " sg=" + shg(sg) + " mg=" + shmg(mg) + " smg=" + shmg(smg) + f" n={n}")\n'

    # blocks
    SNAP = 'sxs = xs; sm = m; sg = g; smg = mg'
    GROW = 'for i in 0..40 { xs.push(mk(100 + i)); m[100 + i] = mk(200 + i); g.push([mk(300 + i)]); g[1].push(mk(400 + i)); mg[100 + i] = [mk(500 + i)]; mg[1].push(mk(600 + i)) }'
    SHRINK = 'xs.truncate(2); m.remove(0); m.remove(2); m.remove(3); g.truncate(2); g[1].truncate(2); mg.remove(0); mg.remove(2); mg[1].truncate(2)'
    REPL = 'xs = [mk(70), mk(71), mk(72)]; m = [1: mk(73), 5: mk(74)]; g = [[mk(75), mk(76)], [mk(77), mk(78)]]; mg = [1: [mk(79), mk(80)], 7: [mk(81)]]'
    B = {'snap': SNAP, 'grow': GROW, 'shrink': SHRINK, 'repl': REPL, 'snapgrow': SNAP + '; ' + GROW}
    def kb(e): return 'if n >= 0 { %s; 1 } else { 0 }' % B[e]
    def vb(e): return 'if n >= 0 { %s; mk(8) } else { mk(9) }' % B[e]
    def km(e): return 'match n >= 0 { true => { %s; 1 }, false => 0 }' % B[e]
    def lb(e): return 'if n >= 0 { %s; [mk(8)] } else { [mk(9)] }' % B[e]
    cases = []
    def add(n, s): cases.append((n, s))
    for e in B:
        for kf, kn in ((kb, 'kb'), (km, 'km')):
            k = kf(e)
            add(f'lset_{kn}_{e}', f'xs[{k}] = mk(1)')
            add(f'mset_{kn}_{e}', f'm[{k}] = mk(1)')
            add(f'mrem_{kn}_{e}', f'm.remove({k})')
            add(f'lins_{kn}_{e}', f'xs.insert({k}, mk(1))')
            add(f'lswap_{kn}_{e}', f'xs.swap(0, {k})')
            add(f'lrem_{kn}_{e}', f'let r = xs.remove_at({k})')
            add(f'gset_{kn}_{e}', f'g[{k}][0] = mk(1)')
            add(f'gset2_{kn}_{e}', f'g[0][{k}] = mk(1)')
            add(f'gset3_{kn}_{e}', f'g[{k}][{k}] = mk(1)')
            add(f'gpush_{kn}_{e}', f'g[{k}].push(mk(1))')
            add(f'mgset_{kn}_{e}', f'mg[{k}][0] = mk(1)')
            add(f'mgset2_{kn}_{e}', f'mg[1][{k}] = mk(1)')
            add(f'mgpush_{kn}_{e}', f'mg[{k}].push(mk(1))')
            add(f'mgrem_{kn}_{e}', f'mg.remove({k})')
            add(f'setat_{kn}_{e}', f'xs.set_at({k}, mk(1))')
            add(f'gsetat_{kn}_{e}', f'g[{k}].set_at(0, mk(1))')
            add(f'gsetat2_{kn}_{e}', f'g[1].set_at({k}, mk(1))')
            if ADD:
                add(f'ladd_{kn}_{e}', f'xs[{k}] += mk(1)')
                add(f'madd_{kn}_{e}', f'm[{k}] += mk(1)')
                add(f'gadd_{kn}_{e}', f'g[{k}][{k}] += mk(1)')
                add(f'mgadd_{kn}_{e}', f'mg[{k}][0] += mk(1)')
        v = vb(e)
        add(f'lset_vb_{e}', f'xs[1] = {v}')
        add(f'mset_vb_{e}', f'm[1] = {v}')
        add(f'mset9_vb_{e}', f'm[9] = {v}')
        add(f'lpush_vb_{e}', f'xs.push({v})')
        add(f'lins_vb_{e}', f'xs.insert(1, {v})')
        add(f'gset_vb_{e}', f'g[1][1] = {v}')
        add(f'gpush_vb_{e}', f'g[1].push({v})')
        add(f'gasg_vb_{e}', f'g[1] = [{v}]')
        add(f'mgset_vb_{e}', f'mg[1][1] = {v}')
        add(f'mgpush_vb_{e}', f'mg[1].push({v})')
        add(f'mgasg_vb_{e}', f'mg[1] = [{v}]')
        add(f'setat_vb_{e}', f'xs.set_at(1, {v})')
        add(f'gsetat_vb_{e}', f'g[1].set_at(1, {v})')
        add(f'xsasg_vb_{e}', f'xs = [{v}]')
        add(f'lext_lb_{e}', f'xs.extend({lb(e)})')
        add(f'gext_lb_{e}', f'g[1].extend({lb(e)})')
        add(f'gpush_lb_{e}', f'g.push({lb(e)})')
        add(f'mgasg_lb_{e}', f'mg[1] = {lb(e)}')
        for e2 in B:
            add(f'lset_kv_{e}_{e2}', f'xs[{kb(e)}] = {vb(e2)}')
            add(f'mset_kv_{e}_{e2}', f'm[{kb(e)}] = {vb(e2)}')
            add(f'gset_kk_{e}_{e2}', f'g[{kb(e)}][{kb(e2)}] = mk(1)')
            add(f'mgset_kk_{e}_{e2}', f'mg[{kb(e)}][{kb(e2)}] = mk(1)')
    # builtin-type var self methods on the local itself
    for kk in ('kgrow', 'kshrink', 'krepl'):
        add(f'lset_m_{kk}', f'xs[xs.{kk}()] = mk(1)')
        add(f'lins_m_{kk}', f'xs.insert(xs.{kk}(), mk(1))')
        add(f'lswap_m_{kk}', f'xs.swap(xs.{kk}(), 0)')
        add(f'lswap2_m_{kk}', f'xs.swap(0, xs.{kk}())')
        add(f'ltrunc_m_{kk}', f'xs.truncate(xs.{kk}() + 1)')
        add(f'lrem_m_{kk}', f'let r = xs.remove_at(xs.{kk}())')
        add(f'setat_m_{kk}', f'xs.set_at(xs.{kk}(), mk(1))')
        add(f'lset_mm_{kk}', f'xs[xs.{kk}()] = xs.vgrow()')
        add(f'lset_mr_{kk}', f'xs[xs.{kk}()] = xs.vrepl()')
        add(f'setat_mm_{kk}', f'xs.set_at(xs.{kk}(), xs.vgrow())')
        add(f'setat_mr_{kk}', f'xs.set_at(xs.{kk}(), xs.vrepl())')
        if ADD: add(f'ladd_m_{kk}', f'xs[xs.{kk}()] += mk(1)')
    for kk in ('ggrow', 'gshrink', 'grepl'):
        add(f'gset_m_{kk}', f'g[g.{kk}()][0] = mk(1)')
        add(f'gset2_m_{kk}', f'g[0][g.{kk}()] = mk(1)')
        add(f'gset3_m_{kk}', f'g[g.{kk}()][g.{kk}()] = mk(1)')
        add(f'gpush_m_{kk}', f'g[g.{kk}()].push(mk(1))')
        add(f'gsetat_m_{kk}', f'g[g.{kk}()].set_at(0, mk(1))')
        add(f'gsetat2_m_{kk}', f'g[1].set_at(g.{kk}(), mk(1))')
        add(f'gsetat3_m_{kk}', f'g[g.{kk}()].set_at(g.{kk}(), g.gvgrow())')
        add(f'gset_mv_{kk}', f'g[g.{kk}()][0] = g.gvrepl()')
        add(f'gset_mvg_{kk}', f'g[g.{kk}()][0] = g.gvgrow()')
        add(f'gpush_mv_{kk}', f'g[g.{kk}()].push(g.gvrepl())')
        add(f'gpush_mvg_{kk}', f'g[g.{kk}()].push(g.gvgrow())')
        add(f'gins_m_{kk}', f'g[1].insert(g.{kk}(), g.gvgrow())')
        add(f'gswap_m_{kk}', f'g[1].swap(0, g.{kk}())')
        add(f'gtrunc_m_{kk}', f'g[g.{kk}()].truncate(1)')
        add(f'gext_m_{kk}', f'g[g.{kk}()].extend(g[0])')
        if ADD: add(f'gadd_m_{kk}', f'g[g.{kk}()][0] += g.gvgrow()')
    for kk in ('mgrow', 'mshrink', 'mrepl'):
        add(f'mset_m_{kk}', f'm[m.{kk}()] = mk(1)')
        add(f'mrem_m_{kk}', f'm.remove(m.{kk}())')
        add(f'mset_mv_{kk}', f'm[m.{kk}()] = m.mvrepl()')
        add(f'mset_mvg_{kk}', f'm[m.{kk}()] = m.mvgrow()')
        add(f'mupd_m_{kk}', f'm.update(m.{kk}(), mk(1), (v) => v)')
        add(f'mupd_mv_{kk}', f'm.update(m.{kk}(), m.mvgrow(), (v) => v)')
        if ADD: add(f'madd_m_{kk}', f'm[m.{kk}()] += m.mvgrow()')
    add('lpush_mvgrow', 'xs.push(xs.vgrow())')
    add('lpush_mvrepl', 'xs.push(xs.vrepl())')
    add('lext_mgrow', 'xs.extend(xs.lgrow())')
    add('lext_mrepl', 'xs.extend(xs.lrepl())')
    add('lext_self', 'xs.extend(xs)')
    add('lpush_len', 'g.push(g[0])')
    add('gext_self', 'g[0].extend(g[0])')
    add('gpush_self', 'g[0].push(g[0][0])')
    add('lset_self', 'xs[0] = xs[xs.len() - 1]')
    add('lins_self', 'xs.insert(0, xs[xs.len() - 1])')
    add('mset_self', 'm[m.len()] = m[0]')
    add('mg_self', 'mg[5] = mg[1]')
    add('mg_self2', 'mg[1] = mg[0]')
    add('mg_self3', 'mg[1].extend(mg[1])')
    for s in ('self_set', 'self_set_r', 'self_push', 'self_push_r', 'self_setv', 'self_ins', 'self_ext', 'self_ext_r', 'self_ext_self'):
        add(s, f'xs.{s}()')
    for s in ('self_gset', 'self_gpush'):
        add(s, f'g.{s}()')
    for s in ('self_mset', 'self_mset2', 'self_mrem', 'self_mrem2'):
        add(s, f'm.{s}()')

    return PRE, INIT, DUMP, cases


def locals_cases(ELT: str, CTX: str, names: list[str] | None = None) -> tuple[str, list[str], list[tuple[str, str]]]:
    """The prelude, the case names and the driver cases of `locals_` in the
    context `CTX` (`fun`, `async`, `lambda`), of `names` only if given."""
    pre, init, dump, cases = locals_(ELT, CTX)
    if names is not None:
        cases = [c for c in cases if c[0] in set(names)]
    out = []
    for name, stmt in cases:
        d = dump.replace("NAME", name)
        if CTX == "fun":
            out.append((f"fun c_{name}() {{\n{init}    {stmt}\n{d}}}\n", f"c_{name}()"))
        elif CTX == "async":
            out.append((f"async fun c_{name}() {{\n{init}    n = await tick()\n    {stmt}\n    n = n + await tick()\n{d}}}\n",
                        f"await c_{name}()"))
        else:
            out.append((f"fun c_{name}() {{\n    let f = () => {{\n{init}    {stmt}\n{d}    }}\n    f()\n}}\n", f"c_{name}()"))
    return pre, [n for n, _ in cases], out
