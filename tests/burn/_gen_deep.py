"""The deep-copy generator of the review of 2026-11-12 (`repro-r5/native/gen.py`
of R5b, D92): every value shape through every hand-over between tasks and
actors, about 60 each: an actor's store, get, swap and list, forwarding
parameters, `async let` children, a child's result, a channel, `task.all`
of lambdas, `task.pool`, an async lambda. Each round checks each copy against
a checksum and counts the bad ones; `run_<shape>` prints the count and an
accumulated checksum. The shapes `clst` to `plst` (closures that capture the
recursive enums: in a variable, a struct, a list and a partial application)
were added for MYLA-415 (B1)."""
from __future__ import annotations

DECLS = '''
struct Inner { label: str, nums: [int] }
struct Rec { name: str, tags: [str], m: [str: int], inner: Inner, o: Option<str>, t: (int, str) }
enum Lst { Nil, Cons(str, Lst) }
enum Tree { Leaf, Node(Tree, [int], Tree) }
enum Ea { Stop, Go(str, Eb) }
enum Eb { Halt(int), Back(Ea, [int]) }
struct GBox<T> { v: T, more: [T] }
struct Pair<A, B> { a: A, b: B }
struct Hold { fs: [(int) -> int], name: str, g: () -> str }
struct WithL { l: Lst, t: Tree, n: int }
struct HoldL { f: () -> int64, n: int }

fun cs(s: str) -> int64 {
    var h: int64 = s.len() as int64
    for i in 0..s.len() { h = (h * 31 + (s[i] as int64)) % 1000003 }
    return h
}
fun cl(xs: [int]) -> int64 {
    var h: int64 = xs.len() as int64
    for x in xs { h = (h * 17 + (x as int64)) % 1000003 }
    return h
}
fun cls(xs: [str]) -> int64 {
    var h: int64 = xs.len() as int64
    for x in xs { h = (h * 13 + cs(x)) % 1000003 }
    return h
}
fun mklst(n: int) -> Lst {
    var l = Lst.Nil
    for i in 0..n { l = Lst.Cons(f"c{i}", l) }
    return l
}
fun chklst(l: Lst) -> int64 {
    var h: int64 = 7
    var cur = l
    while true {
        match cur {
            Cons(s, rest) => {
                h = (h * 11 + cs(s)) % 1000003
                cur = rest
            }
            Nil => { break }
        }
    }
    return h
}
fun addl(l: Lst, k: int) -> int64 { return (chklst(l) + (k as int64)) % 1000003 }
fun mktree(n: int) -> Tree {
    if n <= 0 { return Tree.Leaf }
    return Tree.Node(mktree(n / 2), [n, n + 1], mktree(n / 3))
}
fun chktree(t: Tree) -> int64 {
    return match t {
        Leaf => 3
        Node(l, xs, r) => (chktree(l) * 7 + cl(xs) * 5 + chktree(r)) % 1000003
    }
}
fun mkea(n: int) -> Ea {
    if n <= 0 { return Ea.Stop }
    return Ea.Go(f"g{n}", mkeb(n - 1))
}
fun mkeb(n: int) -> Eb {
    if n <= 0 { return Eb.Halt(n) }
    return Eb.Back(mkea(n - 1), [n, n])
}
fun chkea(a: Ea) -> int64 {
    return match a {
        Stop => 1
        Go(s, b) => (cs(s) + 3 * chkeb(b)) % 1000003
    }
}
fun chkeb(b: Eb) -> int64 {
    return match b {
        Halt(n) => 2 + (n as int64)
        Back(a, xs) => (chkea(a) * 5 + cl(xs)) % 1000003
    }
}
'''

# name: (T, mk body, chk body, mut body)  ; in mut the parameter is v0 and it must return the new value
SH = {}
def shape(name, T, mk, chk, mut):
    SH[name] = (T, mk, chk, mut)

shape('str', 'str', 'if n % 5 == 0 { return "" }\n    return f"v{n}:{n * 7}"', 'return cs(v)', 'return v0 + "!"')
shape('lint', '[int]', 'var xs: [int] = []\n    for i in 0..n % 6 { xs.push(n + i) }\n    return xs', 'return cl(v)', 'var v = v0\n    v.push(99)\n    v[0] = v[0] + 1\n    return v')
shape('lstr', '[str]', 'var xs: [str] = []\n    for i in 0..n % 5 { xs.push(f"e{n + i}") }\n    return xs', 'return cls(v)', 'var v = v0\n    v.push("more")\n    v[0] = v[0] + "+"\n    return v')
shape('mis', '[int: str]', 'var m: [int: str] = [:]\n    for i in 0..n % 5 { m[n + i] = f"m{i}" }\n    return m',
      'var h: int64 = v.len() as int64\n    for k in v { h = (h * 7 + (k as int64) + cs(v[k])) % 1000003 }\n    return h',
      'var v = v0\n    v[-1] = "neg"\n    for k in v0 { v[k] = v[k] + "~" }\n    return v')
