"""Burn tests: hand-written programs exercising codegen corners, each asserting
the native binary's output matches the interpreter (and exit codes for traps)."""
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON, build_and_run, interpret

PROGRAMS = {
    "unsigned_wrap": (
        "#main\nfun main() {\n"
        "    var b: uint8 = 255u8\n    b = b + 1u8\n    print(b)\n"
        "    print(18446744073709551615u64 + 1u64)\n}\n"
    ),
    "signed_wrap_and_div": (
        "#main\nfun main() {\n"
        "    var x: int8 = 127i8\n    x = x + 1i8\n    print(x)\n"
        "    print(-7 / 2)\n    print(-7 % 2)\n    print(7 / -2)\n}\n"
    ),
    "recursion": (
        "fun fib(n: int) -> int {\n"
        "    if n < 2 {\n        return n\n    }\n"
        "    return fib(n - 1) + fib(n - 2)\n}\n"
        "#main\nfun main() {\n    print(fib(10))\n}\n"
    ),
    "nested_struct_return": (
        "struct P { x: int, y: int }\nstruct L { a: P, b: P }\n"
        "fun mk(v: int) -> P {\n    return P { x: v, y: v * 2 }\n}\n"
        "#main\nfun main() {\n"
        "    let l = L { a: mk(1), b: mk(3) }\n"
        "    print(l.a.x)\n    print(l.a.y)\n    print(l.b.y)\n}\n"
    ),
    "struct_value_semantics": (
        "struct P { x: int, y: int }\n"
        "#main\nfun main() {\n"
        "    var a = P { x: 1, y: 2 }\n    var b = a\n    b.x = 99\n"
        "    print(a.x)\n    print(b.x)\n}\n"
    ),
    "loops_and_logic": (
        "#main\nfun main() {\n"
        "    var total = 0\n    for i in 1..5 {\n        total = total + i\n    }\n"
        "    print(total)\n"
        "    let a = true\n    let b = false\n"
        "    print(a && !b)\n    print(a || b)\n    print(!(a && b))\n}\n"
    ),
    # --- v0.3.1 operators & literals ---
    "bitwise_and_complement": (
        "#main\nfun main() {\n"
        "    print(0b1100 & 0b1010)\n    print(0b1100 | 0b1010)\n"
        "    print(0b1100 ^ 0b1010)\n"
        "    let x: uint8 = 0xF0u8\n    print(~x)\n"
        "    print(0xFF & 0o17)\n"
        # bitwise binds tighter than ==, so this is (12 & 8) == 8 -> true
        "    print(0b1100 & 0b1000 == 0b1000)\n}\n"
    ),
    "shifts_signed_and_unsigned": (
        "#main\nfun main() {\n"
        "    print(1 << 10)\n    print(-32 >> 2)\n"
        "    let u: uint8 = 0xF0u8\n    print(u >> 4)\n    print(u << 4)\n"
        "    let s: int64 = -1i64\n    print(s >> 1)\n"
        # shift binds tighter than +, looser than nothing relevant here
        "    print(1 << 2 + 1)\n}\n"
    ),
    "numeric_casts": (
        "#main\nfun main() {\n"
        "    print(257 as uint8)\n    print(-1 as uint8)\n"
        "    let s: int16 = -1i16\n    print(s as int32)\n"
        "    print(s as uint16 as int32)\n"
        "    let u: uint8 = 200u8\n    print(u as int8)\n"
        "    print(-x_helper() as int8)\n}\n"
        "fun x_helper() -> int32 {\n    return 130\n}\n"
    ),
    "break_continue_flow": (
        "#main\nfun main() {\n"
        "    var total = 0\n    var i = 0\n"
        "    while i < 100 {\n        i = i + 1\n"
        "        if i % 2 == 1 {\n            continue\n        }\n"
        "        if i > 10 {\n            break\n        }\n"
        "        total = total + i\n    }\n    print(total)\n"
        "    var found = 0\n"
        "    for k in 0..50 {\n        if k * k > 40 {\n            found = k\n            break\n        }\n    }\n"
        "    print(found)\n}\n"
    ),
    # --- v0.4.1 methods & impl (self / var self, generics, builtins) ---
    "methods_self_and_var_self": (
        "struct Counter { n: int, log: [int] }\n"
        "impl Counter {\n"
        "    fun get(self) -> int { return self.n }\n"
        "    fun bump(var self) {\n"
        "        self.n = self.n + 1\n        push(self.log, self.n)\n    }\n"
        "    fun total(self) -> int {\n"
        "        var s = 0\n        for v in self.log { s = s + v }\n        return s\n    }\n"
        "    fun bump_n(var self, k: int) {\n"
        "        var i = 0\n        while i < k {\n            self.bump()\n            i = i + 1\n        }\n    }\n"
        "}\n"
        "#main\nfun main() {\n"
        "    var c = Counter { n: 0, log: [] }\n"
        "    c.bump_n(3)\n    c.bump()\n"
        "    print(c.get())\n    print(c.total())\n}\n"
    ),
    "methods_value_semantics": (
        "struct P { x: int }\n"
        "impl P {\n"
        "    fun x_of(self) -> int { return self.x }\n"
        "    fun with_x(self, v: int) -> P { return P { x: v } }\n"
        "}\n"
        "#main\nfun main() {\n"
        "    let a = P { x: 1 }\n    let b = a.with_x(99)\n"
        "    print(a.x_of())\n    print(b.x_of())\n}\n"
    ),
    "methods_generic_impl": (
        "struct Box<T> { value: T }\n"
        "impl<T> Box<T> {\n"
        "    fun get(self) -> T { return self.value }\n"
        "    fun set(var self, v: T) { self.value = v }\n"
        "}\n"
        "#main\nfun main() {\n"
        "    var b = Box { value: 7 }\n    b.set(42)\n    print(b.get())\n"
        "    let t = Box { value: true }\n    print(t.get())\n}\n"
    ),
    "methods_enum_and_nested_receiver": (
        "enum Shape { Circle(int), Rect(int, int) }\n"
        "impl Shape {\n"
        "    fun area(self) -> int {\n"
        "        return match self {\n"
        "            Circle(r) => 3 * r * r\n            Rect(w, h) => w * h\n        }\n    }\n}\n"
        "struct Outer { c: Counter }\n"
        "struct Counter { n: int }\n"
        "impl Counter { fun bump(var self) { self.n = self.n + 1 } fun get(self) -> int { return self.n } }\n"
        "impl Outer { fun tick(var self) { self.c.bump() } }\n"
        "#main\nfun main() {\n"
        "    print(Shape.Rect(3, 4).area())\n    print(Shape.Circle(2).area())\n"
        "    var o = Outer { c: Counter { n: 10 } }\n    o.tick()\n    o.tick()\n    print(o.c.get())\n}\n"
    ),
    "methods_on_builtins": (
        "impl int {\n"
        "    fun is_even(self) -> bool { return self % 2 == 0 }\n"
        "    fun double(self) -> int { return self * 2 }\n}\n"
        "#main\nfun main() {\n"
        "    let n = 5\n    print(n.is_even())\n    print(n.double())\n"
        "    print(n.double().is_even())\n    print((3).double())\n}\n"
    ),
    # --- v0.3.2 const + assert/panic/unreachable ---
    "const_folding": (
        "const KIB: int32 = 1 << 10\n"
        "const PAGE: int32 = 4 * KIB\n"
        "const MASK: int32 = PAGE - 1\n"
        'const HELLO: str = "hi"\n'
        "const FLAG: bool = (KIB > 0) && !false\n"
        "const BYTE: uint8 = 0xFFu8 & 0x0Fu8\n"
        "fun align(n: int32) -> int32 {\n    return n & ~MASK\n}\n"
        "#main\nfun main() {\n"
        "    print(KIB)\n    print(PAGE)\n    print(MASK)\n"
        "    print(align(5000))\n    print(HELLO)\n    print(FLAG)\n"
        "    print(BYTE)\n}\n"
    ),
    "assert_pass_and_match_unreachable": (
        "enum E { A, B }\n"
        "fun f(x: int32) -> int32 {\n"
        "    assert(x >= 0)\n    assert(x < 10, \"too big\")\n    return x * x\n}\n"
        "fun g(e: E) -> int32 {\n"
        "    return match e {\n        E.A => 1,\n        E.B => unreachable(),\n    }\n}\n"
        "#main\nfun main() {\n    print(f(3))\n    print(g(E.A))\n}\n"
    ),
    # --- v0.3.3 lists: literals, index, len, for-in, push/pop, CoW ---
    "list_basics_and_for_in": (
        "fun total(xs: [int]) -> int {\n"
        "    var t = 0\n    for x in xs {\n        t = t + x\n    }\n    return t\n}\n"
        "#main\nfun main() {\n"
        "    let xs = [10, 20, 30]\n"
        "    print(len(xs))\n    print(xs[0])\n    print(xs[2])\n    print(total(xs))\n"
        "    let empty: [int] = []\n    print(len(empty))\n}\n"
    ),
    "list_value_semantics_cow": (
        # mutating a copy (and a shared nested cell) must not affect the original.
        "#main\nfun main() {\n"
        "    var a = [1, 2, 3]\n    var b = a\n    b[0] = 99\n    push(b, 4)\n"
        "    print(a[0])\n    print(len(a))\n    print(b[0])\n    print(len(b))\n"
        "    var g = [[1, 2], [3, 4]]\n    var h = g\n    h[0][0] = 7\n"
        "    print(g[0][0])\n    print(h[0][0])\n}\n"
    ),
    "list_push_pop_build": (
        "fun make(n: int) -> [int] {\n"
        "    var out: [int] = []\n"
        "    for i in 0..n {\n        push(out, i * i)\n    }\n    return out\n}\n"
        "#main\nfun main() {\n"
        "    var xs = make(6)\n    print(len(xs))\n    print(xs[5])\n"
        "    print(pop(xs))\n    print(len(xs))\n}\n"
    ),
    "list_of_structs": (
        "struct P { x: int, y: int }\n"
        "fun ysum(ps: [P]) -> int {\n"
        "    var s = 0\n    for p in ps {\n        s = s + p.y\n    }\n    return s\n}\n"
        "#main\nfun main() {\n"
        "    var ps = [P { x: 1, y: 2 }, P { x: 3, y: 4 }]\n"
        "    print(ysum(ps))\n    ps[0] = P { x: 9, y: 9 }\n    print(ysum(ps))\n"
        "    print(ps[1].x)\n}\n"
    ),
    # --- v0.3.4 maps: literals, index, len, get/contains/remove/keys, for-in, CoW ---
    "map_basics_and_index": (
        "#main\nfun main() {\n"
        '    var m: [str: int] = ["a": 1, "b": 2, "c": 3]\n'
        '    print(len(m))\n    print(m["a"])\n    print(m["c"])\n'
        '    m["a"] = 10\n    m["d"] = 4\n'
        '    print(m["a"])\n    print(len(m))\n'
        "    let e: [int: int] = [:]\n    print(len(e))\n}\n"
    ),
    "map_value_semantics_cow": (
        # mutating a copy (write, remove, insert) must not affect the original.
        "#main\nfun main() {\n"
        "    var a = [1: 10, 2: 20]\n    var b = a\n"
        "    b[1] = 99\n    remove(b, 2)\n    b[3] = 30\n"
        "    print(a[1])\n    print(len(a))\n    print(b[1])\n    print(len(b))\n}\n"
    ),
    "map_get_contains": (
        "fun probe(m: [int: int], k: int) -> int {\n"
        "    var r = -1\n"
        "    match get(m, k) {\n        Some(v) => { r = v }\n        None => { r = -1 }\n    }\n"
        "    return r\n}\n"
        "#main\nfun main() {\n"
        "    let m = [1: 100, 2: 200]\n"
        "    print(probe(m, 1))\n    print(probe(m, 9))\n"
        "    print(contains(m, 2))\n    print(contains(m, 7))\n}\n"
    ),
    "map_build_keys_and_for": (
        # grow past the load factor, then sum keys and values (order-independent).
        "fun make(n: int) -> [int: int] {\n"
        "    var m: [int: int] = [:]\n"
        "    var i = 0\n    while i < n {\n        m[i] = i * i\n        i = i + 1\n    }\n"
        "    return m\n}\n"
        "#main\nfun main() {\n"
        "    let m = make(50)\n    print(len(m))\n"
        "    var ks = 0\n    for k in keys(m) {\n        ks = ks + k\n    }\n    print(ks)\n"
        "    var vs = 0\n    for k in m {\n        vs = vs + m[k]\n    }\n    print(vs)\n}\n"
    ),
    "map_remove_reinsert": (
        "#main\nfun main() {\n"
        "    var m = [1: 10, 2: 20, 3: 30]\n"
        "    remove(m, 2)\n    remove(m, 999)\n"
        "    print(len(m))\n    print(contains(m, 2))\n"
        "    m[2] = 42\n    print(m[2])\n    print(len(m))\n}\n"
    ),
    "map_of_lists_cow": (
        # heap-owning values retained/dropped correctly across copy and remove.
        "#main\nfun main() {\n"
        "    var m: [int: [int]] = [:]\n"
        "    m[1] = [2, 3]\n    push(m[1], 4)\n"
        "    var c = m\n    remove(c, 1)\n"
        "    print(m[1][0])\n    print(m[1][2])\n    print(len(c))\n}\n"
    ),
    "string_equality": (
        "#main\nfun main() {\n"
        '    print("abc" == "abc")\n    print("abc" == "abd")\n'
        '    print("abc" != "abd")\n}\n'
    ),
    # --- v0.3.5a strings: len, byte indexing, char literals ---
    "string_len_and_index": (
        "fun blen(s: str) -> int {\n    return len(s)\n}\n"
        "#main\nfun main() {\n"
        '    let s = "Myla"\n'
        "    print(len(s))\n    print(s[0] as int)\n    print(s[3] as int)\n"
        '    print(blen(""))\n    print(blen("hello"))\n}\n'
    ),
    # --- v0.3.5b strings: concat + format ---
    "string_concat": (
        "fun greet(name: str) -> str {\n"
        '    return "Hello, " + name + "!"\n}\n'
        "#main\nfun main() {\n"
        '    print(greet("Myla"))\n'
        '    print("a" + "b" + "c")\n'
        '    let s = "foo" + "bar"\n    print(len(s))\n    print(s[3] as int)\n}\n'
    ),
    "string_format": (
        "#main\nfun main() {\n"
        '    print(format("{} + {} = {}", 2, 3, 5))\n'
        '    print(format("{}", -7))\n'
        '    print(format("max u64 = {}", 18446744073709551615u64))\n'
        '    print(format("{{literal}} {} done", "x"))\n'
        '    print(format("no holes"))\n'
        '    print(format("{} and {}", true, false))\n'
        '    print("p" + format("[{}]", 9) + "q")\n}\n'
    ),
    # --- v0.3.5c strings: StringBuilder ---
    "string_builder": (
        "fun digits(n: int) -> str {\n"
        "    var sb = StringBuilder()\n"
        "    for i in 0..n {\n"
        "        append_byte(sb, ('0' as int + i) as uint8)\n    }\n"
        "    return build(sb)\n}\n"
        "#main\nfun main() {\n"
        "    var sb = StringBuilder()\n"
        '    append(sb, "Hello")\n    append_byte(sb, \',\')\n'
        '    append_byte(sb, \' \')\n    append(sb, "world")\n    append_byte(sb, \'!\')\n'
        "    print(len(sb))\n    print(build(sb))\n"
        "    print(digits(10))\n"
        # value semantics: a copy keeps building independently
        "    var a = StringBuilder()\n    append(a, \"seed\")\n"
        "    var b = a\n    append(b, \" more\")\n"
        "    print(build(a))\n    print(build(b))\n}\n"
    ),
    # MYLA-85: append(sb, s, start, end) appends a byte range
    "string_builder_append_range": (
        "fun field(line: str, n: int) -> str {\n"
        "    var start = 0\n    var k = 0\n    var i = 0\n"
        "    while i <= len(line) {\n"
        "        if i == len(line) || line[i] == ',' {\n"
        "            if k == n {\n"
        "                var sb = StringBuilder()\n"
        "                append(sb, line, start, i)\n"
        "                return build(sb)\n            }\n"
        "            k = k + 1\n            start = i + 1\n        }\n"
        "        i = i + 1\n    }\n"
        "    return \"\"\n}\n"
        "#main\nfun main() {\n"
        "    let line = \"alpha,,λ ö,omega\"\n"
        "    for n in 0..5 { print(format(\"[{}]\", field(line, n))) }\n"
        "    var sb = StringBuilder()\n"
        "    append(sb, line, 0, 0)\n"
        "    append(sb, line, len(line) - 5, len(line))\n"
        "    append(sb, \"aö\", 0, 2)\n"
        "    append(sb, \"aö\", 2, 3)\n"
        "    let s = build(sb)\n"
        "    print(s)\n    print(len(s))\n"
        "    var copy = sb\n    append(copy, line, 0, 5)\n"
        "    print(build(sb))\n    print(build(copy))\n}\n"
    ),
    # MYLA-84: a const string made with `+` read inside a function: the
    # self-hosted backend evaluated the concatenation at each use, into a
    # temporary its frame had no slot for, and the function's return crashed
    # MYLA-102: a local binding shadows a top-level function of the same name
    # in calls too (a closure, a parameter of function type); outside its
    # scope the function is called again
    "local_closure_shadows_a_function": (
        "fun fail(m: str) -> int32 {\n    print(\"the function\")\n    return 1\n}\n"
        "fun twice(n: int32) -> int32 {\n    return 2 * n\n}\n"
        "fun apply(twice: (int32) -> int32, x: int32) -> int32 {\n    return twice(x)\n}\n"
        "#main\nfun main() {\n"
        "    if true {\n"
        "        let fail = (m: str) => len(m)\n"
        "        print(fail(\"the closure\"))\n"
        "        let twice = (n: int32) => n + 100\n"
        "        print(twice(1))\n"
        "    }\n"
        "    print(fail(\"again\"))\n"
        "    print(twice(5))\n"
        "    print(apply((n: int32) => n - 1, 10))\n"
        "}\n"
    ),
    # MYLA-104: structs, tuples and enums without heap values (literals,
    # fields at any depth, var self, sret results, overloaded operators,
    # generic instances, match with guards, or-patterns and block arms) give
    # the same output through the IR as through the old path
    "plain_aggregates": (
        "#derive(Eq)\n"
        "struct Vec2 { x: int, y: int }\n"
        "\n"
        "impl Vec2 {\n"
        "    fun len2(self) -> int {\n"
        "        return self.x * self.x + self.y * self.y\n"
        "    }\n"
        "    fun scale(var self, k: int) {\n"
        "        self.x = self.x * k\n"
        "        self.y = self.y * k\n"
        "    }\n"
        "}\n"
        "\n"
        "impl Add for Vec2 {\n"
        "    fun add(self, other: Vec2) -> Vec2 {\n"
        "        return Vec2 { x: self.x + other.x, y: self.y + other.y }\n"
        "    }\n"
        "}\n"
        "\n"
        "enum Shape {\n"
        "    Dot,\n"
        "    Circle(Vec2, int),\n"
        "    Rect(Vec2, Vec2),\n"
        "}\n"
        "\n"
        "struct Wrap<T> { inner: T, tag: int }\n"
        "\n"
        "fun unwrap<T>(w: Wrap<T>) -> T {\n"
        "    return w.inner\n"
        "}\n"
        "\n"
        "fun area(s: Shape) -> int {\n"
        "    return match s {\n"
        "        Shape.Dot => 0,\n"
        "        Shape.Circle(c, r) if r > 10 => 1000,\n"
        "        Shape.Circle(c, r) => 3 * r * r,\n"
        "        Shape.Rect(a, b) => (b.x - a.x) * (b.y - a.y),\n"
        "    }\n"
        "}\n"
        "\n"
        "fun classify(p: (int, bool)) -> int {\n"
        "    match p {\n"
        "        (0, _) => { return 0 },\n"
        "        (1, true) | (2, true) => { return 12 },\n"
        "        (n, false) => { return -n },\n"
        "        _ => { return 99 },\n"
        "    }\n"
        "    return 100\n"
        "}\n"
        "\n"
        "fun mirror(v: Vec2) -> Vec2 {\n"
        "    var m = v\n"
        "    m.x = v.y\n"
        "    m.y = v.x\n"
        "    return m\n"
        "}\n"
        "\n"
        "struct Line { a: Vec2, b: Vec2 }\n"
        "\n"
        "#main\n"
        "fun main() {\n"
        "    var v = Vec2 { x: 3, y: 4 }\n"
        "    print(v.len2())\n"
        "    v.scale(2)\n"
        "    print(v.x)\n"
        "    print(v.y)\n"
        "    let w = v + Vec2 { x: 1, y: 1 }\n"
        "    print(w.x + w.y)\n"
        "    print(v == Vec2 { x: 6, y: 8 })\n"
        "    print(v != w)\n"
        "    print(area(Shape.Dot))\n"
        "    print(area(Shape.Circle(v, 2)))\n"
        "    print(area(Shape.Circle(v, 20)))\n"
        "    print(area(Shape.Rect(Vec2 { x: 1, y: 1 }, Vec2 { x: 4, y: 5 })))\n"
        "    print(classify((0, true)))\n"
        "    print(classify((2, true)))\n"
        "    print(classify((7, false)))\n"
        "    print(classify((5, true)))\n"
        "    let m = mirror(Vec2 { x: 1, y: 2 })\n"
        "    print(m.x * 10 + m.y)\n"
        "    var line = Line { a: Vec2 { x: 0, y: 0 }, b: m }\n"
        "    line.b.y = 9\n"
        "    line.a = line.b\n"
        "    print(line.a.y + line.b.x)\n"
        "    let t = (1, (2, 3))\n"
        "    print((t.1).0 + (t.1).1)\n"
        "    print(unwrap(Wrap { inner: 7, tag: 0 }))\n"
        "    print(unwrap(Wrap { inner: Vec2 { x: 2, y: 5 }, tag: 1 }).y)\n"
        "    let s = Shape.Circle(Vec2 { x: 0, y: 0 }, 1)\n"
        "    let r = match s {\n"
        "        Shape.Circle(c, k) => {\n"
        "            let doubled = k * 2\n"
        "            doubled + c.x\n"
        "        },\n"
        "        _ => -1,\n"
        "    }\n"
        "    print(r)\n"
        "}\n"
    ),
    # MYLA-105: strings and aggregates holding them through the IR: a const,
    # concatenation, equality, len, fields and payloads, a copy whose field is
    # reassigned, early returns from a loop, a match on a string whose arm
    # writes it, a break with owners in scope
    "strings_through_the_ir": (
        'const GREETING: str = "hello"\n'
        "\n"
        "struct Named { name: str, n: int }\n"
        "\n"
        "enum Token {\n"
        "    Word(str),\n"
        "    Num(int),\n"
        "    End,\n"
        "}\n"
        "\n"
        "fun describe(t: Token) -> str {\n"
        "    return match t {\n"
        '        Token.Word(w) => "word " + w,\n'
        '        Token.Num(n) => "num",\n'
        '        Token.End => "end",\n'
        "    }\n"
        "}\n"
        "\n"
        "fun rename(x: Named, to: str) -> Named {\n"
        "    var y = x\n"
        '    y.name = to + "!"\n'
        "    return y\n"
        "}\n"
        "\n"
        "fun first_long(a: str, b: str, c: str) -> str {\n"
        "    for i in 0..3 {\n"
        "        if i == 0 && len(a) > 3 { return a }\n"
        "        if i == 1 && len(b) > 3 { return b }\n"
        "    }\n"
        "    return c\n"
        "}\n"
        "\n"
        "#main\n"
        "fun main() {\n"
        "    var s = GREETING\n"
        '    s = s + ", " + "world"\n'
        "    print(s)\n"
        "    print(len(s))\n"
        '    print(s == "hello, world")\n'
        "    print(s != GREETING)\n"
        '    let n = Named { name: "a", n: 1 }\n'
        '    let m = rename(n, "b")\n'
        "    print(n.name)\n"
        "    print(m.name)\n"
        '    var t = Token.Word("hi")\n'
        "    print(describe(t))\n"
        "    print(describe(Token.Num(3)))\n"
        "    print(describe(Token.End))\n"
        '    var mode = "start"\n'
        "    match mode {\n"
        '        "start" => { mode = "running" },\n'
        "        _ => {},\n"
        "    }\n"
        "    print(mode)\n"
        '    print(first_long("ab", "abcd", "c"))\n'
        '    print(first_long("ab", "a", "c"))\n'
        '    var words = "x"\n'
        "    var i = 0\n"
        "    while i < 4 {\n"
        "        let piece = describe(Token.Word(words))\n"
        "        if len(piece) > 9 {\n"
        "            break\n"
        "        }\n"
        '        words = words + "y"\n'
        "        i = i + 1\n"
        "    }\n"
        "    print(words)\n"
        "}\n"
    ),
    # MYLA-105: lists through the IR: literals, push and pop (also through
    # var self and into nested lists), element reads and writes at any depth
    # with copy-on-write, for loops with an early return, string bytes
    "lists_through_the_ir": (
        "struct Item { name: str, qty: int }\n"
        "\n"
        "struct Bag { items: [Item], tags: [str] }\n"
        "\n"
        "fun total(xs: [int]) -> int {\n"
        "    var sum = 0\n"
        "    for x in xs {\n"
        "        sum = sum + x\n"
        "    }\n"
        "    return sum\n"
        "}\n"
        "\n"
        "fun names(bag: Bag) -> [str] {\n"
        "    var out: [str] = []\n"
        "    for it in bag.items {\n"
        '        push(out, it.name + "!")\n'
        "    }\n"
        "    return out\n"
        "}\n"
        "\n"
        "fun first_big(xs: [int]) -> int {\n"
        "    for x in xs {\n"
        "        if x > 10 { return x }\n"
        "    }\n"
        "    return -1\n"
        "}\n"
        "\n"
        "impl Bag {\n"
        "    fun add(var self, name: str, qty: int) {\n"
        "        push(self.items, Item { name: name, qty: qty })\n"
        "        push(self.tags, name)\n"
        "    }\n"
        "}\n"
        "\n"
        "#main\n"
        "fun main() {\n"
        "    var xs = [3, 1, 4]\n"
        "    push(xs, 1)\n"
        "    push(xs, 5)\n"
        "    print(len(xs))\n"
        "    print(total(xs))\n"
        "    print(xs[2])\n"
        "    xs[2] = 40\n"
        "    print(first_big(xs))\n"
        "    let ys = xs\n"
        "    xs[0] = 0\n"
        "    print(ys[0])\n"
        "    print(xs[0])\n"
        "    print(pop(xs))\n"
        "    print(len(xs))\n"
        '    var bag = Bag { items: [], tags: ["start"] }\n'
        '    bag.add("apple", 2)\n'
        '    bag.add("pear", 5)\n'
        "    let ns = names(bag)\n"
        "    print(ns[0] + ns[1])\n"
        "    print(len(bag.tags))\n"
        "    bag.items[1].qty = 9\n"
        "    print(bag.items[1].qty)\n"
        "    let copy = bag\n"
        "    bag.items[1].qty = 10\n"
        "    print(copy.items[1].qty)\n"
        "    print(bag.items[1].qty)\n"
        "    var grid = [[1, 2], [3]]\n"
        "    grid[1][0] = 30\n"
        "    push(grid[0], 7)\n"
        "    print(len(grid[0]) + grid[1][0])\n"
        '    let s = "hello"\n'
        "    print(s[1])\n"
        "    var words: [str] = []\n"
        "    var i = 0\n"
        "    while i < 5 {\n"
        '        push(words, "w")\n'
        "        i = i + 1\n"
        "    }\n"
        "    let last = pop(words)\n"
        "    print(last + words[0])\n"
        "    print(len(words))\n"
        "}\n"
    ),
    # MYLA-105: maps, builders, chars and format through the IR: literals,
    # reads, inserts and overwrites (of owned values), contains, remove, keys,
    # len, for loops, get, nested places with copy-on-write; StringBuilder with
    # ranges and bytes; f-strings of every printable type
    "maps_and_builders_through_the_ir": (
        "struct Pt { x: int, label: str }\n"
        "\n"
        "fun count(m: [str: int]) -> int {\n"
        "    var n = 0\n"
        "    for k in m {\n"
        "        n = n + m[k]\n"
        "    }\n"
        "    return n\n"
        "}\n"
        "\n"
        "fun describe(m: [str: int], k: str) -> str {\n"
        "    return match get(m, k) {\n"
        '        Some(v) => f"{k}={v}"\n'
        '        None => f"{k} missing"\n'
        "    }\n"
        "}\n"
        "\n"
        "fun joined(parts: [str]) -> str {\n"
        "    var sb = StringBuilder()\n"
        "    for p in parts {\n"
        "        if len(sb) > 0 { append_byte(sb, 44) }\n"
        "        append(sb, p)\n"
        "    }\n"
        "    return build(sb)\n"
        "}\n"
        "\n"
        "#main\n"
        "fun main() {\n"
        '    var m = ["a": 1, "b": 2]\n'
        '    m["c"] = 3\n'
        '    m["a"] = 10\n'
        "    print(len(m))\n"
        '    print(m["a"] + m["c"])\n'
        '    print(contains(m, "b"))\n'
        "    let saved = m\n"
        '    remove(m, "b")\n'
        '    print(contains(m, "b"))\n'
        '    print(contains(saved, "b"))\n'
        "    print(count(m))\n"
        "    print(count(saved))\n"
        '    print(describe(m, "c"))\n'
        '    print(describe(m, "z"))\n'
        "    print(len(keys(saved)))\n"
        '    var names: [int: str] = [1: "one"]\n'
        '    names[2] = "two"\n'
        '    names[1] = "uno" + "!"\n'
        "    print(names[1] + names[2])\n"
        '    var pts = ["p": Pt { x: 1, label: "first" }]\n'
        '    pts["q"] = Pt { x: 2, label: "second" }\n'
        "    let old = pts\n"
        '    pts["p"].x = 7\n'
        '    pts["p"].label = "moved"\n'
        '    print(pts["p"].x + old["p"].x)\n'
        '    print(pts["p"].label + old["p"].label)\n'
        '    var lists: [str: [int]] = ["xs": [1, 2]]\n'
        '    push(lists["xs"], 3)\n'
        '    lists["xs"][0] = 100\n'
        '    print(lists["xs"][0] + len(lists["xs"]))\n'
        '    print(joined(["x", "yy", "zzz"]))\n'
        "    var sb = StringBuilder()\n"
        '    append(sb, "hello world", 6, 11)\n'
        "    append_byte(sb, 33)\n"
        "    let built = build(sb)\n"
        "    print(built)\n"
        "    print(len(sb))\n"
        "    var vowels = 0\n"
        '    for c in chars("héllo wörld") {\n'
        "        if c == 'o' || c == 'ö' || c == 'é' { vowels = vowels + 1 }\n"
        "    }\n"
        "    print(vowels)\n"
        "    let f: float64 = 2.5\n"
        "    let ok = true\n"
        "    let ch = 'q'\n"
        '    print(f"{vowels} {f} {ok} {ch} {built}!")\n'
        '    print(format("[{}|{}]", len(m), "s"))\n'
        "}\n"
    ),
    # MYLA-105: recursive enums through the IR: boxed payloads, fields, list
    # elements and map values; recursion, patterns through boxes, member
    # writes that release the old box, push/pop/for, copies that keep theirs
    "recursive_enums_through_the_ir": (
        "enum Tree {\n"
        "    Leaf(int),\n"
        "    Node(Tree, Tree),\n"
        "    Named(str, Tree),\n"
        "}\n"
        "\n"
        "struct Holder { name: str, tree: Tree, spare: [Tree] }\n"
        "\n"
        "fun sum(t: Tree) -> int {\n"
        "    return match t {\n"
        "        Leaf(n) => n\n"
        "        Node(l, r) => sum(l) + sum(r)\n"
        "        Named(s, inner) => len(s) + sum(inner)\n"
        "    }\n"
        "}\n"
        "\n"
        "fun grow(depth: int) -> Tree {\n"
        "    if depth == 0 { return Tree.Leaf(1) }\n"
        "    return Tree.Node(grow(depth - 1), Tree.Named(\"n\", grow(depth - 1)))\n"
        "}\n"
        "\n"
        "fun leftmost(t: Tree) -> int {\n"
        "    return match t {\n"
        "        Node(Node(Leaf(a), _), _) => a * 100\n"
        "        Node(Leaf(a), _) => a * 10\n"
        "        Node(l, _) => leftmost(l)\n"
        "        Named(_, Leaf(a)) => a\n"
        "        _ => -1\n"
        "    }\n"
        "}\n"
        "\n"
        "fun first(o: Option<Tree>) -> int {\n"
        "    return match o {\n"
        "        Some(t) => sum(t)\n"
        "        None => 0\n"
        "    }\n"
        "}\n"
        "\n"
        "#main\n"
        "fun main() {\n"
        "    let t = grow(4)\n"
        "    print(sum(t))\n"
        "    print(leftmost(t))\n"
        "    print(leftmost(Tree.Node(Tree.Node(Tree.Leaf(7), Tree.Leaf(0)), Tree.Leaf(0))))\n"
        "    var h = Holder { name: \"h\", tree: Tree.Leaf(5), spare: [] }\n"
        "    let before = h\n"
        "    h.tree = Tree.Node(h.tree, Tree.Leaf(6))\n"
        "    print(sum(h.tree) + sum(before.tree))\n"
        "    push(h.spare, t)\n"
        "    push(h.spare, Tree.Named(\"xyz\", Tree.Leaf(1)))\n"
        "    var total = 0\n"
        "    for s in h.spare {\n"
        "        total = total + sum(s)\n"
        "    }\n"
        "    print(total)\n"
        "    let last = pop(h.spare)\n"
        "    print(sum(last) + len(h.spare))\n"
        "    h.spare[0] = Tree.Leaf(42)\n"
        "    print(sum(h.spare[0]))\n"
        "    var forest = [\"a\": Tree.Leaf(2)]\n"
        "    forest[\"b\"] = Tree.Node(forest[\"a\"], forest[\"a\"])\n"
        "    forest[\"a\"] = Tree.Leaf(3)\n"
        "    print(sum(forest[\"a\"]) + sum(forest[\"b\"]))\n"
        "    print(first(Some(t)) + first(None))\n"
        "    var count = 0\n"
        "    var i = 0\n"
        "    while i < 200 {\n"
        "        let big = grow(6)\n"
        "        h.tree = big\n"
        "        count = count + sum(h.tree)\n"
        "        i = i + 1\n"
        "    }\n"
        "    print(count)\n"
        "}\n"
    ),
    # MYLA-106: `?` through the IR: on Result and Option, with scalar,
    # string, aggregate and recursive-enum payloads, inside expressions,
    # conditions and loops, releasing the owners and temporaries it leaves
    "try_through_the_ir": (
        "struct Pair { name: str, n: int }\n"
        "\n"
        "enum Expr {\n"
        "    Num(int),\n"
        "    Add(Expr, Expr),\n"
        "}\n"
        "\n"
        "fun parse_num(s: str) -> Result<int, str> {\n"
        "    if len(s) == 0 { return Err(\"empty\") }\n"
        "    var n = 0\n"
        "    for c in chars(s) {\n"
        "        if c < '0' || c > '9' { return Err(\"bad \" + s) }\n"
        "        n = n * 10 + ((c as int32) - 48)\n"
        "    }\n"
        "    return Ok(n)\n"
        "}\n"
        "\n"
        "fun pair(s: str) -> Result<Pair, str> {\n"
        "    let n = parse_num(s)?\n"
        "    return Ok(Pair { name: \"p\" + s, n: n })\n"
        "}\n"
        "\n"
        "fun total(parts: [str]) -> Result<int, str> {\n"
        "    var seen: [str] = []\n"
        "    var sum = 0\n"
        "    for p in parts {\n"
        "        push(seen, p + \"!\")\n"
        "        sum = sum + pair(p)?.n\n"
        "    }\n"
        "    return Ok(sum + len(seen))\n"
        "}\n"
        "\n"
        "fun names(parts: [str]) -> Result<str, str> {\n"
        "    var out = \"\"\n"
        "    for p in parts {\n"
        "        let q = pair(p)?\n"
        "        out = out + q.name\n"
        "    }\n"
        "    return Ok(out)\n"
        "}\n"
        "\n"
        "fun tree(depth: int) -> Option<Expr> {\n"
        "    if depth < 0 { return None }\n"
        "    if depth == 0 { return Some(Expr.Num(1)) }\n"
        "    return Some(Expr.Add(tree(depth - 1)?, tree(depth - 1)?))\n"
        "}\n"
        "\n"
        "fun eval(e: Expr) -> int {\n"
        "    return match e {\n"
        "        Num(n) => n\n"
        "        Add(a, b) => eval(a) + eval(b)\n"
        "    }\n"
        "}\n"
        "\n"
        "fun first_even(xs: [int]) -> Option<int> {\n"
        "    for x in xs {\n"
        "        if x % 2 == 0 { return Some(x) }\n"
        "    }\n"
        "    return None\n"
        "}\n"
        "\n"
        "fun doubled_even(xs: [int]) -> Option<int> {\n"
        "    if first_even(xs)? > 100 { return Some(-1) }\n"
        "    return Some(first_even(xs)? * 2)\n"
        "}\n"
        "\n"
        "fun must(r: Result<int, str>) -> int {\n"
        "    return match r {\n"
        "        Ok(n) => n\n"
        "        Err(e) => { panic(e) }\n"
        "    }\n"
        "}\n"
        "\n"
        "fun show(r: Result<int, str>) -> str {\n"
        "    return match r {\n"
        "        Ok(n) => f\"ok {n}\"\n"
        "        Err(e) => f\"err {e}\"\n"
        "    }\n"
        "}\n"
        "\n"
        "#main\n"
        "fun main() {\n"
        "    print(must(parse_num(\"12\")))\n"
        "    print(show(total([\"1\", \"22\", \"333\"])))\n"
        "    print(show(total([\"1\", \"x2\", \"333\"])))\n"
        "    print(show(total([\"\", \"5\"])))\n"
        "    match names([\"7\", \"8\"]) {\n"
        "        Ok(s) => { print(s) },\n"
        "        Err(e) => { print(e) },\n"
        "    }\n"
        "    match names([\"7\", \"?\"]) {\n"
        "        Ok(s) => { print(s) },\n"
        "        Err(e) => { print(e) },\n"
        "    }\n"
        "    match tree(3) {\n"
        "        Some(e) => { print(eval(e)) },\n"
        "        None => { print(0) },\n"
        "    }\n"
        "    match tree(-1) {\n"
        "        Some(e) => { print(eval(e)) },\n"
        "        None => { print(0) },\n"
        "    }\n"
        "    match doubled_even([1, 3, 8]) {\n"
        "        Some(n) => { print(n) },\n"
        "        None => { print(-2) },\n"
        "    }\n"
        "    match doubled_even([1, 3]) {\n"
        "        Some(n) => { print(n) },\n"
        "        None => { print(-2) },\n"
        "    }\n"
        "}\n"
    ),
    # MYLA-106: function values through the IR: lambdas with and without
    # captures (strings, lists), named functions as values, partial
    # application of functions, methods and function values, composition,
    # calls through locals, fields, list elements and results, aggregate
    # results through a function value
    "function_values_through_the_ir": (
        "struct Counter { step: int, apply: (int) -> int }\n"
        "\n"
        "struct Box2 { w: int }\n"
        "\n"
        "impl Box2 {\n"
        "    fun scaled(self, k: int, d: int) -> int { return self.w * k + d }\n"
        "}\n"
        "\n"
        "fun add(a: int, b: int) -> int { return a + b }\n"
        "\n"
        "fun twice(f: (int) -> int, x: int) -> int { return f(f(x)) }\n"
        "\n"
        "fun make_adder(n: int) -> (int) -> int { return (x: int) => x + n }\n"
        "\n"
        "fun make_greeter(prefix: str) -> (str) -> str { return (name: str) => prefix + name }\n"
        "\n"
        "fun pair_of(a: int, b: int) -> (int, int) { return (a, b) }\n"
        "\n"
        "fun apply_all(fs: [(int) -> int], x: int) -> int {\n"
        "    var t = x\n"
        "    for f in fs {\n"
        "        t = f(t)\n"
        "    }\n"
        "    return t\n"
        "}\n"
        "\n"
        "#main\n"
        "fun main() {\n"
        "    print(twice(make_adder(3), 10))\n"
        "    let g = make_greeter(\"hi \")\n"
        "    print(g(\"bob\"))\n"
        "    let inc = add(1, _)\n"
        "    print(inc(41))\n"
        "    let f = add\n"
        "    print(f(2, 3))\n"
        "    let h = make_adder(1) >> make_adder(10)\n"
        "    print(h(100))\n"
        "    var fs: [(int) -> int] = [inc, make_adder(5), (x: int) => x * 2]\n"
        "    push(fs, h)\n"
        "    print(apply_all(fs, 1))\n"
        "    print(fs[1](0))\n"
        "    let c = Counter { step: 2, apply: make_adder(7) }\n"
        "    print(c.apply(c.step))\n"
        "    let mk = pair_of\n"
        "    let p = mk(4, 5)\n"
        "    print(p.0 + p.1)\n"
        "    let b = Box2 { w: 6 }\n"
        "    let sc = b.scaled(_, 1)\n"
        "    print(sc(10))\n"
        "    let again = g(_)\n"
        "    print(again(\"ann\"))\n"
        "    var words: [str] = []\n"
        "    for i in 0..3 {\n"
        "        let w = make_greeter(f\"{i}:\")\n"
        "        push(words, w(\"x\"))\n"
        "    }\n"
        "    print(words[2])\n"
        "    let big = [1, 2, 3]\n"
        "    let s = (k: int) => big[k] + len(big)\n"
        "    print(s(2))\n"
        "    print(make_adder(20)(22))\n"
        "}\n"
    ),
    # MYLA-108: `&&` and `||` results kept as values (stored, passed,
    # returned): their temporary is written in two blocks, so it can't be
    # recomputed from either
    "logical_results_as_values": (
        "fun both(a: int, b: int) -> bool {\n"
        "    return a > 1 && b > 1\n"
        "}\n"
        "\n"
        "fun show(x: bool) -> int {\n"
        "    if x { return 1 }\n"
        "    return 0\n"
        "}\n"
        "\n"
        "#main\n"
        "fun main() {\n"
        "    let a = 5\n"
        "    let b = 0\n"
        "    let and_ab = a > 1 && b > 1\n"
        "    let or_ab = a > 1 || b > 1\n"
        "    let nor = !(a < 1 || b < 1)\n"
        "    print(and_ab)\n"
        "    print(or_ab)\n"
        "    print(nor)\n"
        "    print(both(2, 3))\n"
        "    print(both(2, 0))\n"
        "    print(show(a > 1 && b == 0) + show(b > 1 || a == 0))\n"
        "    var flags: [bool] = []\n"
        "    for i in 0..4 {\n"
        "        push(flags, i % 2 == 0 && i > 0)\n"
        "    }\n"
        "    print(flags[2])\n"
        "    print(flags[1] || flags[3])\n"
        "}\n"
    ),
    # MYLA-108: aggregates built in their destination (a new variable, the
    # caller's result), with a `return` nested in the value
    "aggregates_built_in_place": (
        "struct Pair { name: str, n: int }\n"
        "\n"
        "fun make(n: int) -> Pair {\n"
        "    return Pair { name: f\"p{n}\", n: n }\n"
        "}\n"
        "\n"
        "fun pick(o: Option<Pair>) -> Result<Pair, str> {\n"
        "    let p = match o {\n"
        "        Some(x) => x\n"
        "        None => { return Err(\"none\") }\n"
        "    }\n"
        "    let q = Pair { name: p.name + \"!\", n: p.n * 2 }\n"
        "    return Ok(q)\n"
        "}\n"
        "\n"
        "fun twice(p: Pair) -> (Pair, Pair) {\n"
        "    return (p, make(p.n + 1))\n"
        "}\n"
        "\n"
        "#main\n"
        "fun main() {\n"
        "    let a = make(1)\n"
        "    let b = pick(Some(a))\n"
        "    let c = pick(None)\n"
        "    match b {\n"
        "        Ok(p) => { print(p.name) },\n"
        "        Err(e) => { print(e) },\n"
        "    }\n"
        "    match c {\n"
        "        Ok(p) => { print(p.name) },\n"
        "        Err(e) => { print(e) },\n"
        "    }\n"
        "    let t = twice(a)\n"
        "    print(t.0.name + t.1.name)\n"
        "    var total = 0\n"
        "    for i in 0..1000 {\n"
        "        let p = make(i)\n"
        "        let r = pick(Some(p))\n"
        "        match r {\n"
        "            Ok(q) => { total = total + q.n },\n"
        "            Err(e) => {},\n"
        "        }\n"
        "    }\n"
        "    print(total)\n"
        "}\n"
    ),
    # MYLA-24: chars through format() and f-strings, ASCII and multi-byte
    "format_renders_chars": (
        "struct Glyph { c: char, name: str }\n"
        "fun show(g: Glyph) -> str {\n    return f\"{g.name}={g.c}\"\n}\n"
        "#main\nfun main() {\n"
        "    print(format(\"{}\", 'a'))\n"
        "    print(format(\"[{}|{}|{}]\", 'é', '€', '😀'))\n"
        "    let c = 'z'\n"
        "    print(f\"c={c} n={c as uint32}\")\n"
        "    print(show(Glyph { c: 'ß', name: \"sharp\" }))\n"
        "    var s = \"\"\n"
        "    for i in 0..5 {\n"
        "        s = s + format(\"{}{}\", 'x', i)\n"
        "    }\n"
        "    print(s)\n"
        "    print(format(\"{} {} {}\", 'q', 1.5f64, true))\n"
        "}\n"
    ),
    "const_string_concatenation_in_functions": (
        "const TABLE: str = \"ab\" + \"cd\" + \"ef\"\n"
        "const N: int32 = 2 + 3\n"
        "fun at(i: int32) -> uint8 {\n    return TABLE[i]\n}\n"
        "fun size() -> int32 {\n    return len(TABLE) + N\n}\n"
        "#main\nfun main() {\n"
        "    var total = 0\n"
        "    for i in 0..100000 {\n"
        "        total = total + (at(i % 6) as int32) + size()\n"
        "    }\n"
        "    print(total)\n"
        "    print(TABLE)\n"
        "}\n"
    ),
    # MYLA-87: `==` on an enum without payloads compares tags; a hand-written
    # `impl Eq` on one is still called
    "derived_eq_on_plain_enums": (
        "#derive(Eq)\nenum K { A, B, C }\n"
        "enum Loose { X, Y }\n"
        "impl Eq for Loose {\n    fun eq(self, other: Loose) -> bool { return true }\n}\n"
        "#derive(Eq)\nstruct Tok { kind: K, n: int }\n"
        "fun same<T: Eq>(a: T, b: T) -> bool {\n    return a == b\n}\n"
        "#main\nfun main() {\n"
        "    let ks = [K.A, K.B, K.C]\n"
        "    for a in ks {\n"
        "        for b in ks {\n"
        "            print(f\"{a == b} {a != b} {same(a, b)}\")\n"
        "        }\n"
        "    }\n"
        "    print(Loose.X == Loose.Y)\n"
        "    print(Tok { kind: K.B, n: 1 } == Tok { kind: K.B, n: 1 })\n"
        "    print(Tok { kind: K.B, n: 1 } == Tok { kind: K.C, n: 1 })\n"
        "    var count = 0\n"
        "    for i in 0..300000 {\n"
        "        if ks[i % 3] == K.C { count = count + 1 }\n"
        "    }\n"
        "    print(count)\n"
        "}\n"
    ),
    # MYLA-80: `?` whose operand is larger than the function's result: the
    # self-hosted backend copied the whole operand into the result and
    # overwrote the caller's frame (`myla build` crashed after a type error)
    "try_with_a_larger_success_payload": (
        "struct C { a: int, b: int, c: int, d: int, e: int }\n"
        "fun load(ok: bool) -> Result<C, int> {\n"
        "    if ok { return Ok(C { a: 1, b: 2, c: 3, d: 4, e: 5 }) }\n"
        "    return Err(7)\n}\n"
        "fun compile(ok: bool) -> Result<int, int> {\n"
        "    let c = load(ok)?\n"
        "    return Ok(c.a + c.e)\n}\n"
        "fun first(xs: [int]) -> Option<(int, int, int, int)> {\n"
        "    if len(xs) == 0 { return None }\n"
        "    return Some((xs[0], 0, 0, 0))\n}\n"
        "fun head(xs: [int]) -> Option<int> {\n"
        "    let t = first(xs)?\n"
        "    return Some(t.0)\n}\n"
        "fun describe(ok: bool) -> Result<str, str> {\n"
        "    let c = match load(ok) { Ok(c) => c, Err(e) => { return Err(format(\"error {}\", e)) } }\n"
        "    return Ok(format(\"{}\", c.b))\n}\n"
        "#main\nfun main() {\n"
        "    for i in 0..3 {\n"
        "        match compile(i == 1) { Ok(v) => { print(v) }, Err(e) => { print(e) } }\n"
        "        match head([]) { Some(v) => { print(v) }, None => { print(-1) } }\n"
        "        match head([9]) { Some(v) => { print(v) }, None => { print(-1) } }\n"
        "        match describe(i == 2) { Ok(s) => { print(s) }, Err(s) => { print(s) } }\n"
        "    }\n}\n"
    ),
    "string_char_literals_and_match": (
        "fun count_byte(s: str, b: uint8) -> int {\n"
        "    var n = 0\n    var i = 0\n"
        "    while i < len(s) {\n        if s[i] == b {\n            n = n + 1\n        }\n"
        "        i = i + 1\n    }\n    return n\n}\n"
        "fun vowel(c: uint8) -> int {\n"
        "    return match c {\n        'a' => 1,\n        'e' => 1,\n        _ => 0,\n    }\n}\n"
        "#main\nfun main() {\n"
        '    print(count_byte("banana", \'a\'))\n'
        "    let nl = '\\n'\n    print(nl as int)\n    print('\\0' as int)\n"
        '    print(vowel("apple"[0]))\n    print(vowel("xyz"[0]))\n}\n'
    ),
    "tuple_multi_return_and_index": (
        "fun divmod(a: int, b: int) -> (int, int) {\n"
        "    return a / b, a % b\n}\n"
        "#main\nfun main() {\n"
        "    let (q, r) = divmod(17, 5)\n    print(q)\n    print(r)\n"
        "    let t = (1, 2, 3)\n    print(t.0 + t.1 + t.2)\n}\n"
    ),
    "tuple_nested_and_struct_payload": (
        "struct P { x: int, y: int }\n"
        "fun shift(p: P, by: int) -> (P, int) {\n"
        "    return P { x: p.x + by, y: p.y + by }, by\n}\n"
        "#main\nfun main() {\n"
        "    let ((a, b), c) = ((10, 20), 30)\n    print(a + b + c)\n"
        "    let (moved, amount) = shift(P { x: 1, y: 2 }, 5)\n"
        "    print(moved.x)\n    print(moved.y)\n    print(amount)\n}\n"
    ),
    "tuple_value_semantics": (
        "struct P { x: int }\n"
        "#main\nfun main() {\n"
        "    let orig = P { x: 1 }\n    let t = (orig, 7)\n"
        "    var c = t.0\n    c.x = 99\n    print(orig.x)\n    print(c.x)\n}\n"
    ),
    "enum_payload_and_match": (
        "enum Shape { Circle(int), Rect(int, int), Empty }\n"
        "fun area(s: Shape) -> int {\n"
        "    return match s {\n"
        "        Shape.Circle(r) => 3 * r * r,\n"
        "        Shape.Rect(w, h) => w * h,\n"
        "        Shape.Empty => 0,\n"
        "    }\n}\n"
        "#main\nfun main() {\n"
        "    print(area(Shape.Circle(2)))\n    print(area(Shape.Rect(3, 4)))\n"
        "    print(area(Shape.Empty))\n}\n"
    ),
    "enum_guards_or_and_nested": (
        "struct P { x: int, y: int }\n"
        "enum Tree { Leaf(int), Node(P, int) }\n"
        "enum Color { Red, Green, Blue }\n"
        "fun describe(c: Color) -> str {\n"
        "    return match c { Red => \"warm\", Green | Blue => \"cool\" }\n}\n"
        "fun sum(t: Tree) -> int {\n"
        "    return match t {\n"
        "        Tree.Leaf(n) if n > 100 => 0,\n"
        "        Tree.Leaf(n) => n,\n"
        "        Tree.Node(P { x, y }, w) => x + y + w,\n"
        "    }\n}\n"
        "#main\nfun main() {\n"
        "    print(describe(Color.Red))\n    print(describe(Color.Blue))\n"
        "    print(sum(Tree.Leaf(7)))\n    print(sum(Tree.Leaf(200)))\n"
        "    print(sum(Tree.Node(P { x: 1, y: 2 }, 3)))\n}\n"
    ),
    "match_returns_enum_and_statement": (
        "enum Opt { Some(int), None }\n"
        "fun unwrap_or(o: Opt, d: int) -> int {\n"
        "    return match o { Opt.Some(n) => n, Opt.None => d }\n}\n"
        "fun bump(o: Opt) -> Opt {\n"
        "    return match o { Opt.Some(n) => Opt.Some(n + 1), Opt.None => Opt.None }\n}\n"
        "#main\nfun main() {\n"
        "    print(unwrap_or(bump(Opt.Some(41)), 0))\n"
        "    var seen = 0\n"
        "    match Opt.Some(5) { Opt.Some(n) => { seen = n } Opt.None => { seen = -1 } }\n"
        "    print(seen)\n}\n"
    ),
    # --- v0.2.3 recursive enums: heap boxing ---
    "recursive_list_sum_len": (
        "enum List { Cons(int, List), Nil }\n"
        "fun sum(xs: List) -> int {\n"
        "    return match xs { List.Cons(h, t) => h + sum(t), List.Nil => 0 }\n}\n"
        "fun count(xs: List) -> int {\n"
        "    return match xs { List.Cons(_, t) => 1 + count(t), List.Nil => 0 }\n}\n"
        "#main\nfun main() {\n"
        "    let xs = List.Cons(10, List.Cons(20, List.Cons(30, List.Nil)))\n"
        "    print(sum(xs))\n    print(count(xs))\n}\n"
    ),
    "recursive_list_rebuild": (
        "enum List { Cons(int, List), Nil }\n"
        "fun sum(xs: List) -> int {\n"
        "    return match xs { List.Cons(h, t) => h + sum(t), List.Nil => 0 }\n}\n"
        "fun map_inc(xs: List) -> List {\n"
        "    return match xs {\n"
        "        List.Cons(h, t) => List.Cons(h + 1, map_inc(t)),\n"
        "        List.Nil => List.Nil,\n"
        "    }\n}\n"
        "#main\nfun main() {\n"
        "    let xs = List.Cons(1, List.Cons(2, List.Cons(3, List.Nil)))\n"
        "    print(sum(map_inc(xs)))\n}\n"
    ),
    "recursive_tree_nested_patterns": (
        "enum Tree { Leaf(int), Node(Tree, Tree) }\n"
        "fun total(t: Tree) -> int {\n"
        "    return match t { Tree.Leaf(n) => n, Tree.Node(l, r) => total(l) + total(r) }\n}\n"
        "fun shape(t: Tree) -> str {\n"
        "    return match t {\n"
        "        Tree.Node(Tree.Leaf(a), Tree.Leaf(b)) if a == b => \"twins\",\n"
        "        Tree.Node(Tree.Leaf(_), Tree.Leaf(_)) => \"pair\",\n"
        "        Tree.Node(_, _) => \"branch\",\n"
        "        Tree.Leaf(_) => \"leaf\",\n"
        "    }\n}\n"
        "#main\nfun main() {\n"
        "    let t = Tree.Node(Tree.Node(Tree.Leaf(1), Tree.Leaf(2)), Tree.Leaf(7))\n"
        "    print(total(t))\n"
        "    print(shape(Tree.Node(Tree.Leaf(5), Tree.Leaf(5))))\n"
        "    print(shape(Tree.Node(Tree.Leaf(5), Tree.Leaf(6))))\n"
        "    print(shape(t))\n}\n"
    ),
    "recursive_enum_in_struct_and_tuple": (
        "enum List { Cons(int, List), Nil }\n"
        "struct Holder { tag: int, items: List }\n"
        "fun sum(xs: List) -> int {\n"
        "    return match xs { List.Cons(h, t) => h + sum(t), List.Nil => 0 }\n}\n"
        "fun pack(xs: List) -> (int, List) {\n    return sum(xs), xs\n}\n"
        "#main\nfun main() {\n"
        "    let xs = List.Cons(4, List.Cons(5, List.Nil))\n"
        "    let h = Holder { tag: 1, items: xs }\n"
        "    print(h.tag)\n    print(sum(h.items))\n"
        "    let (s, ys) = pack(xs)\n    print(s)\n    print(sum(ys))\n}\n"
    ),
    # --- v0.2.3b reference counting: aliasing/reassignment must stay correct ---
    "rc_shared_aliasing": (
        # `ys` shares `xs`'s spine (a retain); both stay usable, then a longer
        # list is built sharing the tail again. A refcount bug here double-frees.
        "enum List { Cons(int, List), Nil }\n"
        "fun sum(xs: List) -> int {\n"
        "    return match xs { List.Cons(h, t) => h + sum(t), List.Nil => 0 }\n}\n"
        "#main\nfun main() {\n"
        "    let xs = List.Cons(1, List.Cons(2, List.Nil))\n"
        "    let ys = xs\n"
        "    let zs = List.Cons(0, xs)\n"
        "    print(sum(xs))\n    print(sum(ys))\n    print(sum(zs))\n}\n"
    ),
    "rc_reassign_prepend_loop": (
        # repeatedly reassign a recursive-enum variable, reading its old value —
        # exercises drop-old / build-new ordering in `_gen_assign`.
        "enum List { Cons(int, List), Nil }\n"
        "fun sum(xs: List) -> int {\n"
        "    return match xs { List.Cons(h, t) => h + sum(t), List.Nil => 0 }\n}\n"
        "fun count(xs: List) -> int {\n"
        "    return match xs { List.Cons(_, t) => 1 + count(t), List.Nil => 0 }\n}\n"
        "#main\nfun main() {\n"
        "    var acc = List.Nil\n    var i = 1\n"
        "    while i <= 5 {\n        acc = List.Cons(i, acc)\n        i = i + 1\n    }\n"
        "    print(sum(acc))\n    print(count(acc))\n}\n"
    ),
    "rc_match_returns_binding": (
        # an arm result is a borrowed binding that escapes (must be retained).
        "enum List { Cons(int, List), Nil }\n"
        "fun tail(xs: List) -> List {\n"
        "    return match xs { List.Cons(_, t) => t, List.Nil => List.Nil }\n}\n"
        "fun sum(xs: List) -> int {\n"
        "    return match xs { List.Cons(h, t) => h + sum(t), List.Nil => 0 }\n}\n"
        "#main\nfun main() {\n"
        "    let xs = List.Cons(7, List.Cons(8, List.Cons(9, List.Nil)))\n"
        "    let t = tail(xs)\n    print(sum(t))\n    print(sum(xs))\n}\n"
    ),
    "rc_nested_temps": (
        # deep temporary chains: append/map/sum nest, dropping intermediates.
        "enum List { Cons(int, List), Nil }\n"
        "fun sum(xs: List) -> int {\n"
        "    return match xs { List.Cons(h, t) => h + sum(t), List.Nil => 0 }\n}\n"
        "fun cat(a: List, b: List) -> List {\n"
        "    return match a {\n"
        "        List.Cons(h, t) => List.Cons(h, cat(t, b)),\n"
        "        List.Nil => b,\n"
        "    }\n}\n"
        "fun dbl(xs: List) -> List {\n"
        "    return match xs {\n"
        "        List.Cons(h, t) => List.Cons(h * 2, dbl(t)),\n"
        "        List.Nil => List.Nil,\n"
        "    }\n}\n"
        "#main\nfun main() {\n"
        "    let a = List.Cons(1, List.Cons(2, List.Nil))\n"
        "    let b = List.Cons(3, List.Nil)\n"
        "    print(sum(dbl(cat(a, b))))\n}\n"
    ),
    # --- v0.2.4a generics: monomorphization (D13), call-site inference (D34) ---
    "generic_id_multi_instantiation": (
        # one `id<T>` stamped out at three concrete types from the call sites.
        "fun id<T>(x: T) -> T {\n    return x\n}\n"
        "#main\nfun main() {\n"
        "    print(id(7))\n    print(id(255u8))\n"
        '    print(id(true))\n    print(id("hi"))\n}\n'
    ),
    "generic_tuple_param_and_result": (
        # type parameters threaded through tuple parameters and results.
        "fun swap<A, B>(p: (A, B)) -> (B, A) {\n"
        "    let (a, b) = p\n    return (b, a)\n}\n"
        "fun firstof<T>(p: (T, T)) -> T {\n"
        "    let (a, _) = p\n    return a\n}\n"
        "#main\nfun main() {\n"
        "    let (x, y) = swap((1, 2))\n    print(x)\n    print(y)\n"
        "    print(firstof((10, 20)))\n}\n"
    ),
    "generic_calls_generic": (
        # a generic body calls another generic; the inner call is monomorphized
        # per instantiation of the outer one (T=int32 and T=uint8 here).
        "fun id<T>(x: T) -> T {\n    return x\n}\n"
        "fun dup<T>(x: T) -> (T, T) {\n"
        "    let a = id(x)\n    return (a, a)\n}\n"
        "#main\nfun main() {\n"
        "    let (p, q) = dup(8)\n    print(p + q)\n"
        "    let (r, s) = dup(100u8)\n    print(r + s)\n}\n"
    ),
    "generic_struct_payload_value_semantics": (
        # a struct flows through `id<T>`; value semantics must be preserved.
        "struct P { x: int, y: int }\n"
        "fun id<T>(x: T) -> T {\n    return x\n}\n"
        "#main\nfun main() {\n"
        "    let p = P { x: 3, y: 4 }\n    var q = id(p)\n    q.x = 99\n"
        "    print(p.x)\n    print(q.x)\n    print(q.y)\n}\n"
    ),
    "generic_struct_two_instantiations": (
        # Box<int> and Box<bool> are distinct stamped layouts.
        "struct Box<T> { value: T }\n"
        "fun unbox<T>(b: Box<T>) -> T {\n    return b.value\n}\n"
        "#main\nfun main() {\n"
        "    print(unbox(Box { value: 7 }))\n"
        "    print(unbox(Box { value: true }))\n"
        "    let b: Box<uint8> = Box { value: 250u8 }\n    print(b.value + 5u8)\n}\n"
    ),
    "generic_struct_mixed_params": (
        # Pair<A, B> with two independent parameters, field access per arm.
        "struct Pair<A, B> { first: A, second: B }\n"
        "fun fst<A, B>(p: Pair<A, B>) -> A {\n    return p.first\n}\n"
        "#main\nfun main() {\n"
        "    let p = Pair { first: 11, second: true }\n"
        "    print(fst(p))\n    print(p.second)\n"
        "    let q = Pair { first: false, second: 99 }\n"
        "    print(q.second)\n}\n"
    ),
    "generic_enum_expected_inference": (
        # `Maybe.Nothing` takes its type from the annotation; `Just` from its arg.
        "enum Maybe<T> { Just(T), Nothing }\n"
        "fun unwrap_or<T>(m: Maybe<T>, d: T) -> T {\n"
        "    return match m { Maybe.Just(v) => v, Maybe.Nothing => d }\n}\n"
        "#main\nfun main() {\n"
        "    print(unwrap_or(Maybe.Just(5), 0))\n"
        "    let n: Maybe<int> = Maybe.Nothing\n    print(unwrap_or(n, -1))\n}\n"
    ),
    "generic_recursive_enum_rc": (
        # a recursive generic enum (List<T>) is boxed + reference-counted per
        # instantiation; the reassignment loop frees and reuses cells.
        "enum List<T> { Cons(T, List<T>), Nil }\n"
        "fun prepend<T>(x: T, xs: List<T>) -> List<T> {\n"
        "    return List.Cons(x, xs)\n}\n"
        "fun sum(xs: List<int>) -> int {\n"
        "    return match xs { List.Cons(h, t) => h + sum(t), List.Nil => 0 }\n}\n"
        "fun length<T>(xs: List<T>) -> int {\n"
        "    return match xs { List.Cons(_, t) => 1 + length(t), List.Nil => 0 }\n}\n"
        "#main\nfun main() {\n"
        "    var acc: List<int> = List.Nil\n    var i = 0\n"
        "    while i < 40 {\n        acc = prepend(i, acc)\n        i = i + 1\n    }\n"
        "    print(sum(acc))\n    print(length(acc))\n"
        "    let ss: List<str> = prepend(\"a\", prepend(\"b\", List.Nil))\n"
        "    print(length(ss))\n}\n"
    ),
    "generic_enum_of_struct_nested": (
        # nested instantiation: List<Box<int>> stamps List__Box__int32 etc.
        "struct Box<T> { value: T }\n"
        "enum Opt<T> { Some(T), None }\n"
        "fun get_or<T>(o: Opt<T>, d: T) -> T {\n"
        "    return match o { Opt.Some(v) => v, Opt.None => d }\n}\n"
        "#main\nfun main() {\n"
        "    let o: Opt<Box<int>> = Opt.Some(Box { value: 42 })\n"
        "    let b = get_or(o, Box { value: 0 })\n    print(b.value)\n}\n"
    ),
    "try_result_propagation": (
        # `?` short-circuits on the first Err; bare Ok/Err constructors.
        "fun safe_div(a: int, b: int) -> Result<int, str> {\n"
        "    if b == 0 {\n        return Err(\"div0\")\n    }\n"
        "    return Ok(a / b)\n}\n"
        "fun chain(a: int, b: int, c: int) -> Result<int, str> {\n"
        "    let x = safe_div(a, b)?\n    let y = safe_div(x, c)?\n"
        "    return Ok(y + 1)\n}\n"
        "fun show(r: Result<int, str>) -> int {\n"
        "    return match r { Ok(v) => v, Err(_) => -1 }\n}\n"
        "#main\nfun main() {\n"
        "    print(show(chain(100, 5, 2)))\n"
        "    print(show(chain(100, 0, 2)))\n"
        "    print(show(chain(100, 5, 0)))\n}\n"
    ),
    "try_option_propagation": (
        # `?` on Option returns None early; bare Some/None constructors.
        "fun first(a: int, b: int) -> Option<int> {\n"
        "    if a > 0 {\n        return Some(a)\n    }\n"
        "    if b > 0 {\n        return Some(b)\n    }\n"
        "    return None\n}\n"
        "fun bumped(a: int, b: int) -> Option<int> {\n"
        "    let v = first(a, b)?\n    return Some(v + 100)\n}\n"
        "fun show(o: Option<int>) -> int {\n"
        "    return match o { Some(v) => v, None => -1 }\n}\n"
        "#main\nfun main() {\n"
        "    print(show(bumped(-1, 7)))\n    print(show(bumped(-1, -1)))\n}\n"
    ),
    "try_aggregate_payload": (
        # `?` unwrapping a Result whose Ok payload is an aggregate (a struct).
        "struct P { x: int, y: int }\n"
        "fun make(v: int) -> Result<P, str> {\n"
        "    if v < 0 {\n        return Err(\"neg\")\n    }\n"
        "    return Ok(P { x: v, y: v * 2 })\n}\n"
        "fun total(v: int) -> Result<int, str> {\n"
        "    let p = make(v)?\n    return Ok(p.x + p.y)\n}\n"
        "fun show(r: Result<int, str>) -> int {\n"
        "    return match r { Ok(v) => v, Err(_) => -1 }\n}\n"
        "#main\nfun main() {\n"
        "    print(show(total(5)))\n    print(show(total(-1)))\n}\n"
    ),
    # --- v0.4.2 function types, lambdas & closures ---
    "closures_higher_order": (
        # capture-by-value, a plain `fun` used as a value, a closure stored in a
        # struct field, and a generic higher-order helper returning a closure.
        "struct Adder { f: (int) -> int }\n"
        "fun inc(n: int) -> int {\n    return n + 1\n}\n"
        "fun compose(f: (int) -> int, g: (int) -> int) -> (int) -> int {\n"
        "    return (x: int) => f(g(x))\n}\n"
        "#main\nfun main() {\n"
        "    let k = 10\n"
        "    let bump = (x: int) => x + k\n"            # captures k by value
        "    print(bump(5))\n"                          # 15
        "    let g = inc\n    print(g(41))\n"           # 42 (fun as value)
        "    let a = Adder { f: (x: int) => x * x }\n"
        "    print(a.f(7))\n"                           # 49 (closure in a field)
        "    let h = compose((x: int) => x * 2, inc)\n"  # 2*(x+1)
        "    print(h(20))\n}\n"                         # 42
    ),
    "closure_captures_list_deep_immutable": (
        # A closure captures a list *by value* (D14/D48): later mutation of the
        # original list (push / element assignment, both copy-on-write) is
        # invisible to the captured snapshot.
        "#main\nfun main() {\n"
        "    var xs: [int] = []\n"
        "    push(xs, 1)\n    push(xs, 2)\n"
        "    let snapshot = (i: int) => xs[i]\n"
        "    push(xs, 3)\n    xs[0] = 99\n"
        "    print(snapshot(0))\n"                      # 1
        "    print(snapshot(1))\n"                      # 2
        "    print(len(xs))\n"                          # 3
        "    print(xs[0])\n}\n"                         # 99
    ),
    # --- v0.4.3 pipelines, composition & partial application ---
    "pipelines_compose_partial": (
        # `|>` splices the left value as the first argument; `>>` composes two
        # function values; `_` partially applies. All desugar to v0.4.2 calls
        # and lambdas, so the native binary must match the interpreter.
        "fun double(n: int) -> int {\n    return n * 2\n}\n"
        "fun inc(n: int) -> int {\n    return n + 1\n}\n"
        "fun add(a: int, b: int) -> int {\n    return a + b\n}\n"
        "#main\nfun main() {\n"
        "    print(5 |> double |> inc)\n"               # inc(double(5)) = 11
        "    print(5 |> add(3))\n"                       # add(5, 3) = 8
        "    let f = double >> inc >> double\n"
        "    print(f(3))\n"                              # double(inc(double(3))) = 14
        "    let add5 = add(5, _)\n    print(add5(10))\n"   # 15
        "    let half = add(_, 2)\n    print(half(40))\n}\n"  # 42
    ),
    "compose_partial_capture": (
        # Composition over *local* function values that capture, plus a
        # partial application whose filled argument is a captured variable —
        # both build refcounted closure environments at runtime.
        "fun add(a: int, b: int) -> int {\n    return a + b\n}\n"
        "#main\nfun main() {\n"
        "    let k = 100\n"
        "    let bump = (x: int) => x + k\n"            # captures k
        "    let twice = (x: int) => x * 2\n"
        "    let combo = bump >> twice\n"               # (x) => (x + 100) * 2
        "    print(combo(1))\n"                          # 202
        "    let base = 7\n"
        "    let plus_base = add(base, _)\n"            # captures base
        "    print(plus_base(35))\n}\n"                  # 42
    ),
    # --- v0.4.4 traits, operator overloading & derivable Eq ---
    "traits_operators_derive": (
        # Operator overloading (`+`/`==`/`<` -> Add/Eq/Ord methods), a user
        # trait method, and `#derive(Eq)` over a struct with a nested enum.
        "struct V { x: int, y: int }\n"
        "impl Add for V {\n"
        "    fun add(self, o: V) -> V { return V { x: self.x + o.x, y: self.y + o.y } }\n"
        "}\n"
        "impl Eq for V { fun eq(self, o: V) -> bool { return self.x == o.x && self.y == o.y } }\n"
        "impl Ord for V { fun cmp(self, o: V) -> int { return (self.x + self.y) - (o.x + o.y) } }\n"
        "trait Name { fun name(self) -> str }\n"
        "impl Name for V { fun name(self) -> str { return \"v\" } }\n"
        "#derive(Eq)\nenum Tag { A, B(int) }\n"
        "#derive(Eq)\nstruct Cell { v: V, tag: Tag }\n"
        "#main\nfun main() {\n"
        "    let s = V { x: 1, y: 2 } + V { x: 3, y: 4 }\n"
        "    print(s.x)\n    print(s.y)\n"                       # 4, 6
        "    print(s == V { x: 4, y: 6 })\n"                     # true
        "    print(s != V { x: 0, y: 0 })\n"                     # true
        "    print(V { x: 1, y: 1 } < V { x: 5, y: 5 })\n"       # true
        "    print(s.name())\n"                                  # v
        "    print(Tag.B(3) == Tag.B(3))\n"                      # true
        "    print(Tag.B(3) == Tag.A)\n"                         # false
        "    let c = Cell { v: V { x: 1, y: 2 }, tag: Tag.A }\n"
        "    print(c == Cell { v: V { x: 1, y: 2 }, tag: Tag.A })\n}\n"  # true
    ),
    "trait_generic_bounds": (
        # Limited generic bounds (`<T: Add>` / `<T: Ord>`) dispatched over both a
        # primitive and a user type: the body uses the bound's operators.
        "struct V { x: int }\n"
        "impl Add for V { fun add(self, o: V) -> V { return V { x: self.x + o.x } } }\n"
        "impl Ord for V { fun cmp(self, o: V) -> int { return self.x - o.x } }\n"
        "fun sum<T: Add>(xs: [T], zero: T) -> T {\n"
        "    var acc = zero\n    for x in xs { acc = acc + x }\n    return acc\n}\n"
        "fun max_of<T: Ord>(a: T, b: T) -> T {\n    if a > b { return a }\n    return b\n}\n"
        "#main\nfun main() {\n"
        "    print(sum([1, 2, 3, 4], 0))\n"                       # 10
        "    let v = sum([V { x: 1 }, V { x: 2 }, V { x: 3 }], V { x: 0 })\n"
        "    print(v.x)\n"                                        # 6
        "    print(max_of(3, 9))\n"                               # 9
        "    print(max_of(V { x: 5 }, V { x: 2 }).x)\n}\n"        # 5
    ),
    # --- v0.5.2 floats (D56): arithmetic, casts, comparisons, printing ---
    "float_arithmetic": (
        "#main\nfun main() {\n"
        "    print(1.5 + 2.25)\n    print(1.5 - 2.25)\n    print(1.5 * 2.25)\n"
        "    print(7.0 / 2.0)\n    print(5.5 % 2.0)\n    print(-3.5)\n"
        "    print(0.1f64 + 0.2f64)\n    print(0.1f32 + 0.2f32)\n"
        "    print(2.0)\n    print(100000.0f64)\n    print(123.456)\n"
        "    print(0.0009765625f64)\n}\n"
    ),
    "float_nonfinite": (
        "#main\nfun main() {\n"
        "    print(1.0 / 0.0)\n    print(-1.0 / 0.0)\n    print(0.0 / 0.0)\n"
        "    print(-0.0f64)\n    print(0.0f64)\n}\n"
    ),
    "float_casts": (
        "#main\nfun main() {\n"
        "    print(3.9 as int32)\n    print(-3.9 as int32)\n"
        "    print(5 as float64)\n    print(5 as float32)\n"
        "    print(300.0f64 as int8)\n"                            # truncate + wrap
        "    let big: uint64 = 18446744073709551615u64\n"
        "    print(big as float64)\n"
        "    print(1.5f64 as float32)\n    print(1.5f32 as float64)\n}\n"
    ),
    "float_compare_and_control": (
        "#main\nfun main() {\n"
        "    print(1.5 < 2.0)\n    print(2.0 <= 2.0)\n    print(3.0 > 2.0)\n"
        "    print(2.0 >= 3.0)\n    print(2.0 == 2.0)\n    print(2.0 != 2.0)\n"
        "    let nan = 0.0 / 0.0\n    print(nan == nan)\n    print(nan != nan)\n"
        "    print(nan < 1.0)\n"
        "    var sum = 0.0f64\n    var i = 0\n"
        "    while i < 5 { sum = sum + 1.5f64\n i = i + 1 }\n    print(sum)\n}\n"
    ),
    "float_functions_and_const": (
        "const TAU: float64 = 6.283185307179586f64\n"
        "fun area(r: float64) -> float64 { return TAU / 2.0 * r * r }\n"
        "#main\nfun main() {\n"
        "    print(TAU)\n    print(area(2.0f64))\n"
        "    let xs = [1.5f64, 2.5f64, 3.0f64]\n"
        "    var acc = 0.0f64\n    for x in xs { acc = acc + x }\n    print(acc)\n"
        "    print(format(\"r={} area={}\", 2.0f64, area(2.0f64)))\n}\n"
    ),
    # --- v0.5.3a chars (D25): Unicode-scalar literals, UTF-8 glyphs, casts ---
    "char_print_utf8": (
        "#main\nfun main() {\n"
        "    print('a')\n"                                  # 1-byte
        "    print('\\u{A5}')\n"                            # 2-byte (¥)
        "    print('\\u{3BB}')\n"                           # 2-byte (λ)
        "    print('\\u{20AC}')\n"                          # 3-byte (€)
        "    print('\\u{1F600}')\n"                         # 4-byte (😀)
        "    print('\\n')\n    print('\\u{0}' as uint32)\n}\n"
    ),
    "char_compare_cast": (
        "#main\nfun main() {\n"
        "    print('a' < 'b')\n    print('b' <= 'b')\n    print('z' > 'a')\n"
        "    print('a' == 'a')\n    print('a' != 'b')\n"
        "    print('A' as uint32)\n    print('\\u{1F600}' as uint32)\n"
        "    print(65 as char)\n    print(955 as char)\n"
        "    let s = \"hello\"\n    print(s[0] == 'h')\n"
        "    print(format(\"{}-{}\", 'x', '\\u{3BB}'))\n}\n"
    ),
    "char_classify_and_map": (
        "fun is_vowel(c: char) -> bool {\n"
        "    return c == 'a' || c == 'e' || c == 'i' || c == 'o' || c == 'u'\n}\n"
        "#main\nfun main() {\n"
        "    print(is_vowel('e'))\n    print(is_vowel('x'))\n"
        "    var m: [char: int] = [:]\n"
        "    m['a'] = 1\n    m['\\u{3BB}'] = 2\n"
        "    print(m['a'])\n    print(m['\\u{3BB}'])\n"
        "    let c: char = 'b'\n"
        "    print(match c { 'a' => 10, 'b' => 20, _ => 0 })\n}\n"
    ),
    # --- v0.5.3b chars(): UTF-8 codepoint iteration + bytes view (s[i]/len) ---
    "char_chars_iteration": (
        "fun vowels(s: str) -> int {\n"
        "    var n = 0\n"
        "    for c in chars(s) {\n"
        "        if c == 'a' || c == 'e' || c == 'i' || c == 'o' || c == 'u' {\n"
        "            n = n + 1\n        }\n    }\n    return n\n}\n"
        "#main\nfun main() {\n"
        "    let s = \"h\u00e9\u03bb\U0001f600w\u00f6\"\n"  # raw multibyte UTF-8
        "    print(len(s))\n"                  # 1+2+2+4+1+2 = 12 bytes
        "    print(len(chars(s)))\n"           # 6 scalars
        "    for c in chars(s) { print(c as uint32) }\n"
        "    print(vowels(\"education\"))\n"   # 5
        "    print(len(chars(\"\")))\n}\n"     # 0
    ),
    # MYLA-4: a mutating builtin evaluates its value argument before it touches
    # the container. A `?` that returns early from inside the argument must
    # leave the container as it was (no zeroed slot to drop or to leak to the
    # caller through `var self`).
    "try_inside_push_leaves_the_list_intact": (
        "struct P { name: str, tags: [int] }\n"
        "enum Tree { Leaf(int), Node(Tree, Tree) }\n"
        "struct Bag { items: [[int]] }\n"
        "fun upto(n: int, limit: int) -> Result<int, str> {\n"
        "    if n >= limit { return Err(\"stop\") }\n    return Ok(n)\n}\n"
        "impl Bag {\n"
        "    fun fill(var self, n: int) -> Result<int, str> {\n"
        "        var i = 0\n"
        "        while i < n {\n"
        "            push(self.items, [upto(i, 2)?])\n"
        "            i = i + 1\n        }\n"
        "        return Ok(len(self.items))\n    }\n}\n"
        "fun lists(n: int) -> Result<int, str> {\n"
        "    var xs: [[int]] = []\n"
        "    for i in 0..n { push(xs, [upto(i, 2)?]) }\n"
        "    return Ok(len(xs))\n}\n"
        "fun structs(n: int) -> Result<int, str> {\n"
        "    var ps: [P] = []\n"
        "    for i in 0..n { push(ps, P { name: \"p\", tags: [upto(i, 2)?] }) }\n"
        "    return Ok(len(ps))\n}\n"
        "fun trees(n: int) -> Result<int, str> {\n"
        "    var ts: [Tree] = []\n"
        "    for i in 0..n { push(ts, Tree.Leaf(upto(i, 2)?)) }\n"
        "    return Ok(len(ts))\n}\n"
        "fun show(r: Result<int, str>) {\n"
        "    match r { Ok(k) => print(k), Err(e) => print(e) }\n}\n"
        "#main\nfun main() {\n"
        "    var b = Bag { items: [] }\n"
        "    show(b.fill(5))\n"
        "    print(len(b.items))\n"            # 2: no half-pushed third item
        "    show(lists(2))\n    show(lists(5))\n"
        "    show(structs(2))\n    show(structs(5))\n"
        "    show(trees(2))\n    show(trees(5))\n}\n"
    ),
    "try_inside_map_insert_leaves_the_map_intact": (
        "struct Index { m: [int: [int]] }\n"
        "fun upto(n: int, limit: int) -> Result<int, str> {\n"
        "    if n >= limit { return Err(\"stop\") }\n    return Ok(n)\n}\n"
        "impl Index {\n"
        "    fun fill(var self, n: int) -> Result<int, str> {\n"
        "        for i in 0..n { self.m[i] = [upto(i, 2)?] }\n"
        "        return Ok(len(self.m))\n    }\n}\n"
        "#main\nfun main() {\n"
        "    var ix = Index { m: [:] }\n"
        "    match ix.fill(5) { Ok(k) => print(k), Err(e) => print(e) }\n"
        "    print(len(ix.m))\n"
        "    for k in keys(ix.m) { print(len(ix.m[k])) }\n}\n"
    ),
    "try_inside_append_byte_leaves_the_builder_intact": (
        "struct Out { sb: StringBuilder }\n"
        "fun upto(n: int, limit: int) -> Result<int, str> {\n"
        "    if n >= limit { return Err(\"stop\") }\n    return Ok(n)\n}\n"
        "impl Out {\n"
        "    fun fill(var self, n: int) -> Result<int, str> {\n"
        "        for i in 0..n { append_byte(self.sb, (65 + upto(i, 2)?) as uint8) }\n"
        "        return Ok(n)\n    }\n}\n"
        "#main\nfun main() {\n"
        "    var o = Out { sb: StringBuilder() }\n"
        "    match o.fill(5) { Ok(k) => print(k), Err(e) => print(e) }\n"
        "    print(build(o.sb))\n}\n"
    ),
    "push_evaluates_its_value_before_the_list": (
        "#main\nfun main() {\n"
        "    var xs = [1, 2, 3]\n"
        "    push(xs, pop(xs) * 10)\n"         # [1, 2, 30]
        "    print(len(xs))\n"
        "    for x in xs { print(x) }\n"
        "    var m: [int: int] = [:]\n"
        "    m[1] = 5\n"
        "    m[2] = len(m) * 100\n"            # the size before the insert
        "    print(m[2])\n}\n"
    ),
    # MYLA-72: `?` in a lambda is checked against the lambda's result type,
    # so the enclosing function needn't return an Option
    "try_in_lambdas_checks_against_the_lambda": (
        "fun half(x: int) -> Option<int> {\n"
        "    if x % 2 == 1 { return None }\n    return Some(x / 2)\n}\n"
        "fun parse(s: str) -> Result<int, str> {\n"
        "    if s == \"\" { return Err(\"empty\") }\n    return Ok(len(s))\n}\n"
        "fun apply(f: (int) -> Option<int>, x: int) -> int {\n"
        "    return match f(x) { Some(v) => v, None => -1 }\n}\n"
        "#main\nfun main() {\n"
        "    let g: (int) -> Option<int> = (x: int) => Some(half(x)? + 100)\n"
        "    print(apply(g, 4))\n    print(apply(g, 3))\n"
        "    print(apply((x) => Some(half(half(x)?)? * 10), 8))\n"
        "    let total: (str, str) -> Result<int, str> = (a: str, b: str) => Ok(parse(a)? + parse(b)?)\n"
        "    print(match total(\"ab\", \"cde\") { Ok(n) => n, Err(e) => -1 })\n"
        "    print(match total(\"ab\", \"\") { Ok(n) => n, Err(e) => -1 })\n}\n"
    ),
    # MYLA-29: floats beyond examples/floats.my (also run through the
    # self-hosted compiler)
    "floats_in_depth": (
        "struct P { x: float64, y: float32 }\n"
        "const SCALE: float64 = 2.5f64\n"
        "fun hyp(p: P) -> float64 {\n    return p.x * p.x + (p.y as float64) * (p.y as float64)\n}\n"
        "#main\nfun main() {\n"
        "    let a = 0.1f32 * 3.0f32\n"            # float32 rounding after each op
        "    print(a)\n"
        "    print(1.0f32 / 3.0f32)\n"
        "    print(16777217.0f32)\n"               # rounds to 16777216
        "    let nan = 0.0f64 / 0.0f64\n"
        "    print(nan < 1.0f64)\n    print(nan <= 1.0f64)\n    print(nan > 1.0f64)\n"
        "    print(nan >= 1.0f64)\n    print(nan == nan)\n    print(nan != nan)\n"
        "    print(-7.5f64 % 2.0f64)\n"            # fmod keeps the dividend's sign
        "    print(-0.0f64)\n    print(0.0f64 * -1.0f64)\n"
        "    print(-1.0f64 / 0.0f64)\n    print(nan)\n"
        "    print(-3.9f64 as int32)\n"            # truncates toward zero
        "    print(300.7f64 as uint8)\n"           # then wraps
        "    let umax = 18446744073709551615u64\n"
        "    print(umax as float64)\n"
        "    print(9007199254740993i64 as float64)\n" # an int64 above 2^53
        "    print((1.5f64 as float32) + 0.1f32)\n"
        "    print(1e300f64 * 1e10f64)\n"
        "    print(5e-324f64)\n    print(1.7976931348623157e308f64)\n"
        "    print(1e-290f64)\n    print(3e300f64)\n    print(3.690843807971407e-302f64)\n"
        "    print(SCALE * 4.0f64)\n"
        "    let p = P { x: 3.0f64, y: 4.0f32 }\n"
        "    print(hyp(p))\n"
        "    var xs: [float64] = [0.5f64, 1.25f64]\n"
        "    push(xs, -2.0f64)\n"
        "    var total = 0.0f64\n"
        "    for x in xs { total = total + x }\n"
        "    print(total)\n"
        "    var m: [int: float32] = [1: 0.5f32]\n"
        "    m[2] = m[1] * 3.0f32\n"
        "    print(m[2])\n"
        "    print(format(\"{} and {}\", 2.5f64, 0.1f32))\n"
        "    let c = 'z'\n"
        "    print(f\"x={p.x} c={c} q={1.0f64 / 8.0f64}\")\n"
        "    print(2.0f64 < 3.0f64 && 3.0f32 >= 3.0f32)\n}\n"
    ),
    # MYLA-22: a closure environment owns its captures (and a composition or
    # partial application its parts): they outlive the variables they came from.
    "closure_environments_own_their_captures": (
        "enum Tree { Leaf(int), Node(Tree, Tree) }\n"
        "fun count(t: Tree) -> int {\n"
        "    return match t {\n"
        "        Leaf(n) => n\n        Node(a, b) => count(a) + count(b)\n    }\n}\n"
        "fun make_adder(xs: [int]) -> (int) -> int {\n"
        "    let k = len(xs)\n"
        "    return (i: int) => xs[i] + k\n}\n"
        "fun pick(xs: [int], i: int) -> int {\n    return xs[i]\n}\n"
        "fun double(x: int) -> int {\n    return x * 2\n}\n"
        "fun churn() {\n"                       # reuses freed cells, if any
        "    var big: [[int]] = []\n"
        "    for i in 0..50 { push(big, [i, i, i, i, i, i]) }\n}\n"
        "#main\nfun main() {\n"
        "    var f = make_adder([10, 20, 30])\n"
        "    churn()\n"
        "    print(f(1))\n"
        "    var ys = [1, 2, 3]\n"
        "    let g = (i: int) => ys[i]\n"
        "    ys = [7]\n"
        "    churn()\n"
        "    print(g(2))\n"
        "    var fs: [(int) -> int] = []\n"
        "    push(fs, make_adder([4, 5]))\n"
        "    churn()\n"
        "    print(fs[0](0))\n"
        "    let h = make_adder([1, 1]) >> double\n"
        "    churn()\n"
        "    print(h(0))\n"
        "    var zs = [6, 7, 8]\n"
        "    let p = pick(zs, _)\n"
        "    zs = []\n"
        "    churn()\n"
        "    print(p(2))\n"
        "    let t = Tree.Node(Tree.Leaf(1), Tree.Leaf(2))\n"
        "    let k = 40\n"
        "    let c = (x: int) => count(t) + k + x\n"   # a recursive enum capture is stored inline
        "    churn()\n"
        "    print(c(100))\n"
        "    for r in 0..20000 {\n"           # environments are reclaimed
        "        let q = make_adder([r, r, r])\n"
        "        if r == 19999 { print(q(0)) }\n    }\n}\n"
    ),
    # MYLA-21: destructuring reads a boxed (recursive) enum leaf through its
    # pointer, and the leaves own their heap values.
    "destructure_boxed_enum_and_list_leaves": (
        "enum V { VI(int), VP(V), VU }\n"
        "fun pair() -> (V, int) {\n    return (V.VI(5), 1)\n}\n"
        "fun nested() -> ((V, [int]), str) {\n"
        "    return ((V.VP(V.VI(2)), [1, 2, 3]), \"s\")\n}\n"
        "fun show(v: V) -> int {\n"
        "    return match v {\n"
        "        VI(n) => n\n        VP(w) => 10 + show(w)\n        VU => 0\n    }\n}\n"
        "#main\nfun main() {\n"
        "    let (a, b) = pair()\n"
        "    print(show(a))\n    print(b)\n"
        "    let ((c, xs), s) = nested()\n"
        "    print(show(c))\n    print(len(xs))\n    print(s)\n"
        "    var keep: [[int]] = []\n"
        "    for i in 0..3 {\n"
        "        let (v, n) = (V.VI(i), [i, i])\n"
        "        push(keep, n)\n"
        "        print(show(v))\n    }\n"
        "    print(len(keep[2]))\n}\n"
    ),
    "try_in_an_expression_lambda_returns_from_the_lambda": (
        # the interpreter let the `?` escape the lambda and return from its
        # caller (found with MYLA-10)
        "fun half(x: int) -> Option<int> {\n"
        "    if x % 2 == 1 { return None }\n    return Some(x / 2)\n}\n"
        "fun twice(f: (int) -> Option<int>, x: int) -> int {\n"
        "    let r = match f(x) { Some(v) => v, None => -1 }\n"
        "    print(r)\n    return r\n}\n"
        "fun run() -> Option<int> {\n"
        "    let g: (int) -> Option<int> = (x: int) => Some(half(x)? + 100)\n"
        "    print(twice(g, 4))\n    print(twice(g, 3))\n    return Some(7)\n}\n"
        "#main\nfun main() {\n"
        "    match run() { Some(v) => print(v), None => print(0) }\n}\n"
    ),
    # MYLA-2: a match binding is a value: writing to the scrutinee's variable
    # in an arm must not change (or free) what the binding sees.
    "match_binding_survives_writes_to_the_scrutinee": (
        "struct Bag { items: [int], name: str }\n"
        "enum Box { Full([int]), Empty }\n"
        "fun churn() {\n"                       # reuses freed cells, if any
        "    var big: [[int]] = []\n"
        "    for i in 0..50 { push(big, [i, i, i, i]) }\n}\n"
        "#main\nfun main() {\n"
        "    var xs = [1]\n"
        "    match xs {\n"
        "        ys => {\n"
        "            push(xs, 2)\n            push(xs, 3)\n"
        "            push(xs, 4)\n            push(xs, 5)\n"
        "            churn()\n"
        "            print(len(ys))\n"
        "            print(ys[0])\n        }\n    }\n"
        "    var b = Bag { items: [1, 2], name: \"b\" }\n"
        "    match b {\n"
        "        Bag { items, name } => {\n"
        "            b.items = [9]\n"
        "            churn()\n"
        "            print(len(items))\n"
        "            print(items[1])\n        }\n    }\n"
        "    var m: [int: int] = [1: 10]\n"
        "    match m {\n"
        "        mm => {\n"
        "            m[2] = 20\n            m[3] = 30\n"
        "            m[4] = 40\n            m[5] = 50\n            m[6] = 60\n"
        "            churn()\n"
        "            print(len(mm))\n        }\n    }\n"
        "    var bx = Box.Full([7, 7, 7])\n"
        "    match bx {\n"
        "        Full(vs) => {\n"
        "            bx = Box.Empty\n"
        "            churn()\n"
        "            print(len(vs))\n        },\n"
        "        Empty => print(0),\n    }\n"
        "    print(len(xs))\n}\n"
    ),
    # MYLA-3: a heap-owning aggregate can be assigned to any place; the new
    # value is taken before the old one is released.
    "assign_heap_owning_struct_to_any_place": (
        "struct Inner { xs: [int] }\n"
        "struct Outer { inner: Inner, tag: int }\n"
        "struct Deep { outer: Outer }\n"
        "#main\nfun main() {\n"
        "    var o = Outer { inner: Inner { xs: [1] }, tag: 1 }\n"
        "    o.inner = Inner { xs: [2, 3] }\n"
        "    print(len(o.inner.xs))\n"
        "    var d = Deep { outer: o }\n"
        "    d.outer.inner = Inner { xs: [4, 5, 6] }\n"
        "    print(len(d.outer.inner.xs))\n"
        "    print(len(o.inner.xs))\n"          # value semantics: still 2
        "    var os = [o, o]\n"
        "    os[1].inner = Inner { xs: [7, 7, 7, 7] }\n"
        "    print(len(os[0].inner.xs))\n"
        "    print(len(os[1].inner.xs))\n"
        "    var m: [int: Outer] = [1: o]\n"
        "    m[1].inner = Inner { xs: [8] }\n"
        "    print(len(m[1].inner.xs))\n"
        "    print(len(o.inner.xs))\n}\n"
    ),
    "assign_to_a_field_of_a_shared_element_copies_it": (
        # value semantics: writing a field through a list element or map value
        # unshares the container first (the native code wrote into the cell
        # both variables shared)
        "struct P { x: int, ys: [int] }\n"
        "struct W { p: P }\n"
        "#main\nfun main() {\n"
        "    var a = [P { x: 1, ys: [1] }]\n"
        "    var b = a\n"
        "    b[0].x = 5\n"
        "    print(a[0].x)\n"
        "    print(b[0].x)\n"
        "    b[0].ys = [4, 4]\n"
        "    print(len(a[0].ys))\n"
        "    var m: [int: P] = [1: P { x: 1, ys: [] }]\n"
        "    var m2 = m\n"
        "    m2[1].x = 7\n"
        "    print(m[1].x)\n"
        "    var ws = [W { p: P { x: 1, ys: [] } }]\n"
        "    var ws2 = ws\n"
        "    ws2[0].p.x = 9\n"
        "    print(ws[0].p.x)\n"
        "    print(ws2[0].p.x)\n}\n"
    ),
    "borrowed_lets_survive_a_moved_value": (
        # MYLA-127: a value something borrows (a `let` of it, a loop over it,
        # a match on it) isn't moved out of its variable by its last use: the
        # borrower may still read it after the new owner lets it go
        "fun churn() {\n"                       # reuses freed cells, if any
        "    var big: [str] = []\n"
        "    for i in 0..50 { push(big, f\"cell {i}\") }\n}\n"
        "fun lets() {\n"
        "    let s = \"a\" + \"b\"\n"
        "    let n = s\n"
        "    var t = s\n"
        "    t = \"z\"\n"
        "    churn()\n"
        "    print(n)\n"
        "    print(t)\n}\n"
        "fun loops() {\n"
        "    let xs = [\"c\" + \"d\"]\n"
        "    for x in xs {\n"
        "        var ys = xs\n"
        "        ys = []\n"
        "        churn()\n"
        "        print(x)\n"
        "    }\n}\n"
        "#main\nfun main() {\n"
        "    lets()\n"
        "    loops()\n}\n"
    ),
    "become_keeps_the_stack_flat": (
        # MYLA-128, D87: `become` calls in constant stack: direct, mutual,
        # a method, a `var self` method, through a function value (a field
        # holding a function, a lambda, a parameter, a partial application),
        # with an aggregate result, more and fewer argument words, heap values
        # handed over or passed on, a generic callee, no result
        "struct Pair { a: int, b: int }\n"
        "struct Counter { step: int }\n"
        "struct Machine { step: int, next: (Machine, int, int) -> int }\n"
        "struct Walker { pos: int, steps: int }\n"
        "\n"
        "fun count(n: int, acc: int) -> int {\n"
        "    if n == 0 { return acc }\n"
        "    become count(n - 1, acc + n)\n"
        "}\n"
        "\n"
        "fun is_even(n: int) -> bool {\n"
        "    if n == 0 { return true }\n"
        "    become is_odd(n - 1)\n"
        "}\n"
        "\n"
        "fun is_odd(n: int) -> bool {\n"
        "    if n == 0 { return false }\n"
        "    become is_even(n - 1)\n"
        "}\n"
        "\n"
        "impl Counter {\n"
        "    fun run(self, n: int, acc: int) -> int {\n"
        "        if n == 0 { return acc }\n"
        "        become self.run(n - 1, acc + self.step)\n"
        "    }\n"
        "}\n"
        "\n"
        "impl Walker {\n"
        "    fun walk(var self, n: int) {\n"
        "        if n == 0 { return }\n"
        "        self.pos = self.pos + 2\n"
        "        self.steps = self.steps + 1\n"
        "        become self.walk(n - 1)\n"
        "    }\n"
        "}\n"
        "\n"
        "fun spin(m: Machine, n: int, acc: int) -> int {\n"
        "    if n == 0 { return acc }\n"
        "    become m.next(m, n - 1, acc + m.step)\n"
        "}\n"
        "\n"
        "fun fib(n: int, a: int, b: int) -> Pair {\n"
        "    if n == 0 { return Pair { a: a, b: b } }\n"
        "    become fib(n - 1, b, (a + b) % 1000003)\n"
        "}\n"
        "\n"
        "fun spread(n: int, a: int) -> int {\n"
        "    if n == 0 { return a }\n"
        "    become gather(n - 1, a, n % 3, 1)\n"
        "}\n"
        "\n"
        "fun gather(n: int, a: int, b: int, c: int) -> int {\n"
        "    become spread(n, (a + b * c) % 1000003)\n"
        "}\n"
        "\n"
        "fun total(xs: [int], i: int, acc: int) -> int {\n"
        "    if i == len(xs) { return acc }\n"
        "    become total(xs, i + 1, acc + xs[i])\n"
        "}\n"
        "\n"
        "fun via(g: ([int], int, int) -> int, xs: [int]) -> int {\n"
        "    become g(xs, 0, 0)\n"
        "}\n"
        "\n"
        "fun label(n: int, s: str) -> str {\n"
        "    if n == 0 { return s }\n"
        "    become label(n - 1, s + \".\")\n"
        "}\n"
        "\n"
        "fun last<T>(xs: [T], i: int) -> T {\n"
        "    if i + 1 == len(xs) { return xs[i] }\n"
        "    become last(xs, i + 1)\n"
        "}\n"
        "\n"
        "fun relay<T>(x: T, n: int) -> T {\n"
        "    if n == 0 { return x }\n"
        "    become relay(x, n - 1)\n"
        "}\n"
        "\n"
        "fun pick(p: Pair, n: int) -> int {\n"
        "    if n == 0 { return p.a * 10 + p.b }\n"
        "    become pick(p, n - 1)\n"
        "}\n"
        "\n"
        "fun apply2(g: (int, int) -> int, a: int, b: int) -> int {\n"
        "    become g(a, b)\n"
        "}\n"
        "\n"
        "fun add3(a: int, b: int, c: int) -> int {\n"
        "    return a * 100 + b * 10 + c\n"
        "}\n"
        "\n"
        "fun shout(n: int) {\n"
        "    if n == 0 {\n"
        "        print(\"done\")\n"
        "        return\n"
        "    }\n"
        "    become shout(n - 1)\n"
        "}\n"
        "\n"
        "#main\n"
        "fun main() {\n"
        "    let deep = 20000\n"
        "    print(count(deep, 0))\n"
        "    print(is_even(deep))\n"
        "    print(is_odd(deep + 1))\n"
        "    print(Counter { step: 3 }.run(deep, 0))\n"
        "    var w = Walker { pos: 0, steps: 0 }\n"
        "    w.walk(deep)\n"
        "    print(w.pos + w.steps)\n"
        "    print(spin(Machine { step: 2, next: spin }, deep, 0))\n"
        "    let near = Machine { step: 1, next: (m: Machine, n: int, acc: int) => spin(m, n, acc * 2 % 1000003) }\n"
        "    print(spin(near, 50, 1))\n"
        "    let p = fib(deep, 0, 1)\n"
        "    print(p.a)\n"
        "    print(p.b)\n"
        "    print(spread(deep, 0))\n"
        "    var xs: [int] = []\n"
        "    for i in 0..1000 { push(xs, i % 7) }\n"
        "    print(total(xs, 0, 0))\n"
        "    print(via(total, xs))\n"
        "    print(len(label(1000, \"\")))\n"
        "    print(last([\"a\", \"b\", \"c\"], 0))\n"
        "    print(relay(\"ab\" + \"c\", deep))\n"
        "    print(pick(Pair { a: 4, b: 2 }, deep))\n"
        "    print(apply2(add3(7, _, _), 8, 9))\n"
        "    shout(deep)\n"
        "}\n"
    ),
    "method_arguments_survive_the_receivers_writes": (
        # MYLA-123: an argument read from the receiver of a `var self` method
        # is a copy taken before the call, which the method's writes to its
        # receiver neither change nor release
        "struct B { name: str, xs: [int] }\n"
        "impl B {\n"
        "    fun rename(var self, n: str) {\n"
        "        self.name = \"zz\" + \"yy\"\n"
        "        churn()\n"
        "        print(n)\n"
        "    }\n"
        "    fun swap(var self, other: B) {\n"
        "        self.name = \"q\" + \"r\"\n"
        "        self.xs = [9]\n"
        "        churn()\n"
        "        print(other.name)\n"
        "        print(len(other.xs))\n"
        "    }\n"
        "    fun keep(var self, xs: [int]) {\n"
        "        push(self.xs, 5)\n"
        "        print(len(xs))\n"
        "    }\n"
        "}\n"
        "fun churn() {\n"                       # reuses freed cells, if any
        "    var big: [str] = []\n"
        "    for i in 0..50 { push(big, f\"cell {i}\") }\n}\n"
        "#main\nfun main() {\n"
        "    var b = B { name: \"a\" + \"b\", xs: [1, 2] }\n"
        "    b.rename(b.name)\n"
        "    b.swap(b)\n"
        "    b.keep(b.xs)\n"
        "    print(b.name)\n"
        "    print(len(b.xs))\n"
        "    var bs = [B { name: \"c\" + \"d\", xs: [] }]\n"
        "    bs[0].rename(bs[0].name)\n}\n"
    ),
    "assign_heap_owning_struct_to_itself": (
        "struct Inner { xs: [int] }\n"
        "struct Outer { inner: Inner }\n"
        "fun churn() {\n"                       # reuses freed cells, if any
        "    var big: [[int]] = []\n"
        "    for i in 0..50 { push(big, [i, i, i, i]) }\n}\n"
        "#main\nfun main() {\n"
        "    var p = Inner { xs: [9, 9, 9] }\n"
        "    p = p\n"
        "    churn()\n"
        "    print(len(p.xs))\n"
        "    var o = Outer { inner: Inner { xs: [1, 2] } }\n"
        "    o.inner = o.inner\n"
        "    churn()\n"
        "    print(len(o.inner.xs))\n}\n"
    ),
    "assign_replaces_map_and_builder_elements": (
        # replacing an element releases the old one with its own type's drop
        # routine (the native compiler used to assume every element was a list)
        "struct P { tags: [int] }\n"
        "#main\nfun main() {\n"
        "    var ms: [[int: int]] = [[1: 2]]\n"
        "    ms[0] = [3: 4, 5: 6]\n"
        "    print(len(ms[0]))\n"
        "    var bs = [StringBuilder()]\n"
        "    bs[0] = StringBuilder()\n"
        "    append(bs[0], \"hi\")\n"
        "    print(build(bs[0]))\n"
        # the new value is taken before the old one is released, so a struct
        # assigned to its own slot keeps its list alive
        "    var ps = [P { tags: [7, 8] }]\n"
        "    ps[0] = ps[0]\n"
        "    var big: [int] = []\n"
        "    for i in 0..64 { push(big, i) }\n"   # reuses a freed cell, if any
        "    print(len(ps[0].tags))\n"
        "    print(ps[0].tags[1])\n}\n"
    ),
    # const references fold to the referenced value; unary operators fold (MYLA-27)
    "consts_fold_through_references": (
        'const A: int = 4\n'
        'const B: int = 100 / A\n'
        'const C: int = -A\n'
        'const D: int = ~A\n'
        'const E: bool = !(A > 3)\n'
        'const F: int = B - C\n'
        'const G: uint8 = 200\n'
        'const H: uint8 = G + G\n'
        '#main\n'
        'fun main() {\n'
        '    print(B)\n'
        '    print(C)\n'
        '    print(D)\n'
        '    print(E)\n'
        '    print(F)\n'
        '    print(H)\n'
        '}\n'
    ),
    # operands, arguments and literal elements evaluate left to right; an
    # assignment evaluates its value first, then the place (MYLA-8)
    "evaluation_order_is_left_to_right": (
        "#derive(Eq)\n"
        "struct P { x: int, y: int }\n"
        "\n"
        "enum E { A(int, int), B(str, P) }\n"
        "\n"
        "struct Ctr { n: int }\n"
        "\n"
        "impl Ctr {\n"
        "    fun add(self, a: int, b: int) -> int {\n"
        "        return self.n + a + b\n"
        "    }\n"
        "    fun bump(var self, a: int) -> int {\n"
        "        self.n = self.n + a\n"
        "        return self.n\n"
        "    }\n"
        "}\n"
        "\n"
        "impl Add for P {\n"
        "    fun add(self, o: P) -> P {\n"
        "        return P { x: self.x + o.x, y: self.y + o.y }\n"
        "    }\n"
        "}\n"
        "\n"
        "fun f(x: int) -> int {\n"
        "    print(x)\n"
        "    return x\n"
        "}\n"
        "\n"
        "fun s(x: str) -> str {\n"
        "    print(x)\n"
        "    return x\n"
        "}\n"
        "\n"
        "fun fl(x: float64) -> float64 {\n"
        "    print(x)\n"
        "    return x\n"
        "}\n"
        "\n"
        "fun pt(x: int) -> P {\n"
        "    print(x)\n"
        "    return P { x: x, y: x }\n"
        "}\n"
        "\n"
        "fun lst(x: int) -> [int] {\n"
        "    print(x)\n"
        "    return [10, 20, 30, 40]\n"
        "}\n"
        "\n"
        "fun mp(x: int) -> [str: int] {\n"
        "    print(x)\n"
        "    return [\"a\": 1, \"b\": 2]\n"
        "}\n"
        "\n"
        "fun ctr(x: int) -> Ctr {\n"
        "    print(x)\n"
        "    return Ctr { n: x }\n"
        "}\n"
        "\n"
        "fun g(a: int, b: int) -> int {\n"
        "    return a + b\n"
        "}\n"
        "\n"
        "fun g3(a: int, b: P, c: int) -> P {\n"
        "    return P { x: a + b.x, y: c + b.y }\n"
        "}\n"
        "\n"
        "fun pick(x: int) -> (int, int) -> int {\n"
        "    print(x)\n"
        "    return (a: int, b: int) => a - b\n"
        "}\n"
        "\n"
        "fun id<T>(a: T, b: T) -> T {\n"
        "    return a\n"
        "}\n"
        "\n"
        "#main\n"
        "fun main() {\n"
        "    print(\"-- binary\")\n"
        "    let a = f(1) - f(2)\n"
        "    let b = f(3) * f(4) + f(5) / f(6)\n"
        "    let c = f(7) < f(8)\n"
        "    let d = f(9) == f(10)\n"
        "    let e = s(\"s1\") + s(\"s2\")\n"
        "    let e2 = s(\"s3\") == s(\"s4\")\n"
        "    let h = fl(1.5f64) - fl(2.5f64)\n"
        "    let h2 = fl(3.5f64) < fl(4.5f64)\n"
        "    let i = pt(11) == pt(12)\n"
        "    let j = pt(13) + pt(14)\n"
        "    let k = f(15) << f(1)\n"
        "    let k2 = f(16) & f(17)\n"
        "    print(\"-- calls\")\n"
        "    let l = g(f(18), f(19))\n"
        "    let m = g3(f(20), pt(21), f(22))\n"
        "    let n = id(f(23), f(24))\n"
        "    let n2 = id(pt(25), pt(26))\n"
        "    print(\"-- methods\")\n"
        "    let o = ctr(27).add(f(28), f(29))\n"
        "    var cc = Ctr { n: 0 }\n"
        "    let o2 = cc.bump(f(30)) + cc.bump(f(31))\n"
        "    print(\"-- literals\")\n"
        "    let q = P { x: f(32), y: f(33) }\n"
        "    let q2 = P { y: f(34), x: f(35) }\n"
        "    let r = [f(36), f(37), f(38)]\n"
        "    let t = (f(39), s(\"s5\"), pt(40))\n"
        "    let u = [s(\"k1\"): f(41), s(\"k2\"): f(42)]\n"
        "    let v = E.A(f(43), f(44))\n"
        "    let v2 = E.B(s(\"s6\"), pt(45))\n"
        "    print(\"-- index\")\n"
        "    let w = lst(46)[f(1)]\n"
        "    let w2 = mp(47)[s(\"a\")]\n"
        "    let w3 = s(\"hello\")[f(2)]\n"
        "    print(\"-- format\")\n"
        "    let x = format(\"{} {}\", f(48), s(\"s7\"))\n"
        "    let x2 = f\"{f(49)} {s(\"s8\")}\"\n"
        "    print(\"-- closures\")\n"
        "    let y = pick(50)(f(51), f(52))\n"
        "    let fy = (p: int, q: int) => p * q\n"
        "    let y2 = fy(f(53), f(54))\n"
        "    let p55 = f(55)\n"
        "    let part = g(p55, _)\n"
        "    let y3 = part(f(56))\n"
        "    let y4 = f(57) |> g(f(58))\n"
        "    print(\"-- assign\")\n"
        "    var xs = [0, 0, 0]\n"
        "    xs[f(1)] = f(59)\n"
        "    var ms = [\"a\": 0]\n"
        "    ms[s(\"b\")] = f(60)\n"
        "    var pp = P { x: 0, y: 0 }\n"
        "    pp.x = f(61)\n"
        "    print(\"-- builtins\")\n"
        "    push(xs, f(62))\n"
        "    let z = contains(ms, s(\"s9\"))\n"
        "    var sb = StringBuilder()\n"
        "    append(sb, s(\"s10\"))\n"
        "    for ii in f(63)..f(65) {\n"
        "        print(ii)\n"
        "    }\n"
        "    print(\"-- done\")\n"
        "    print(a + b + l + o + o2 + n + w + w2 + y + y2 + y3 + y4 + k + k2)\n"
        "    print(m.x + n2.x + j.x + q.x + q2.y + r[0] + t.0 + u[\"k1\"] + pp.x)\n"
        "    print(c && d && e2 && h2 && i && z)\n"
        "    print(e + x + x2 + build(sb))\n"
        "    print(h)\n"
        "    print(w3)\n"
        "    match v {\n"
        "        A(p1, p2) => print(p1 + p2),\n"
        "        _ => {},\n"
        "    }\n"
        "    match v2 {\n"
        "        B(p1, p2) => print(p1),\n"
        "        _ => {},\n"
        "    }\n"
        "}\n"
    ),
    # a partial application evaluates its callee, receiver and filled
    # arguments once, when it is made (D51, D60, MYLA-75)
    "partial_application_evaluates_its_arguments_once": (
        "struct Ctr { n: int }\n"
        "\n"
        "impl Ctr {\n"
        "    fun add(self, a: int, b: int) -> int {\n"
        "        return self.n + a + b\n"
        "    }\n"
        "}\n"
        "\n"
        "fun f(x: int) -> int {\n"
        "    print(x)\n"
        "    return x\n"
        "}\n"
        "\n"
        "fun g(a: int, b: int, c: int) -> int {\n"
        "    return a * 100 + b * 10 + c\n"
        "}\n"
        "\n"
        "fun ctr(n: int) -> Ctr {\n"
        "    print(n)\n"
        "    return Ctr { n: n }\n"
        "}\n"
        "\n"
        "fun pick(n: int) -> (int, int) -> int {\n"
        "    print(n)\n"
        "    return (a: int, b: int) => a - b\n"
        "}\n"
        "\n"
        "#main\n"
        "fun main() {\n"
        "    let p = g(f(1), _, f(2))\n"
        "    print(\"made\")\n"
        "    print(p(f(3)))\n"
        "    print(p(f(4)))\n"
        "    let m = ctr(5).add(f(6), _)\n"
        "    print(\"made\")\n"
        "    print(m(f(7)))\n"
        "    print(m(f(8)))\n"
        "    let fv = pick(9)\n"
        "    let q = fv(_, f(10))\n"
        "    print(\"made\")\n"
        "    print(q(f(11)))\n"
        "    var x = 1\n"
        "    let r = g(x, _, 3)\n"
        "    x = 2\n"
        "    print(r(0))\n"
        "    let lit = g(1, _, 2)\n"
        "    print(lit(5))\n"
        "}\n"
    ),
    # #derive(Eq) on char and float fields compares like `==`: NaN is not
    # equal to itself, 0.0 equals -0.0 (MYLA-13)
    "derived_eq_on_char_and_float_fields": (
        "#derive(Eq)\n"
        "struct P { c: char, f: float64, g: float }\n"
        "\n"
        "#derive(Eq)\n"
        "enum E { A(char), B(float64), N }\n"
        "\n"
        "#main\n"
        "fun main() {\n"
        "    let z: float64 = 0.0\n"
        "    let nan = z / z\n"
        "    let a = P { c: 'x', f: 1.5f64, g: 2.5 }\n"
        "    print(a == P { c: 'x', f: 1.5f64, g: 2.5 })\n"
        "    print(a == P { c: 'y', f: 1.5f64, g: 2.5 })\n"
        "    print(a != P { c: 'x', f: 1.25f64, g: 2.5 })\n"
        "    print(P { c: 'x', f: nan, g: 0.0 } == P { c: 'x', f: nan, g: 0.0 })\n"
        "    print(P { c: 'x', f: 0.0, g: 0.0 } == P { c: 'x', f: -z, g: -0.0 })\n"
        "    print(E.A('\\u{1F600}') == E.A('\\u{1F600}'))\n"
        "    print(E.B(nan) == E.B(nan))\n"
        "    print(E.B(-z) == E.B(z))\n"
        "    print(E.A('a') == E.N)\n"
        "}\n"
    ),
    # a statement match's arms need no value, so an arm block may end in a
    # match statement (MYLA-59)
    "match_statement_ending_an_arm_block": (
        "enum Shape { Dot, Box(int, int) }\n"
        "\n"
        "fun describe(s: Shape, verbose: bool) {\n"
        "    match s {\n"
        "        Dot => {\n"
        "            print(\"dot\")\n"
        "            match verbose {\n"
        "                true => print(\"  a point\")\n"
        "                false => {}\n"
        "            }\n"
        "        }\n"
        "        Box(w, h) => match w == h {\n"
        "            true => print(\"square\")\n"
        "            false => {\n"
        "                print(\"box\")\n"
        "                match h {\n"
        "                    0 => print(\"  flat\")\n"
        "                    _ => print(w * h)\n"
        "                }\n"
        "            }\n"
        "        }\n"
        "    }\n"
        "}\n"
        "\n"
        "#main\n"
        "fun main() {\n"
        "    let r: Result<int, str> = Ok(1)\n"
        "    match r {\n"
        "        Ok(n) => {\n"
        "            print(n)\n"
        "            match n {\n"
        "                1 => print(\"one\")\n"
        "                _ => print(\"other\")\n"
        "            }\n"
        "        }\n"
        "        Err(e) => print(e)\n"
        "    }\n"
        "    describe(Shape.Dot, true)\n"
        "    describe(Shape.Box(2, 2), false)\n"
        "    describe(Shape.Box(2, 3), false)\n"
        "    describe(Shape.Box(4, 0), false)\n"
        "    let v = match r {\n"
        "        Ok(n) => {\n"
        "            match n {\n"
        "                1 => print(\"still a value\")\n"
        "                _ => {}\n"
        "            }\n"
        "            n * 10\n"
        "        }\n"
        "        Err(e) => 0\n"
        "    }\n"
        "    print(v)\n"
        "}\n"
    ),
    # instantiations with type arguments that share a mangled spelling, or
    # that differ only in function types, are distinct (MYLA-9, MYLA-33)
    "generic_instantiations_get_distinct_names": (
        "struct A_B { v: int }\n"
        "struct C { v: int }\n"
        "struct A { s: str, v: int }\n"
        "struct B_C { v: int }\n"
        "struct Pair<X, Y> { x: X, y: Y }\n"
        "\n"
        "fun first<X, Y>(p: Pair<X, Y>) -> X {\n"
        "    return p.x\n"
        "}\n"
        "\n"
        "fun ident<T>(x: T) -> T {\n"
        "    return x\n"
        "}\n"
        "\n"
        "fun call<T>(f: T, describe: str) -> str {\n"
        "    return describe\n"
        "}\n"
        "\n"
        "#main\n"
        "fun main() {\n"
        "    let p1 = Pair { x: A_B { v: 1 }, y: C { v: 2 } }\n"
        "    let p2 = Pair { x: A { s: \"three\", v: 3 }, y: B_C { v: 4 } }\n"
        "    print(first(p1).v + first(p2).v)\n"
        "    let inc = ident((a: int) => a + 1)\n"
        "    let size = ident((s: str) => len(s))\n"
        "    print(inc(41))\n"
        "    print(size(\"four\"))\n"
        "    print(call((a: int) => a, \"int to int\"))\n"
        "    print(call((s: str) => s, \"str to str\"))\n"
        "    let t1 = ident((1, A_B { v: 5 }))\n"
        "    let t2 = ident((A { s: \"six\", v: 6 }, 2))\n"
        "    print(t1.1.v + t2.0.v)\n"
        "}\n"
    ),
    # float -> integer casts saturate, NaN gives 0 (D59, MYLA-6)
    "float_to_int_casts_saturate": (
        "const BIG: float64 = 1e19\n"
        "const CA: uint64 = BIG as uint64\n"
        "const CB: int16 = (0.0f64 / 0.0f64) as int16\n"
        "fun to_u64(x: float64) -> uint64 {\n    return x as uint64\n}\n"
        "fun to_i64(x: float64) -> int64 {\n    return x as int64\n}\n"
        "fun to_i32(x: float64) -> int32 {\n    return x as int32\n}\n"
        "fun to_u32(x: float64) -> uint32 {\n    return x as uint32\n}\n"
        "fun to_u8(x: float64) -> uint8 {\n    return x as uint8\n}\n"
        "fun to_i8(x: float64) -> int8 {\n    return x as int8\n}\n"
        "#main\nfun main() {\n"
        "    let z: float64 = 0.0\n"
        "    let xs: [float64] = [z / z, 1.0f64 / z, -1.0f64 / z, 0.0, -0.0, 0.9, -0.9, 1.5, -1.5,"
        " 2.9, -2.9, 127.9, 128.0, -128.9, -129.0, 255.9, 256.0, 300.0, -300.0,"
        " 2147483647.5, 2147483648.0, -2147483648.9, -2147483649.0, 4294967295.5, 4294967296.0,"
        " 9223372036854775807.0, -9223372036854775808.0, -1e19, 1e19, 1.8e19,"
        " 18446744073709549568.0, 18446744073709551616.0, 3e19]\n"
        "    for x in xs {\n"
        "        print(f\"{to_u64(x)} {to_i64(x)} {to_i32(x)} {to_u32(x)} {to_u8(x)} {to_i8(x)}\")\n"
        "    }\n"
        "    let f: float32 = 3e9\n"
        "    print(f as int32)\n    print(f as uint32)\n"
        "    let n: float32 = 0.0 / 0.0\n    print(n as uint64)\n"
        "    print(CA)\n    print(CB)\n"
        "}\n"
    ),
    # the int64 minimum divided by -1 wraps instead of trapping (MYLA-5)
    "int64_min_divided_by_minus_one": (
        'const MIN: int64 = -9223372036854775807 - 1\n'
        'const Q: int64 = MIN / -1\n'
        'const R: int64 = MIN % -1\n'
        'fun div(a: int64, b: int64) -> int64 {\n'
        '    return a / b\n'
        '}\n'
        'fun rem(a: int64, b: int64) -> int64 {\n'
        '    return a % b\n'
        '}\n'
        '#main\n'
        'fun main() {\n'
        '    let a: int64 = -9223372036854775807 - 1\n'
        '    var b: int64 = -1\n'
        '    print(a / b)\n'
        '    print(a % b)\n'
        '    print(div(a, -1))\n'
        '    print(rem(a, -1))\n'
        '    print(div(-7, -1))\n'
        '    print(rem(-7, -1))\n'
        '    print(div(7, -2))\n'
        '    print(rem(7, -2))\n'
        '    let c: int32 = -2147483647 - 1\n'
        '    var d: int32 = -1\n'
        '    print(c / d)\n'
        '    print(c % d)\n'
        '    print(Q)\n'
        '    print(R)\n'
        '}\n'
    ),
    # integer literals of 2^63 and above (MYLA-73)
    "big_integer_literals": (
        '#main\n'
        'fun main() {\n'
        '    let max: uint64 = 18446744073709551615u64\n'
        '    print(max)\n'
        '    print(max >> 60)\n'
        '    let top: uint64 = 9223372036854775808\n'
        '    print(top)\n'
        '    print(top == (1u64 << 63))\n'
        '    let low: int64 = -9223372036854775808i64\n'
        '    print(low)\n'
        '    print(0xFFFF_FFFF_FFFF_FFFFu64 == max)\n'
        '    let x: uint64 = 12345678901234567890\n'
        '    print(x & 9223372036854775808u64)\n'
        '    print(x % 1000)\n'
        '    match max {\n'
        '        18446744073709551615 => { print("max") },\n'
        '        _ => { print("other") },\n'
        '    }\n'
        '}\n'
    ),
    # `remove` unshares the map first and drops the removed value (MYLA-25)
    "remove_leaves_map_copies_alone": (
        '#main\n'
        'fun main() {\n'
        '    var a = ["x": [1, 2], "y": [3]]\n'
        '    var b = a\n'
        '    remove(b, "x")\n'
        '    print(len(a))\n'
        '    print(contains(a, "x"))\n'
        '    print(len(b))\n'
        '    print(len(a["x"]))\n'
        '    var c = a\n'
        '    remove(c, "y")\n'
        '    remove(c, "nope")\n'
        '    print(len(c))\n'
        '    print(len(a))\n'
        '}\n'
    ),
    # partial application of functions, methods and function values with
    # aggregate results and arguments (MYLA-26)
    "partial_application_of_aggregates": (
        'struct P { x: int, y: int }\n'
        'struct H { f: (P, int) -> P }\n'
        'impl P {\n'
        '    fun moved(self, d: int, q: P) -> P {\n'
        '        return P { x: self.x + d + q.x, y: self.y + d + q.y }\n'
        '    }\n'
        '}\n'
        'fun mk(a: int, b: int) -> P {\n'
        '    return P { x: a, y: b }\n'
        '}\n'
        'fun shift(p: P, d: int) -> P {\n'
        '    return P { x: p.x + d, y: p.y + d }\n'
        '}\n'
        'fun pair(a: int, s: str) -> (int, str) {\n'
        '    return (a * 2, s)\n'
        '}\n'
        '#main\n'
        'fun main() {\n'
        '    let f = mk(3, _)\n'
        '    let p = f(5)\n'
        '    print(p.x)\n'
        '    print(p.y)\n'
        '    let g = shift(_, 10)\n'
        '    let q = g(P { x: 1, y: 2 })\n'
        '    print(q.x)\n'
        '    print(q.y)\n'
        '    let h = pair(_, "hi")\n'
        '    let t = h(21)\n'
        '    print(t.0)\n'
        '    print(t.1)\n'
        '    let base = P { x: 100, y: 200 }\n'
        '    let m = base.moved(_, P { x: 1, y: 1 })\n'
        '    let r = m(5)\n'
        '    print(r.x)\n'
        '    print(r.y)\n'
        '    let lam = (a: int, s: P) => P { x: a * s.x, y: a * s.y }\n'
        '    let twice = lam(2, _)\n'
        '    let u = twice(P { x: 3, y: 4 })\n'
        '    print(u.x)\n'
        '    print(u.y)\n'
        '    let holder = H { f: shift }\n'
        '    let viafield = holder.f(_, 7)\n'
        '    let w = viafield(P { x: 0, y: 1 })\n'
        '    print(w.x)\n'
        '    print(w.y)\n'
        '}\n'
    ),
    # `#derive(Eq)` compares boxed payloads structurally (MYLA-23)
    "derived_eq_on_recursive_enums": (
        '#derive(Eq)\n'
        'enum L { Nil, Cons(int, L) }\n'
        '#derive(Eq)\n'
        'enum T { Leaf(str), Node(T, T) }\n'
        '#main\n'
        'fun main() {\n'
        '    let a = L.Cons(1, L.Cons(2, L.Nil))\n'
        '    let b = L.Cons(1, L.Cons(2, L.Nil))\n'
        '    let c = L.Cons(1, L.Cons(3, L.Nil))\n'
        '    print(a == b)\n'
        '    print(a == c)\n'
        '    print(a != c)\n'
        '    let t1 = T.Node(T.Leaf("x"), T.Node(T.Leaf("y"), T.Leaf("z")))\n'
        '    let t2 = T.Node(T.Leaf("x"), T.Node(T.Leaf("y"), T.Leaf("z")))\n'
        '    let t3 = T.Node(T.Leaf("x"), T.Leaf("y"))\n'
        '    print(t1 == t2)\n'
        '    print(t1 == t3)\n'
        '}\n'
    ),
    "diverging_arm_of_an_aggregate_match": (
        # an arm ending in `panic`/`unreachable` has no value to store (the
        # native compiler used to look for its aggregate result and crash)
        "struct P { a: int, b: str }\n"
        "fun mk(ok: bool) -> Result<P, str> {\n"
        "    if ok { return Ok(P { a: 1, b: \"x\" }) }\n    return Err(\"no\")\n}\n"
        "fun block_arm(ok: bool) -> P {\n"
        "    return match mk(ok) {\n        Ok(p) => p,\n"
        "        Err(d) => { panic(\"cannot happen\") },\n    }\n}\n"
        "fun expr_arm(ok: bool) -> P {\n"
        "    return match mk(ok) {\n        Ok(p) => p,\n        Err(d) => unreachable(),\n    }\n}\n"
        "#main\nfun main() {\n"
        "    print(block_arm(true).b)\n    print(expr_arm(true).a)\n"
        "    let t = match mk(true) {\n        Ok(p) => (p.a, p.b),\n"
        "        Err(d) => { panic(d) },\n    }\n    print(t.1)\n}\n"
    ),
    "remove_many_distinct_keys": (
        # the self-hosted map left a tombstone per `remove` and counted only
        # occupied slots, so after enough distinct keys no slot was empty and
        # looking up a missing key never ended (MYLA-18)
        "#main\nfun main() {\n"
        "    var m: [int: int] = [:]\n    var r = 0\n"
        "    while r < 1000 {\n        m[r] = r\n"
        "        if len(m) > 5 {\n            for k in keys(m) {\n                remove(m, k)\n            }\n        }\n"
        "        r = r + 1\n    }\n"
        "    print(len(m))\n    print(contains(m, 3))\n    print(m[999])\n}\n"
    ),
    "pop_a_boxed_enum": (
        # a list of a recursive enum holds boxes; `pop` copies the value out of
        # the box and releases it (both compilers used to hand out the box
        # pointer itself, MYLA-74)
        "enum T {\n    Leaf(int),\n    Node(T, [T]),\n}\n"
        "fun show(t: T) -> str {\n"
        "    return match t {\n        T.Leaf(n) => f\"leaf {n}\",\n"
        "        T.Node(l, kids) => f\"node({show(l)}, {len(kids)} kids)\",\n    }\n}\n"
        "struct Stack { items: [T] }\n"
        "impl Stack {\n    fun take(var self) -> T {\n        return pop(self.items)\n    }\n}\n"
        "#main\nfun main() {\n"
        "    var xs: [T] = [T.Leaf(1), T.Node(T.Leaf(2), [T.Leaf(3)]), T.Leaf(4)]\n"
        "    let a = pop(xs)\n    print(show(a))\n"
        "    print(show(pop(xs)))\n"
        "    var s = Stack { items: xs }\n    print(show(s.take()))\n"
        "    print(len(s.items))\n    print(len(xs))\n}\n"
    ),
}

