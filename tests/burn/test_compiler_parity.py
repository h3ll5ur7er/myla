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


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestCompilerParity(unittest.TestCase):
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