shape('msl', '[str: [int]]', 'var m: [str: [int]] = [:]\n    for i in 0..n % 4 { m[f"k{n + i}"] = [i, n] }\n    return m',
      'var h: int64 = v.len() as int64\n    for k in v { h = (h * 7 + cs(k) + cl(v[k])) % 1000003 }\n    return h',
      'var v = v0\n    v["zz"] = [1]\n    for k in v0 { v[k].push(5) }\n    return v')
shape('lmap', '[[int: str]]', 'var xs: [[int: str]] = []\n    for i in 0..n % 4 { xs.push([i: f"a{n}", n: f"b{i}"]) }\n    return xs',
      'var h: int64 = v.len() as int64\n    for m in v { for k in m { h = (h * 7 + (k as int64) + cs(m[k])) % 1000003 } }\n    return h',
      'var v = v0\n    v.push([7: "seven"])\n    v[0][1000] = "k"\n    return v')
shape('tup', '(str, [int])', 'return (f"t{n}", [n, n + 1, n % 3])', 'return (cs(v.0) * 3 + cl(v.1)) % 1000003', 'var xs = v0.1\n    xs.push(4)\n    return (v0.0 + "'"'"'", xs)'.replace("'\"'\"'", "*"))
shape('opt', 'Option<[str]>', 'if n % 4 == 0 { return None }\n    return Some([f"o{n}", "p"])',
      'return match v {\n        Some(xs) => cls(xs)\n        None => 5\n    }',
      'return match v0 {\n        Some(xs) => Some(xs + ["q"])\n        None => Some(["was none"])\n    }'.replace('xs + ["q"]', 'xs.concat(["q"])'))
shape('res', 'Result<[int], str>', 'if n % 3 == 0 { return Err(f"bad{n}") }\n    return Ok([n, 2, 3])',
      'return match v {\n        Ok(xs) => cl(xs)\n        Err(e) => cs(e) + 1\n    }',
      'return match v0 {\n        Ok(xs) => Err(f"flip{xs.len()}")\n        Err(e) => Ok([e.len()])\n    }')
shape('rec', 'Rec', 'return Rec { name: f"r{n}", tags: [f"t{n}", "u"], m: [f"k{n}": n, "z": 1], inner: Inner { label: f"in{n}", nums: [n, n] }, o: if n % 2 == 0 { Some(f"o{n}") } else { None }, t: (n, f"tt{n}") }',
      'var h = (cs(v.name) + cls(v.tags) * 3 + cs(v.inner.label) * 5 + cl(v.inner.nums) * 7 + (v.t.0 as int64) + cs(v.t.1)) % 1000003\n    for k in v.m { h = (h * 3 + cs(k) + (v.m[k] as int64)) % 1000003 }\n    match v.o {\n        Some(s) => { h = (h + cs(s)) % 1000003 }\n        None => { h = h + 9 }\n    }\n    return h',
      'var v = v0\n    v.name = v.name + "#"\n    v.tags.push("new")\n    v.m["added"] = 5\n    v.inner.nums.push(8)\n    v.inner.label = "L"\n    v.o = Some("set")\n    return v')