# A program that allocates far more recursive-enum cells (~12M) than the heap
# arena can hold at once. It only terminates without trapping if dropped cells
# are genuinely returned to the allocator's free list and reused.
STRESS_SRC = (
    "enum List { Cons(int, List), Nil }\n"
    "fun make(n: int) -> List {\n"
    "    var acc = List.Nil\n    var i = 0\n"
    "    while i < n {\n        acc = List.Cons(i, acc)\n        i = i + 1\n    }\n"
    "    return acc\n}\n"
    "fun sum(xs: List) -> int {\n"
    "    return match xs { List.Cons(h, t) => h + sum(t), List.Nil => 0 }\n}\n"
    "#main\nfun main() {\n"
    "    var total = 0\n    var k = 0\n"
    "    while k < 200000 {\n"
    "        let xs = make(60)\n        total = total + sum(xs)\n        k = k + 1\n"
    "    }\n    print(total)\n}\n"
)

# `?` early-returns out of `chain` with a live heap list (`xs`) still in scope on
# every iteration; that list must be dropped on the early return or the arena
# leaks. ~6M cells through a finite arena means a leak would trap.
STRESS_TRY_SRC = (
    "enum List { Cons(int, List), Nil }\n"
    "fun make(n: int) -> Result<List, str> {\n"
    "    if n < 0 {\n        return Err(\"neg\")\n    }\n"
    "    var acc: List = List.Nil\n    var i = 0\n"
    "    while i < n {\n        acc = List.Cons(i, acc)\n        i = i + 1\n    }\n"
    "    return Ok(acc)\n}\n"
    "fun chain(n: int) -> Result<int, str> {\n"
    "    let xs = make(n)?\n    let bad = make(-1)?\n    return Ok(0)\n}\n"
    "#main\nfun main() {\n"
    "    var errs = 0\n    var k = 0\n"
    "    while k < 100000 {\n"
    "        match chain(60) { Ok(_) => { } Err(_) => { errs = errs + 1 } }\n"
    "        k = k + 1\n    }\n    print(errs)\n}\n"
)


