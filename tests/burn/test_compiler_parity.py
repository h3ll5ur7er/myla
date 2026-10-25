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


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestCompilerParity(unittest.TestCase):
    def test_allocation_does_not_scan_unusable_free_cells(self):
        # Must finish far below the 5 s limit: the linear free-list scan took
        # about 14 s, size-class free lists take milliseconds.
        out, code = build_and_run(STRESS_FRAGMENTED_FREE_SRC, timeout=5)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "38000")

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