shape('lst', 'Lst', 'return mklst(n % 6)', 'return chklst(v)', 'return Lst.Cons("head", v0)')
shape('tree', 'Tree', 'return mktree(n % 9)', 'return chktree(v)', 'return Tree.Node(v0, [1], v0)')
shape('mutual', 'Ea', 'return mkea(n % 7)', 'return chkea(v)', 'return Ea.Go("top", Eb.Back(v0, [9]))')
shape('gbox', 'GBox<str>', 'return GBox { v: f"g{n}", more: [f"h{n}", "i"] }', 'return (cs(v.v) + cls(v.more) * 3) % 1000003', 'var v = v0\n    v.more.push(v.v)\n    v.v = v.v + "^"\n    return v')
shape('pair', 'Pair<[int], Lst>', 'return Pair { a: [n, n + 2], b: mklst(n % 4) }', 'return (cl(v.a) + chklst(v.b) * 3) % 1000003', 'var v = v0\n    v.a.push(1)\n    v.b = Lst.Cons("x", v.b)\n    return v')
shape('clos', '() -> int64', 'let xs = [n, n + 1, n + 2]\n    let s = f"cap{n}"\n    let m = [s: xs]\n    return () => cl(xs) + cs(s) + cl(m[s])', 'return v()', 'let g = v0\n    let extra = [1, 2, 3]\n    return () => g() + cl(extra)')
shape('sb', 'StringBuilder', 'var sb = StringBuilder()\n    sb.append(f"sb{n}")\n    for i in 0..n % 4 { sb.append("chunk") }\n    return sb', 'var c = v\n    return cs(c.build())', 'var v = v0\n    v.append("++")\n    return v')
shape('hold', 'Hold', 'let k = [n, 1]\n    let nm = f"h{n}"\n    return Hold { fs: [(x: int) => x + k[0], (x: int) => x * k.len()], name: nm, g: () => nm + "!" }',
      'var h = cs(v.name) + cs(v.g())\n    for f in v.fs { h = (h * 3 + (f(2) as int64)) % 1000003 }\n    return h',
      'var v = v0\n    let old = v0.name\n    v.fs.push((x: int) => x + old.len())\n    v.name = v.name + "h"\n    return v')
shape('withl', 'WithL', 'return WithL { l: mklst(n % 5), t: mktree(n % 6), n: n }', 'return (chklst(v.l) + chktree(v.t) * 3 + (v.n as int64)) % 1000003', 'var v = v0\n    v.l = Lst.Cons("w", v.l)\n    v.n += 1\n    return v')
shape('llst', '[Lst]', 'var xs: [Lst] = []\n    for i in 0..n % 4 { xs.push(mklst(i + n % 3)) }\n    return xs', 'var h: int64 = v.len() as int64\n    for l in v { h = (h * 5 + chklst(l)) % 1000003 }\n    return h', 'var v = v0\n    v.push(Lst.Nil)\n    v[0] = Lst.Cons("z", v[0])\n    return v')
shape('olst', 'Option<Tree>', 'if n % 3 == 0 { return None }\n    return Some(mktree(n % 7))', 'return match v {\n        Some(t) => chktree(t)\n        None => 4\n    }', 'return match v0 {\n        Some(t) => Some(Tree.Node(t, [], Tree.Leaf))\n        None => Some(Tree.Leaf)\n    }')
shape('mlst', '[str: Lst]', 'var m: [str: Lst] = [:]\n    for i in 0..n % 4 { m[f"k{i}"] = mklst(i + 1) }\n    return m', 'var h: int64 = v.len() as int64\n    for k in v { h = (h * 5 + cs(k) + chklst(v[k])) % 1000003 }\n    return h', 'var v = v0\n    v["new"] = mklst(2)\n    return v')
shape('tt', '((str, int), [(str, [int])])', 'return ((f"a{n}", n), [(f"b{n}", [n]), ("c", [])])', 'var h = cs((v.0).0) + ((v.0).1 as int64)\n    for p in v.1 { h = (h * 3 + cs(p.0) + cl(p.1)) % 1000003 }\n    return h', 'var xs = v0.1\n    xs.push(("d", [1, 2]))\n    return (((v0.0).0 + "t", (v0.0).1 + 1), xs)')
shape('unit_l', '[()]', 'var xs: [()] = []\n    for i in 0..n % 4 { xs.push(()) }\n    return xs', 'return v.len() as int64', 'var v = v0\n    v.push(())\n    return v')
PACK = {'u8': ('uint8', '(x % 250) as uint8'), 'i8': ('int8', '((x % 200) - 100) as int8'), 'i16': ('int16', '((x % 60000) - 30000) as int16'), 'u16': ('uint16', '(x % 65000) as uint16'),
        'u32': ('uint32', '(x as uint32).wrapping_mul(1000003u32)'), 'i64': ('int64', '(x as int64) * 4000000007'), 'u64': ('uint64', '(x as uint64).wrapping_mul(18000000000000000001u64)'),
        'bool': ('bool', 'x % 3 == 0'), 'char': ('char', "'a' + (x % 1000)"), 'f32': ('float32', '(x as float32) / 3.0f32'), 'f64': ('float', '(x as float) / 7.0')}