# `break`/`continue` jump past a live heap list (`xs`/`ys`) bound in the loop
# body's scope; the codegen must drop those owners on the way out or the arena
# leaks. ~12M cells through a finite arena means a leak would trap.
STRESS_LOOPCTL_SRC = (
    "enum List { Cons(int, List), Nil }\n"
    "fun make(n: int) -> List {\n"
    "    var acc: List = List.Nil\n    var i = 0\n"
    "    while i < n {\n        acc = List.Cons(i, acc)\n        i = i + 1\n    }\n"
    "    return acc\n}\n"
    "fun while_loop(iters: int) -> int {\n"
    "    var k = 0\n"
    "    while true {\n"
    "        let xs = make(60)\n        k = k + 1\n"
    "        if k % 2 == 0 {\n            continue\n        }\n"
    "        if k >= iters {\n            break\n        }\n    }\n"
    "    return k\n}\n"
    "fun for_loop(iters: int) -> int {\n"
    "    var hits = 0\n"
    "    for k in 0..iters {\n"
    "        let xs = make(40)\n"
    "        if k % 3 == 0 {\n            continue\n        }\n"
    "        let ys = make(20)\n        hits = hits + 1\n    }\n"
    "    return hits\n}\n"
    "#main\nfun main() {\n"
    "    print(while_loop(200000))\n    print(for_loop(200000))\n}\n"
)


# MYLA-105: strings churned through every ownership path the IR lowers (an
# owned temporary per concatenation, reassignment in a loop, an early return
# with an owner in scope, struct fields, a match on a string, a break): a
# missed drop would leak some 50 MB over the run and fail the peak check.
# MYLA-105: recursive enums replaced in every kind of member, millions of
# boxes: each write must release the box it replaces
STRESS_BOXED_MEMBERS_SRC = (
        "enum Tree {\n"
        "    Leaf(int),\n"
        "    Node(Tree, Tree),\n"
        "    Named(str, Tree),\n"
        "}\n"
        "\n"
        "struct Holder { tree: Tree, spare: [Tree] }\n"
        "\n"
        "fun grow(depth: int) -> Tree {\n"
        "    if depth == 0 { return Tree.Leaf(1) }\n"
        "    return Tree.Node(grow(depth - 1), Tree.Named(\"n\", grow(depth - 1)))\n"
        "}\n"
        "\n"
        "fun sum(t: Tree) -> int {\n"
        "    return match t {\n"
        "        Leaf(n) => n\n"
        "        Node(l, r) => sum(l) + sum(r)\n"
        "        Named(s, inner) => sum(inner)\n"
        "    }\n"
        "}\n"
        "\n"
        "#main\n"
        "fun main() {\n"
        "    var h = Holder { tree: Tree.Leaf(0), spare: [Tree.Leaf(0)] }\n"
        "    var forest = [\"k\": Tree.Leaf(0)]\n"
        "    var total = 0\n"
        "    var i = 0\n"
        "    while i < 30000 {\n"
        "        h.tree = grow(5)\n"
        "        h.spare[0] = grow(5)\n"
        "        forest[\"k\"] = grow(5)\n"
        "        push(h.spare, grow(5))\n"
        "        let t = pop(h.spare)\n"
        "        total = total + sum(h.tree) + sum(h.spare[0]) + sum(forest[\"k\"]) + sum(t)\n"
        "        i = i + 1\n"
        "    }\n"
        "    print(total)\n"
        "}\n"
)