for k, (t, conv) in PACK.items():
    if t == 'bool': tochk = 'if e { 1 } else { 2 }'; mutv = 'true'
    elif t == 'char': tochk = '(e - \'a\') as int64'; mutv = "'q'"
    elif t in ('float32', 'float'): tochk = '(e * 1000.0) as int64'.replace('1000.0', '1000.0f32' if t == 'float32' else '1000.0'); mutv = '2.5f32' if t == 'float32' else '2.5'
    elif t == 'uint64': tochk = '(e % 1000003u64) as int64'; mutv = '7'
    elif t == 'int64': tochk = 'e % 1000003'; mutv = '7'
    else: tochk = 'e as int64'; mutv = '7'
    shape('p' + k, f'[{t}]', f'var xs: [{t}] = []\n    for i in 0..n % 9 {{\n        let x = n * 3 + i\n        xs.push({conv})\n    }}\n    return xs',
          f'var h: int64 = v.len() as int64\n    for e in v {{ h = (h * 29 + {tochk}) % 1000003 }}\n    return h',
          f'var v = v0\n    v.push({mutv})\n    v[0] = {mutv}\n    return v')

# closures that capture the recursive enums (MYLA-415, B1): in a variable,
# a struct, a list, a partial application
shape('clst', '() -> int64', 'let l = mklst(n % 6)\n    return () => chklst(l)', 'return v()',
      'let g = v0\n    let extra = mklst(2)\n    return () => (g() + chklst(extra)) % 1000003')
shape('ctree', '() -> int64', 'let t = mktree(n % 9)\n    return () => chktree(t)', 'return v()',
      'let g = v0\n    return () => (g() * 3 + 1) % 1000003')
shape('cmutual', '() -> int64', 'let a = mkea(n % 7)\n    return () => chkea(a)', 'return v()',
      'let g = v0\n    let b = mkea(3)\n    return () => (g() + chkea(b)) % 1000003')
shape('hlst', 'HoldL', 'let l = mklst(n % 5)\n    return HoldL { f: () => chklst(l), n: n }', 'return (v.f() + (v.n as int64)) % 1000003',
      'var v = v0\n    v.n += 1\n    return v')
shape('flst', '[() -> int64]', 'let l = mklst(n % 4)\n    let t = mktree(n % 5)\n    return [() => chklst(l), () => chktree(t)]',
      'var h: int64 = v.len() as int64\n    for f in v { h = (h * 7 + f()) % 1000003 }\n    return h',
      'var v = v0\n    let l = mklst(1)\n    v.push(() => chklst(l))\n    return v')
shape('plst', '(int) -> int64', 'let l = mklst(n % 6)\n    return addl(l, _)', 'return v(3)',
      'let g = v0\n    return (k: int) => (g(k) + 1) % 1000003')