STRESS_STR_OWNERSHIP_SRC = (
        "struct Person { name: str, tag: str }\n"
        "\n"
        "fun greet(p: Person) -> str {\n"
        '    return "hi " + p.name\n'
        "}\n"
        "\n"
        "fun pick(n: int) -> str {\n"
        '    var s = "x"\n'
        "    var i = 0\n"
        "    while i < n {\n"
        '        s = s + "y"\n'
        "        if i == 5 {\n"
        '            return s + "!"\n'
        "        }\n"
        "        i = i + 1\n"
        "    }\n"
        "    return s\n"
        "}\n"
        "\n"
        "fun label(s: str) -> int {\n"
        "    return match s {\n"
        '        "a" => 1,\n'
        '        "xyy" => 2,\n'
        "        _ => len(s),\n"
        "    }\n"
        "}\n"
        "\n"
        "#main\n"
        "fun main() {\n"
        "    var total = 0\n"
        "    var k = 0\n"
        "    while k < 300000 {\n"
        '        let p = Person { name: "n" + "m", tag: pick(k % 10) }\n'
        "        let g = greet(p)\n"
        "        total = total + len(g) + len(p.tag) + label(p.tag)\n"
        "        var w = p.name\n"
        "        w = w + w\n"
        "        if len(w) > 100 {\n"
        "            break\n"
        "        }\n"
        "        k = k + 1\n"
        "    }\n"
        "    print(total)\n"
        "}\n"
)


# Lists are reference-counted heap cells with copy-on-write. This churns millions
# of list allocations — building, sharing (forcing CoW clones), push/pop growth,
# and per-iteration drops — through the finite arena: a leak or a missed drop
# would exhaust it and trap. Exercises __alloc/__free reuse, __clone_list,
# __grow_list, and the per-element drop walk.
STRESS_LIST_SRC = (
    "fun sum(xs: [int]) -> int {\n"
    "    var t = 0\n    for x in xs {\n        t = t + x\n    }\n    return t\n}\n"
    "fun make(n: int) -> [int] {\n"
    "    var out: [int] = []\n"
    "    for i in 0..n {\n        push(out, i)\n    }\n    return out\n}\n"
    "#main\nfun main() {\n"
    "    var acc = 0\n"
    "    for r in 0..200000 {\n"
    "        let xs = make(20)\n"          # fresh list each iteration (grows, drops)
    "        var ys = xs\n"                 # share -> CoW on next write
    "        ys[0] = 5\n"                   # forces a clone of the shared buffer
    "        push(ys, 99)\n"
    "        let dropped = pop(ys)\n"
    "        acc = acc + sum(xs) - sum(xs)\n"  # net 0, but keeps xs live
    "    }\n"
    "    print(acc)\n}\n"
)