TAIL = '''    // task.all with lambdas capturing the value
    let cap = mk_{nm}(i)
    let fs: [async () -> int64] = [async () => chk_{nm}(cap), async () => chk_{nm}(mut_{nm}(cap)), async () => chk_{nm}(cap)]
    let rs = await task.all(fs)
    if rs[0] != e || rs[1] != em || rs[2] != e {{ bad += 1 }}
    // a pool's jobs and results
    let outs = await task.pool(2, [mk_{nm}(i), cap, cap, mut_{nm}(cap)], async (j: {T}) => mut_{nm}(j))
    if chk_{nm}(outs[0]) != em || chk_{nm}(outs[1]) != em || chk_{nm}(outs[2]) != em {{ bad += 1 }}
    if chk_{nm}(outs[3]) != chk_{nm}(mut_{nm}(mut_{nm}(cap))) {{ bad += 1 }}
    if chk_{nm}(cap) != e {{ bad += 1 }}
    // an async lambda called as a child
    let lam = async (k: {T}) => (chk_{nm}(k) + chk_{nm}(cap)) % 1000003
    async let lr = lam(mut_{nm}(cap))
    if await lr != (em + e) % 1000003 {{ bad += 1 }}
'''
def per_shape(nm):
    T, mk, chk, mut = SH[nm]
    tail = TAIL.replace('{nm}', nm).replace('{T}', T).replace('{{', '{').replace('}}', '}') if nm not in ('lst', 'tree', 'mutual') else ''
    return f'''
// ---- {nm}: {T}
fun mk_{nm}(n: int) -> {T} {{
    {mk}
}}
fun chk_{nm}(v: {T}) -> int64 {{
    {chk}
}}
fun mut_{nm}(v0: {T}) -> {T} {{
    {mut}
}}

actor A_{nm} {{ held: {T}, all: [{T}], n: int }}

impl A_{nm} {{
    fun put(var self, v: {T}) {{
        self.held = v
        self.n += 1
    }}
    fun keep(var self, v: {T}) {{ self.all.push(v) }}
    fun peek(self, v: {T}) -> int64 {{ return chk_{nm}(v) }}
    fun both(var self, a: {T}, b: {T}) -> int64 {{
        self.held = a
        return chk_{nm}(b)
    }}
    fun swap_in(var self, v: {T}) -> {T} {{
        let old = self.held
        self.held = v
        return old
    }}
    fun get(self) -> {T} {{ return self.held }}
    fun sum(self) -> int64 {{ return chk_{nm}(self.held) }}
    fun sum_all(self) -> int64 {{
        var h: int64 = 0
        for v in self.all {{ h = (h + chk_{nm}(v)) % 1000003 }}
        return h
    }}
    fun bump(var self) {{ self.held = mut_{nm}(self.held) }}
    fun bump_all(var self) {{
        for i in 0..self.all.len() {{ self.all[i] = mut_{nm}(self.all[i]) }}
    }}
    fun clear(var self) {{ self.all = [] }}
    async fun put_slow(var self, v: {T}) -> int64 {{
        await task.yield()
        self.held = v
        await task.yield()
        return chk_{nm}(self.held)
    }}
}}

// forwarding functions: parameters only ever given temporaries / variables / both
async fun viat_{nm}(a: A_{nm}, v: {T}) -> int64 {{
    await a.put(v)
    return chk_{nm}(v)
}}
async fun viav_{nm}(a: A_{nm}, v: {T}) -> int64 {{
    await a.put(v)
    return chk_{nm}(v)
}}
async fun viam_{nm}(a: A_{nm}, v: {T}) -> int64 {{
    await a.put(v)
    return chk_{nm}(v)
}}
async fun viak_{nm}(a: A_{nm}, v: {T}, w: {T}) -> int64 {{
    await a.keep(v)
    await a.keep(w)
    await a.keep(v)
    return chk_{nm}(v) + chk_{nm}(w)
}}
fun plain_t_{nm}(v: {T}) -> {T} {{ return v }}
fun plain_v_{nm}(v: {T}) -> {T} {{ return v }}

async fun child_{nm}(v: {T}) -> int64 {{
    var w = v
    w = mut_{nm}(w)
    await task.yield()
    return (chk_{nm}(v) * 3 + chk_{nm}(w)) % 1000003
}}
async fun make_{nm}(i: int) -> {T} {{
    let v = mk_{nm}(i)
    await task.yield()
    return v
}}
async fun echo_{nm}(v: {T}) -> {T} {{ return v }}
async fun echo2_{nm}(v: {T}) -> {T} {{
    await task.yield()
    return mut_{nm}(v)
}}
async fun recv_{nm}(ch: task.Channel<{T}>, n: int) -> int64 {{
    var s: int64 = 0
    for i in 0..n {{
        match await ch.recv() {{
            Some(v) => {{
                var w = v
                w = mut_{nm}(w)
                s = (s + chk_{nm}(v) + chk_{nm}(w)) % 1000003
            }}
            None => {{ s = s + 777 }}
        }}
    }}
    return s
}}

async fun round_{nm}(a: A_{nm}, i: int) -> int {{
    let e = chk_{nm}(mk_{nm}(i))
    let em = chk_{nm}(mut_{nm}(mk_{nm}(i)))
    var bad = 0
    // actor stores a temporary
    await a.put(mk_{nm}(i))
    if await a.sum() != e {{ bad += 1 }}
    // a variable, changed after on this side
    var v = mk_{nm}(i)
    await a.put(v)
    v = mut_{nm}(v)
    if await a.sum() != e {{ bad += 1 }}
    if chk_{nm}(v) != em {{ bad += 1 }}
    // changed on the actor's side
    var u = mk_{nm}(i)
    await a.put(u)
    await a.bump()
    if chk_{nm}(u) != e {{ bad += 1 }}
    if await a.sum() != em {{ bad += 1 }}
    // back from the actor, then the actor changes its own
    let g = await a.get()
    await a.bump()
    if chk_{nm}(g) != em {{ bad += 1 }}
    // the same value twice, used after
    if await a.both(u, u) != e {{ bad += 1 }}
    if await a.peek(u) != e {{ bad += 1 }}
    let old = await a.swap_in(u)
    if chk_{nm}(old) != e {{ bad += 1 }}
    u = mut_{nm}(u)
    if await a.sum() != e {{ bad += 1 }}
    if await a.put_slow(mut_{nm}(mk_{nm}(i))) != em {{ bad += 1 }}
    // a list in the actor
    await a.clear()
    await a.keep(mk_{nm}(i))
    await a.keep(v)
    await a.keep(v)
    await a.bump_all()
    if await a.sum_all() != (em + chk_{nm}(mut_{nm}(v)) * 2) % 1000003 {{ bad += 1 }}
    if chk_{nm}(v) != em {{ bad += 1 }}
    // through parameters: temporaries only, variables only, both
    if await viat_{nm}(a, mk_{nm}(i)) != e {{ bad += 1 }}
    if await viat_{nm}(a, mut_{nm}(mk_{nm}(i))) != em {{ bad += 1 }}
    if await a.sum() != em {{ bad += 1 }}
    var pv = mk_{nm}(i)
    if await viav_{nm}(a, pv) != e {{ bad += 1 }}
    pv = mut_{nm}(pv)
    if await a.sum() != e {{ bad += 1 }}
    if await viav_{nm}(a, pv) != em {{ bad += 1 }}
    if await viam_{nm}(a, mk_{nm}(i)) != e {{ bad += 1 }}
    if await viam_{nm}(a, pv) != em {{ bad += 1 }}
    if await a.sum() != em {{ bad += 1 }}
    await a.clear()
    if await viak_{nm}(a, pv, plain_t_{nm}(mk_{nm}(i))) != (e + em) % 2000006 {{ bad += 1 }}
    let pw = plain_v_{nm}(pv)
    pv = mut_{nm}(pv)
    if await a.sum_all() != (em * 2 + e) % 1000003 {{ bad += 1 }}
    if chk_{nm}(pw) != em {{ bad += 1 }}
    await a.clear()
    // async let children: the same value twice, changed here meanwhile
    var c0 = mk_{nm}(i)
    async let x = child_{nm}(c0)
    async let y = child_{nm}(c0)
    async let z0 = child_{nm}(mk_{nm}(i))
    c0 = mut_{nm}(c0)
    let want = (e * 3 + em) % 1000003
    if await x != want {{ bad += 1 }}
    if await y != want {{ bad += 1 }}
    if await z0 != want {{ bad += 1 }}
    if chk_{nm}(c0) != em {{ bad += 1 }}
    // a child's result
    let m1 = await make_{nm}(i)
    var m2 = m1
    m2 = mut_{nm}(m2)
    if chk_{nm}(m1) != e {{ bad += 1 }}
    if chk_{nm}(m2) != em {{ bad += 1 }}
    async let z = make_{nm}(i)
    async let zz = echo_{nm}(m1)
    async let z2 = echo2_{nm}(m1)
    let zv = await z
    let zzv = await zz
    let z2v = await z2
    if chk_{nm}(zv) != e {{ bad += 1 }}
    if chk_{nm}(zzv) != e {{ bad += 1 }}
    if chk_{nm}(z2v) != em {{ bad += 1 }}
    if chk_{nm}(m1) != e {{ bad += 1 }}
    // a channel
    let ch: task.Channel<{T}> = task.channel(2)
    async let r = recv_{nm}(ch, 4)
    var s = mk_{nm}(i)
    let s1 = await ch.send(s)
    s = mut_{nm}(s)
    let s2 = await ch.send(s)
    let s3 = await ch.send(mk_{nm}(i))
    let s4 = await ch.send(s)
    if await r != ((e + em) * 2 + (em + chk_{nm}(mut_{nm}(s))) * 2) % 1000003 {{ bad += 1 }}
    if chk_{nm}(s) != em {{ bad += 1 }}
    await ch.close()
{tail}    return bad
}}

async fun run_{nm}(rounds: int) -> int {{
    let a = A_{nm} {{ held: mk_{nm}(1), all: [], n: 0 }}
    var bad = 0
    var acc: int64 = 0
    for i in 0..rounds {{
        bad += await round_{nm}(a, i)
        acc = (acc * 3 + await a.sum()) % 1000003
    }}
    println(f"{nm} bad={{bad}} acc={{acc}}")
    return bad
}}
'''


def cases(names: list[str], rounds: int) -> list[tuple[str, str]]:
    """The driver cases of the shapes `names`, `rounds` rounds each."""
    return [(per_shape(n), f"let bad_{n} = await run_{n}({rounds})") for n in names]


PRELUDE = "\n".join(["from std.io import println", "import std.task as task", DECLS])