# Maps are reference-counted heap cells with copy-on-write, and `remove` rebuilds
# the table (allocating a fresh cell and moving values over). This churns millions
# of map allocations — building (with rehash growth), sharing (forcing CoW clones),
# per-key remove rebuilds, and per-iteration drops — through the finite arena: a
# leak or missed drop would exhaust it and trap. The values are themselves lists,
# so it also exercises the owned-value retain/drop walk inside __clone/__drop/
# __remove_map.
STRESS_MAP_SRC = (
    "fun make(n: int) -> [int: [int]] {\n"
    "    var m: [int: [int]] = [:]\n"
    "    var i = 0\n    while i < n {\n        m[i] = [i, i * 2]\n        i = i + 1\n    }\n"
    "    return m\n}\n"
    "#main\nfun main() {\n"
    "    var acc = 0\n"
    "    for r in 0..200000 {\n"
    "        var m = make(20)\n"          # fresh map each iteration (grows, drops)
    "        var c = m\n"                  # share -> CoW on next write
    "        c[0] = [7]\n"                 # forces a clone of the shared table
    "        remove(c, 1)\n"               # rebuild deletion (alloc + value move)
    "        acc = acc + len(m) - len(m)\n"  # net 0, but keeps m live
    "    }\n"
    "    print(acc)\n}\n"
)


# `remove` releases the value it takes out of the map (the self-hosted compiler
# leaked it, MYLA-25): 600k removals of a fresh 8-element list from one map.
STRESS_MAP_REMOVE_SRC = (
    "#main\nfun main() {\n"
    "    var m: [int: [int]] = [:]\n"
    "    var total = 0\n"
    "    for r in 0..600000 {\n"
    "        m[r % 7] = [r, r, r, r, r, r, r, r]\n"
    "        remove(m, (r + 3) % 7)\n"
    "        total = total + len(m)\n"
    "    }\n"
    "    print(total)\n}\n"
)


# StringBuilders are reference-counted, copy-on-write byte buffers that
# reallocate as they grow. This churns millions of builder cells through the
# finite arena — building (with repeated grows), sharing (forcing a CoW clone),
# mutating the clone (more grows), and per-iteration drops — so a leak or missed
# drop would exhaust the arena and trap.
STRESS_SB_SRC = (
    "fun make(n: int) -> StringBuilder {\n"
    "    var sb = StringBuilder()\n"
    "    var i = 0\n    while i < n {\n        append(sb, \"abcde\")\n"
    "        i = i + 1\n    }\n    return sb\n}\n"
    "#main\nfun main() {\n"
    "    var acc = 0\n"
    "    for r in 0..200000 {\n"
    "        var sb = make(8)\n"            # fresh builder each iteration (grows)
    "        var c = sb\n"                   # share -> CoW on next write
    "        append(c, \"Z\")\n"             # clones the shared buffer, may grow
    "        acc = acc + len(sb) - len(sb)\n"  # net 0, but keeps sb live
    "    }\n"
    "    print(acc)\n}\n"
)


STRESS_CLOSURE_SRC = (
    # Each iteration builds a list holding two *capturing* closures (each owning a
    # refcounted environment) and then drops the list at the end of the loop body.
    # Far more environment cells are allocated than the arena holds at once, so it
    # only completes (exit 0) if closure environments are reference-counted and
    # their cells returned to the free list.
    "#main\nfun main() {\n"
    "    var acc = 0\n"
    "    for r in 0..300000 {\n"
    "        var fns: [(int) -> int] = []\n"
    "        let cap = r\n"
    "        push(fns, (n: int) => n + cap)\n"
    "        push(fns, (n: int) => n + cap + 1)\n"
    "        acc = acc + fns[0](0) + fns[1](0) - (2 * r + 1)\n"
    "    }\n"
    "    print(acc)\n}\n"
)

STRESS_PARTIAL_SRC = (
    # `>>` composition and `_` partial application both desugar to capturing
    # lambdas (refcounted environments). Each iteration builds a composed
    # function and a partial application that capture a per-iteration value,
    # then drops them — far more env cells than the arena holds at once, so it
    # only finishes (exit 0) if those desugared closures are reference-counted.
    "fun add(a: int, b: int) -> int {\n    return a + b\n}\n"
    "#main\nfun main() {\n"
    "    var acc = 0\n"
    "    for r in 0..300000 {\n"
    "        let cap = r\n"
    "        let bump = (x: int) => x + cap\n"
    "        let composed = bump >> bump\n"             # (x) => (x + cap) + cap
    "        let plus_cap = add(cap, _)\n"              # (b) => add(cap, b)
    "        acc = acc + composed(0) + plus_cap(0) - 3 * r\n"
    "    }\n"
    "    print(acc)\n}\n"
)


STRESS_TRAIT_DISPATCH_SRC = (
    # A generic `T: Add` summed over a heap-owning user type (`Bag` owns a list):
    # the bounded operator dispatches to `Bag.add`, which copies/concatenates
    # lists, allocating refcounted list cells. Each iteration builds and drops
    # several Bags/lists — far more cells than the arena holds at once, so it
    # only finishes (exit 0) if trait-dispatched results are reference-counted.
    "struct Bag { items: [int] }\n"
    "impl Add for Bag {\n"
    "    fun add(self, other: Bag) -> Bag {\n"
    "        var r = self.items\n        for x in other.items { push(r, x) }\n"
    "        return Bag { items: r }\n    }\n}\n"
    "fun total<T: Add>(xs: [T], zero: T) -> T {\n"
    "    var acc = zero\n    for x in xs { acc = acc + x }\n    return acc\n}\n"
    "#main\nfun main() {\n"
    "    var checksum = 0\n"
    "    for r in 0..200000 {\n"
    "        let a = Bag { items: [r, r] }\n"
    "        let b = Bag { items: [r] }\n"
    "        let c = total([a, b], Bag { items: [] })\n"
    "        checksum = checksum + len(c.items)\n"
    "    }\n    print(checksum)\n}\n"
)


_BIG_LIST = "[" + ", ".join(["i"] * 64) + "]"   # a fresh 544-byte cell per use

STRESS_TRY_AFTER_STAGED_VALUE_SRC = (
    # A container store evaluates its value first (MYLA-4); a `?` that fails
    # later, in the map key, the list index or the pushed-to list's expression,
    # must release that value. 2.5 million leaked 64-element lists would need
    # 1.4 GB, more than the 1 GiB arena.
    "fun fail(i: int) -> Result<int, str> {\n    return Err(\"no\")\n}\n"
    "fun by_key(i: int) -> Result<int, str> {\n"
    "    var m: [int: [int]] = [:]\n"
    f"    m[fail(i)?] = {_BIG_LIST}\n"
    "    return Ok(len(m))\n}\n"
    "fun by_index(i: int) -> Result<int, str> {\n"
    "    var xs: [[int]] = [[]]\n"
    f"    xs[fail(i)?] = {_BIG_LIST}\n"
    "    return Ok(len(xs))\n}\n"
    "fun by_holder(i: int) -> Result<int, str> {\n"
    "    var xss: [[[int]]] = [[]]\n"
    f"    push(xss[fail(i)?], {_BIG_LIST})\n"
    "    return Ok(len(xss))\n}\n"
    "#main\nfun main() {\n"
    "    var fails = 0\n"
    "    for i in 0..2500000 {\n"
    "        match by_key(i) { Ok(n) => {}, Err(e) => { fails = fails + 1 } }\n"
    "        match by_index(i) { Ok(n) => {}, Err(e) => { fails = fails + 1 } }\n"
    "        match by_holder(i) { Ok(n) => {}, Err(e) => { fails = fails + 1 } }\n"
    "    }\n    print(fails)\n}\n"
)


# Strings are reference-counted cells like lists (MYLA-18): results of `+`,
# `format`, f-strings and `build`, strings held by structs, lists and as map
# keys (inserted, removed, listed by `keys`) are all released. About 2 GB of
# strings go through the 1 GiB arena.
STRESS_STR_SRC = (
    "struct Named {\n    name: str,\n    n: int,\n}\n"
    "fun label(i: int) -> str {\n"
    "    return format(\"item-{}-{}-{}\", i, i % 7 == 0, 'x') + \"-padding-padding-padding-padding-padding-padding-padding-padding-padding-padding-padding-padding-padding-padding-padding-padding-padding-padding-padding-padding\"\n}\n"
    "#main\nfun main() {\n"
    "    var total = 0\n"
    "    var m: [str: int] = [:]\n"
    "    for r in 0..600000 {\n"
    "        let a = label(r)\n"
    "        let b = a + \"-\" + a\n"
    "        let c = Named { name: b, n: r }\n"
    "        var xs = [c.name, a]\n"
    "        push(xs, f\"{r}:{c.n}\")\n"
    "        let key = f\"k{r}\"\n"
    "        m[key] = len(b)\n"
    "        let v = m[key]\n"
    "        if len(m) > 50 {\n"
    "            for k in keys(m) {\n                remove(m, k)\n            }\n"
    "        }\n"
    "        var sb = StringBuilder()\n"
    "        append(sb, b)\n"
    "        let built = build(sb)\n"
    "        total = total + len(xs) + len(built) - v\n"
    "    }\n"
    "    print(total)\n}\n"
)

# The temporaries of an `if` or `while` condition, a range bound and a match
# guard have no statement end to release them; they must be dropped right after
# the value is computed. An `&&`/`||` operand drops its own, since the right one
# may not run (here it ran in the previous iteration, so its slot holds a
# dropped list) (MYLA-74).
STRESS_CONDITION_TEMPS_SRC = (
    "fun make(n: int) -> [int] {\n"
    "    var out: [int] = []\n    for i in 0..n {\n        push(out, i)\n    }\n    return out\n}\n"
    "fun nonempty(xs: [int]) -> bool {\n    return len(xs) > 0\n}\n"
    "#main\nfun main() {\n"
    "    var acc = 0\n"
    "    for r in 0..600000 {\n"
    "        if nonempty(make(200)) {\n            acc = acc + 1\n        }\n"
    "        var k = 0\n"
    "        while k < len(make(30)) {\n            k = k + 10\n        }\n"
    "        for i in 0..len(make(100)) - 99 {\n            acc = acc + k\n        }\n"
    "        match r {\n            x if nonempty(make(50)) => {\n                acc = acc + 1\n            },\n            _ => {},\n        }\n"
    "        if r % 2 == 0 && nonempty(make(20)) {\n            acc = acc + 1\n        }\n"
    "        let b = r % 3 == 0 || len(make(10)) > 5\n"
    "        if b {\n            acc = acc + 1\n        }\n"
    "    }\n"
    "    print(acc)\n}\n"
)

# A match's scrutinee temporaries (here the `Option` a call returns, holding a
# list) are dropped when the statement ends; an arm that leaves early with
# `return`, `continue` or `break` must drop them itself. A leak keeps the lists
# alive and exhausts the arena (MYLA-74).
STRESS_MATCH_EARLY_EXIT_SRC = (
    "fun make(n: int) -> [int] {\n"
    "    var out: [int] = []\n    for i in 0..n {\n        push(out, i)\n    }\n    return out\n}\n"
    "fun find(xs: [[int]], i: int) -> Option<[int]> {\n"
    "    if i < len(xs) {\n        return Some(xs[i])\n    }\n    return None\n}\n"
    "fun first(xs: [[int]]) -> [int] {\n"
    "    match find(xs, 0) {\n        Some(v) => {\n            return v\n        },\n        None => {},\n    }\n"
    "    return []\n}\n"
    "fun total(xs: [[int]]) -> int {\n"
    "    var n = 0\n    var i = 0\n"
    "    while true {\n"
    "        match find(xs, i) {\n"
    "            Some(v) => {\n"
    "                i = i + 1\n"
    "                if len(v) == 100 {\n                    continue\n                }\n"
    "                n = n + len(v)\n"
    "            },\n"
    "            None => {\n                break\n            },\n"
    "        }\n"
    "    }\n"
    "    return n\n}\n"
    "#main\nfun main() {\n"
    "    var acc = 0\n"
    "    for r in 0..600000 {\n"
    "        let xs = [make(200), make(100), make(50)]\n"
    "        acc = acc + len(first(xs)) + total(xs)\n"
    "    }\n"
    "    print(acc)\n}\n"
)

# A match expression's value owns a reference (the arm's value is retained into
# the result slot); the statement that uses it must release it like any other
# temporary. Here a list comes out of a match through `return`, a `let` and a
# call argument, 600,000 times: a leaked reference keeps every list alive and
# exhausts the arena (MYLA-74).
STRESS_MATCH_RESULT_SRC = (
    "enum Box {\n    Full([int]),\n    Empty,\n}\n"
    "fun items(b: Box) -> [int] {\n"
    "    return match b {\n        Box.Full(xs) => xs,\n        Box.Empty => [],\n    }\n}\n"
    "fun make(n: int) -> [int] {\n"
    "    var out: [int] = []\n    for i in 0..n {\n        push(out, i)\n    }\n    return out\n}\n"
    "#main\nfun main() {\n"
    "    var acc = 0\n"
    "    for r in 0..600000 {\n"
    "        let b = Box.Full(make(200))\n"
    "        let xs = items(b)\n"
    "        let ys = match b {\n            Box.Full(zs) => zs,\n            Box.Empty => xs,\n        }\n"
    "        acc = acc + len(xs) + len(ys) - len(match b {\n            Box.Full(ws) => ws,\n            Box.Empty => xs,\n        })\n"
    "    }\n"
    "    print(acc)\n}\n"
)


STRESS_FRAGMENTED_FREE_SRC = (
    # Leaves 8000 freed cells of 8000 different sizes behind (each `keys(m)` on
    # a growing map frees a list one slot longer than the last), then allocates
    # 30000 small lists that none of those cells fit. An allocator that scans
    # one free list on every allocation does 240 million probes here (about
    # 14 s); size-class free lists find "nothing free" at once (MYLA-16).
    "#main\nfun main() {\n"
    "    var m: [int: int] = [:]\n"
    "    var i = 0\n"
    "    while i < 8000 {\n"
    "        m[i] = i\n"
    "        let ks = keys(m)\n"
    "        i = i + 1\n"
    "    }\n"
    "    var keep: [[int]] = []\n"
    "    var j = 0\n"
    "    while j < 30000 {\n"
    "        push(keep, [j, j])\n"
    "        j = j + 1\n"
    "    }\n"
    "    print(len(keep) + len(m))\n}\n"
)

STRESS_LARGE_SIZES_SRC = (
    # Builds and drops 20000 strings of 20000 different sizes above 4 KiB
    # (1.7 GB in all). A freed large cell kept for an allocation of exactly its
    # size is never used again and the 1 GiB arena runs out; size classes for
    # large cells reuse them (MYLA-80, found as the language server's memory
    # growing with every check).
    "#main\nfun main() {\n"
    "    var sb = StringBuilder()\n"
    "    for k in 0..170000 { append_byte(sb, 'x') }\n"
    "    let big = build(sb)\n"
    "    var total = 0\n"
    "    for i in 0..20000 {\n"
    "        var part = StringBuilder()\n"
    "        append(part, big, 0, 4100 + 8 * i)\n"
    "        let s = build(part)\n"
    "        total = total + len(s) % 7\n"
    "    }\n"
    "    print(total)\n}\n"
)

STRESS_FOR_EARLY_RETURN_SRC = (
    # Returns from inside `for` loops over fresh lists and maps a million
    # times. The loop holds a reference to what it iterates; a `return` from
    # its body left it held, so every list and map stayed allocated (MYLA-80,
    # the language server's checker leaking 7 MB per check).
    "fun first_big(xs: [int]) -> int {\n"
    "    for x in xs {\n        if x > 1 { return x }\n    }\n"
    "    return 0\n}\n"
    "fun any_key(m: [int: int]) -> int {\n"
    "    for k in m { return k }\n"
    "    return -1\n}\n"
    "fun nested(xs: [[int]]) -> int {\n"
    "    for row in xs {\n        for x in row {\n            if x == 3 { return x }\n        }\n    }\n"
    "    return 0\n}\n"
    "#main\nfun main() {\n"
    "    var total = 0\n"
    "    for i in 0..1000000 {\n"
    "        var xs = [1, i, 5]\n"
    "        for k in 0..250 { push(xs, k) }\n"       # 1 KB a list: a leak exhausts the arena
    "        var m: [int: int] = [:]\n"
    "        m[i % 7] = 1\n"
    "        total = total + first_big(xs) % 3 + any_key(m) + nested([[1, 2], [3, i]])\n"
    "    }\n"
    "    print(total)\n}\n"
)

STRESS_MAP_OVERWRITE_SRC = (
    # Overwrites map entries holding strings, lists and maps a million times.
    # The self-hosted backend stored the new value without releasing the old
    # one, so every overwrite leaked it (MYLA-80, the language server keeping
    # every version of a document).
    "#main\nfun main() {\n"
    "    var docs: [str: str] = [:]\n"
    "    var lists: [int: [int]] = [:]\n"
    "    var nested: [str: [str: int]] = [:]\n"
    "    var total = 0\n"
    "    for i in 0..1000000 {\n"
    "        docs[\"a\"] = format(\"version {}\", i)\n"
    "        lists[i % 3] = [i, i, i]\n"
    "        var inner: [str: int] = [:]\n"
    "        inner[\"k\"] = i\n"
    "        nested[\"x\"] = inner\n"
    "        total = total + len(docs[\"a\"]) % 2 + lists[i % 3][0] % 2 + nested[\"x\"][\"k\"] % 2\n"
    "    }\n"
    "    print(total)\n}\n"
)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestCompilerParity(unittest.TestCase):
    def test_overwritten_map_values_are_released(self):
        out, code = build_and_run(STRESS_MAP_OVERWRITE_SRC, timeout=60)
        self.assertEqual(code, 0)
        expected = sum(len(f"version {i}") % 2 + 2 * (i % 2) for i in range(1000000))
        self.assertEqual(out.strip(), str(expected))

    def test_returning_from_a_for_loop_releases_its_iterable(self):
        out, code = build_and_run(STRESS_FOR_EARLY_RETURN_SRC, timeout=60)
        self.assertEqual(code, 0, "arena exhausted — loops leaked what they iterate")
        expected = sum((i if i > 1 else 5) % 3 + i % 7 + 3 for i in range(1000000))
        self.assertEqual(out.strip(), str(expected))

    def test_large_cells_of_new_sizes_are_reused(self):
        out, code = build_and_run(STRESS_LARGE_SIZES_SRC, timeout=60)
        self.assertEqual(code, 0, "arena exhausted — large cells were not reused")
        self.assertEqual(out.strip(), str(sum((4100 + 8 * i) % 7 for i in range(20000))))

    def test_allocation_does_not_scan_unusable_free_cells(self):
        # Must finish far below the 5 s limit: the linear free-list scan took
        # about 14 s, size-class free lists take milliseconds.
        out, code = build_and_run(STRESS_FRAGMENTED_FREE_SRC, timeout=5)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "38000")

    def test_strings_are_reclaimed(self):
        out, code = build_and_run(STRESS_STR_SRC)
        self.assertEqual(code, 0, "arena exhausted — strings were not reclaimed")
        self.assertEqual(out.strip(), "1800000")

    def test_condition_temporaries_are_released(self):
        out, code = build_and_run(STRESS_CONDITION_TEMPS_SRC)
        self.assertEqual(code, 0, "arena exhausted — condition temporaries leaked")
        self.assertEqual(out.strip(), "20100000")

    def test_early_exits_from_match_arms_drop_the_scrutinee(self):
        out, code = build_and_run(STRESS_MATCH_EARLY_EXIT_SRC)
        self.assertEqual(code, 0, "arena exhausted — scrutinee temporaries leaked")
        self.assertEqual(out.strip(), "270000000")

    def test_match_results_are_released(self):
        out, code = build_and_run(STRESS_MATCH_RESULT_SRC)
        self.assertEqual(code, 0, "arena exhausted — match results leaked")
        self.assertEqual(out.strip(), "120000000")

    def test_trait_dispatch_reference_counting_reclaims_heap(self):
        # millions of list cells allocated through a bounded-generic operator
        # that dispatches to a user `Add` impl: the results must be refcounted.
        out, code = build_and_run(STRESS_TRAIT_DISPATCH_SRC)
        self.assertEqual(code, 0, "arena exhausted — trait-dispatched results leaked")
        self.assertEqual(out.strip(), "600000")

    def test_closure_environment_reference_counting_reclaims_heap(self):
        # millions of capturing-closure environment cells through a finite arena.
        out, code = build_and_run(STRESS_CLOSURE_SRC)
        self.assertEqual(code, 0, "arena exhausted — closure environments leaked")
        self.assertEqual(out.strip(), "0")

    def test_partial_and_compose_reference_counting_reclaims_heap(self):
        # millions of desugared `>>`/`_` closure environments through a finite
        # arena: composition and partial application must refcount like lambdas.
        out, code = build_and_run(STRESS_PARTIAL_SRC)
        self.assertEqual(code, 0, "arena exhausted — desugared closures leaked")
        self.assertEqual(out.strip(), "0")

    def test_string_builder_reference_counting_reclaims_heap(self):
        # millions of builder cells (build/grow/share/CoW) through a finite arena.
        out, code = build_and_run(STRESS_SB_SRC)
        self.assertEqual(code, 0, "arena exhausted — builder cells were not reclaimed")
        self.assertEqual(out.strip(), "0")

    def test_map_remove_reclaims_heap(self):
        out, code = build_and_run(STRESS_MAP_REMOVE_SRC)
        self.assertEqual((out.strip(), code), ("2399994", 0))

    def test_map_reference_counting_reclaims_heap(self):
        # millions of map cells (build/grow/share/CoW/remove) through a finite arena.
        out, code = build_and_run(STRESS_MAP_SRC)
        self.assertEqual(code, 0, "arena exhausted — map cells were not reclaimed")
        self.assertEqual(out.strip(), "0")

    def test_list_reference_counting_reclaims_heap(self):
        # millions of list cells (build/share/CoW/push/pop) through a finite arena.
        out, code = build_and_run(STRESS_LIST_SRC)
        self.assertEqual(code, 0, "arena exhausted — list cells were not reclaimed")
        self.assertEqual(out.strip(), "0")

    def test_divide_by_zero_traps_nonzero(self):
        src = "#main\nfun main() {\n    var z = 0\n    print(1 / z)\n}\n"
        out, code = build_and_run(src)
        self.assertEqual(out, "")
        self.assertNotEqual(code, 0)

    def test_reference_counting_reclaims_heap(self):
        # ~12M cells through a finite arena: must complete (exit 0) and be correct.
        out, code = build_and_run(STRESS_SRC)
        self.assertEqual(code, 0, "arena exhausted — dropped cells were not reused")
        self.assertEqual(out.strip(), "354000000")

    def test_try_early_return_drops_live_heap(self):
        # `?` failure path must drop the heap list still bound in the frame.
        out, code = build_and_run(STRESS_TRY_SRC)
        self.assertEqual(code, 0, "arena exhausted — `?` early return leaked locals")
        self.assertEqual(out.strip(), "100000")

    def test_try_after_a_staged_value_releases_it(self):
        out, code = build_and_run(STRESS_TRY_AFTER_STAGED_VALUE_SRC)
        self.assertEqual(code, 0, "arena exhausted — staged container values leaked")
        self.assertEqual(out.strip(), "7500000")

    def test_break_continue_drop_live_heap(self):
        # `break`/`continue` must drop heap owners bound in the loop body scope.
        out, code = build_and_run(STRESS_LOOPCTL_SRC)
        self.assertEqual(code, 0, "arena exhausted — break/continue leaked locals")
        self.assertEqual(out.strip(), "200001\n133333")

    def test_boxed_members_are_released(self):
        # MYLA-105: the recursive-enum stress program the IR gate also runs
        out, code = build_and_run(STRESS_BOXED_MEMBERS_SRC)
        self.assertEqual(code, 0, "arena exhausted: boxes leaked")
        self.assertEqual(out.strip(), "3840000")

    def test_strings_drop_on_every_path(self):
        # MYLA-105: the string stress program the IR gate also runs
        out, code = build_and_run(STRESS_STR_OWNERSHIP_SRC)
        self.assertEqual(code, 0, "arena exhausted: strings leaked")
        self.assertEqual(out.strip(), "4650000")

    def test_panic_aborts_after_flushing_output(self):
        # panic() exits nonzero; output emitted before it must still appear.
        src = '#main\nfun main() {\n    print(1)\n    panic("boom")\n    print(2)\n}\n'
        out, code = build_and_run(src)
        self.assertEqual(out, "1\n")
        self.assertNotEqual(code, 0)

    def test_assert_failure_aborts(self):
        src = ('#main\nfun main() {\n    print(7)\n'
               '    assert(1 > 2, "nope")\n    print(8)\n}\n')
        out, code = build_and_run(src)
        self.assertEqual(out, "7\n")
        self.assertNotEqual(code, 0)

    def test_assert_pass_does_not_abort(self):
        src = "#main\nfun main() {\n    assert(1 < 2)\n    print(42)\n}\n"
        out, code = build_and_run(src)
        self.assertEqual(out, "42\n")
        self.assertEqual(code, 0)

    def test_unreachable_aborts(self):
        src = ("enum E { A, B }\n"
               "fun g(e: E) -> int32 {\n"
               "    return match e {\n        E.A => 1,\n"
               "        E.B => unreachable(),\n    }\n}\n"
               "#main\nfun main() {\n    print(g(E.B))\n}\n")
        out, code = build_and_run(src)
        self.assertEqual(out, "")
        self.assertNotEqual(code, 0)


def _make(src: str):
    def test(self):
        native_out, code = build_and_run(src)
        self.assertEqual(code, 0)
        self.assertEqual(native_out, interpret(src))
    return test


for _name, _src in PROGRAMS.items():
    setattr(TestCompilerParity, f"test_{_name}", _make(_src))


if __name__ == "__main__":
    unittest.main()
