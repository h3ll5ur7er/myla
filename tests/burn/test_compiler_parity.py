"""Burn tests: hand-written programs exercising codegen corners, each asserting
the native binary's output matches the interpreter (and exit codes for traps)."""
import os
import re
import subprocess
import tempfile
import unittest

from tests.burn._targets import program_excuse
from tests.burn._tools import selfhost_tool
from tests.burn._native import (CAN_BUILD_NATIVE, SKIP_REASON, Program, build_and_run, build_and_run_full, interpret,
                                native_build, run_argv, run_file_both_now, selfhost_run, write_program)

PROGRAMS = {
    # MYLA-553, MYLA-580, MYLA-546: containers' iter(), ldexp, padding in bulk
    "iter_ldexp_and_padding_in_bulk": r"""// MYLA-553, MYLA-580, MYLA-546: `iter()` on a BitSet, an Lru and a Grid;
// `ldexp` past ±2100 in three steps; long paddings and repeats in bulk
import std.bitset as bitset
import std.cache as cache
import std.grid as grid
import std.iter as iter
import std.math as math
import std.num as num
import std.fmt as fmt

fun ends(s: str) -> str {
    return f"{s.len()} {s[:4]}|{s[s.len() - 4:]}"
}

fun main() {
    var b = bitset.fixed(300)
    for i in [0, 63, 64, 199, 299] {
        b.insert(i)
    }
    var seen = ""
    for i in b.iter() {
        seen = seen + f"{i},"
    }
    print(f"{seen} {b.iter() |> iter.map((x) => x + 1) |> iter.sum(0)}")
    var c: cache.Lru<str, int> = cache.new(3)
    for k in ["a", "b", "c", "d"] {
        c.put(k, k.len())
    }
    c.get("b")
    var order = ""
    for (k, v) in c.iter() {
        order = order + f"{k}{v} "
    }
    print(order)
    let g = grid.new(3, 2, 'x')
    print(g.iter() |> iter.count())
    print(f"{math.ldexp(1.5, 2147483647)} {math.ldexp(-1.5, -2147483647 - 1)} {math.ldexp(4.9406564584124654e-324, 2097)} {math.ldexp(1.7976931348623157e308, -2098)}")
    print(ends(fmt.fmt_text("xy", ">1000000")))
    print(ends(fmt.pad("xy", "é^999999")))
    print(ends(fmt.fmt_int(-5i64, 32, true, "01000000")))
    print(ends(f"{255:#0100x}"))
    print(ends(num.to_hex(255u64, 1000003)))
    print(ends(num.to_binary(5u64, 4097)))
    print(ends("abc".repeat(333333)))
    print(ends("ab".pad_start(70000, 'ß')))
}
""",
    # MYLA-545: `v.0.0` is two tuple indexes, not `v.` and the float `0.0`
    "tuple_index_chain": r"""fun main() {
    let v = ((1, 2), (3, (4, 5)))
    print(v.0.0)
    print(v.1.1.0 + v.0.1)
    let w = [(7, (8, 9.5))]
    print(w[0].1.1)
    print(w[0].1.0 * 2)
    let x = 0.5
    print(x + 1.25e1)
}
""",
    # MYLA-429: a map that removals leave with few keys shrinks
    "map_shrinks_on_remove": r"""// MYLA-429: a map that removals leave with few keys shrinks: its order, its
// copies, a walk that removes, string, narrow and compound keys, values that
// own memory, and maps in fields and lists all go through the compaction
#derive(Eq, Hash)
struct P {
    x: int,
    y: int,
}

struct Holder {
    m: [int: str],
}

fun show(m: [int: int]) -> str {
    var sb = StringBuilder()
    for k in m {
        sb.append(f"{k}={m[k]} ")
    }
    return sb.build()
}

fun main() {
    // grown to 1,000 keys, then all but six removed, in a scrambled order
    var m: [int: int] = [:]
    for i in 0..1000 {
        m[i] = i * 2
    }
    let before = m
    for i in 0..1000 {
        let k = (i * 7) % 1000
        if k % 199 != 3 { m.remove(k) }
    }
    print(f"{m.len()} {show(m)}")
    // the copy taken before kept every key, in order
    print(f"{before.len()} {before[0]} {before[999]} {before.keys()[500]}")
    // the order after the compaction: new keys last, a removed one again last
    m[5000] = 1
    m.remove(201)
    m[201] = 7
    print(show(m))
    // a walk that removes every key it visits: it walks the keys it began with
    var seen = 0
    for k in m {
        m.remove(k)
        seen += 1
    }
    print(f"{seen} {m.len()} [{show(m)}]")
    m[1] = 1
    print(show(m))

    // string keys and values that own memory, through the compaction
    var w: [str: [str]] = [:]
    for i in 0..300 {
        w[f"k{i}"] = [f"v{i}", f"w{i}"]
    }
    for i in 0..300 {
        if i % 50 != 7 { w.remove(f"k{i}") }
    }
    var sb = StringBuilder()
    for k in w {
        sb.append(f"{k}:{w[k][0]},{w[k][1]} ")
    }
    print(f"{w.len()} {sb.build()}")
    w["k7"].push("x")
    print(f"{w["k7"].len()} {w.contains("k8")} {w.contains("k57")}")

    // narrow keys
    var c: [char: bool] = [:]
    for ch in "abcdefghijklmnopqrstuvwxyz".chars() {
        c[ch] = ch < 'n'
    }
    for ch in "abcdefghijklmnopqrstuvwxy".chars() {
        c.remove(ch)
    }
    print(f"{c.len()} {c.keys()[0]} {c['z']}")
    var b: [int8: int8] = [:]
    for i in 0..100 {
        b[i as int8] = (i % 7) as int8
    }
    for i in 0..98 {
        b.remove(i as int8)
    }
    print(f"{b.len()} {b.keys()[0]} {b.keys()[1]} {b[99]}")

    // compound keys
    var pm: [P: str] = [:]
    var tm: [(int, str): int] = [:]
    for i in 0..400 {
        pm[P { x: i, y: -i }] = f"p{i}"
        tm[(i, f"t{i}")] = i
    }
    for i in 0..400 {
        if i % 97 != 1 {
            pm.remove(P { x: i, y: -i })
            tm.remove((i, f"t{i}"))
        }
    }
    var ps = StringBuilder()
    for p in pm {
        ps.append(f"{p.x},{p.y}={pm[p]} ")
    }
    print(f"{pm.len()} {ps.build()}")
    var ts = StringBuilder()
    for t in tm.keys() {
        ts.append(f"{t.0}/{t.1} ")
    }
    print(f"{tm.len()} {ts.build()}{tm[(98, "t98")]} {tm.contains((99, "t99"))}")

    // a map in a field and in a list
    var h = Holder { m: [:] }
    for i in 0..200 {
        h.m[i] = f"s{i}"
    }
    var hs: [Holder] = [h, h]
    for i in 0..199 {
        h.m.remove(i)
        hs[1].m.remove(199 - i)
    }
    print(f"{h.m.len()} {h.m[199]} {hs[0].m.len()} {hs[1].m.len()} {hs[1].m[0]}")

    // emptied, then filled again
    var e: [int: int] = [:]
    for i in 0..5000 {
        e[i] = i
    }
    for i in 0..5000 {
        e.remove(4999 - i)
    }
    for i in 0..10 {
        e[(i * 3) % 10] = i
    }
    print(f"{e.len()} {show(e)}")
}
""",
    # MYLA-496: a `for` over a map walks its slots, without the list of keys
    "for_over_a_map_walks_its_slots": r"""// MYLA-496: `for k in m` walks the map's slots in the order of insertion
// without the list of its keys: the keys it started with whatever the body
// does to the map, past the gaps of removed keys and taken tombstones, over
// string, narrow and compound keys, a `let` map, a field and a list's map,
// with `break`, `continue` and `return`, nested, and in an async function
#derive(Eq, Hash)
struct P {
    x: int,
    name: str,
}

struct Holder {
    m: [str: int],
}

fun show(m: [int: int]) -> str {
    var sb = StringBuilder()
    for k in m {
        sb.append(f"{k}={m[k]} ")
    }
    return sb.build()
}

fun ints(xs: [int]) -> str {
    var sb = StringBuilder()
    for x in xs { sb.append(f"{x},") }
    return sb.build()
}

// the first key at or above `at`, by a loop that returns from inside
fun first_from(m: [int: int], at: int) -> int {
    for k in m {
        if k >= at { return k }
    }
    return -1
}

async fun total(m: [str: int]) -> int {
    var t = 0
    for k in m {
        t += m[k]
    }
    return t
}

#main
async fun main() {
    // a queue: the oldest key taken until none is left
    var q: [int: int] = [:]
    for i in 0..3000 { q[i] = i }
    var taken = 0
    var sum = 0
    while q.len() > 0 {
        var first = -1
        for k in q {
            first = k
            break
        }
        sum += first
        q.remove(first)
        taken += 1
        // now and then a key goes in again, at the end
        if taken % 1000 == 0 { q[first] = first }
    }
    print(f"{taken} {sum}")

    // the body changes the map: the loop walks the keys it began with
    var m: [int: int] = [:]
    for i in 0..10 { m[i] = i * i }
    var seen: [int] = []
    for k in m {
        seen.push(k)
        if k % 2 == 0 { m.remove(k + 1) }
        m[100 + k] = k
    }
    print(f"{ints(seen)} {m.len()}")
    print(show(m))
    // tombstones taken by new keys: the order is still the insertion's
    var t: [int: int] = [:]
    for i in 0..8 { t[i] = i }
    t.remove(2)
    t.remove(5)
    t[2] = 20
    t[9] = 90
    t.remove(0)
    t[5] = 50
    print(show(t))
    print(f"{first_from(t, 4)} {first_from(t, 8)} {first_from(t, 100)}")
    // continue, and a nested loop over the same map
    var pairs = 0
    for a in t {
        if a % 2 == 1 { continue }
        for b in t {
            if b > a { pairs += 1 }
        }
    }
    print(pairs)

    // string keys, through removals and a compaction
    var w: [str: int] = [:]
    for i in 0..200 { w[f"k{i}"] = i }
    for i in 0..200 {
        if i % 40 != 3 { w.remove(f"k{i}") }
    }
    var sb = StringBuilder()
    for k in w { sb.append(k + " ") }
    print(sb.build())
    // a `let` map, a field's and a list's
    let fixed = w
    var n = 0
    for k in fixed { n += fixed[k] }
    var h = Holder { m: w }
    for k in h.m { h.m.remove(k) }
    let ms = [w, h.m]
    var lens: [int] = []
    for mm in ms {
        var c = 0
        for k in mm { c += k.len() }
        lens.push(c)
    }
    print(f"{n} {h.m.len()} {ints(lens)}")

    // compound and narrow keys
    var cm: [P: int] = [:]
    for i in 0..6 { cm[P { x: i, name: f"p{i}" }] = i }
    cm.remove(P { x: 0, name: "p0" })
    cm.remove(P { x: 3, name: "p3" })
    cm[P { x: 0, name: "p0" }] = 9
    var cs = StringBuilder()
    for k in cm { cs.append(f"{k.name}:{cm[k]} ") }
    print(cs.build())
    var lm: [[int]: str] = [[1]: "a", [2, 3]: "b", []: "c"]
    lm.remove([1])
    lm[[1]] = "d"
    var ls = StringBuilder()
    for k in lm { ls.append(f"{k.len()}{lm[k]} ") }
    print(ls.build())
    var bm: [uint8: bool] = [:]
    for i in 0..5 { bm[(250 + i) as uint8] = i % 2 == 0 }
    bm.remove(251)
    var bs = StringBuilder()
    for k in bm { bs.append(f"{k}={bm[k]} ") }
    print(bs.build())
    var tm: [(int, char): int] = [(1, 'a'): 1, (2, 'b'): 2]
    for k in tm { tm[(k.0 + 10, k.1)] = k.0 }
    var ts = StringBuilder()
    for (a, c) in tm { ts.append(f"{a}{c} ") }
    print(ts.build())

    // empty maps, and one emptied
    var e: [int: int] = [:]
    for k in e { print(k) }
    e[1] = 1
    e.remove(1)
    for k in e { print(k) }
    print(f"{e.len()} {await total(fixed)}")
}
""",
    # D173 (MYLA-379): `IoError`'s `message()` and `Format`
    "io_error_text": r"""// D173 (MYLA-379): an `IoError`'s `message()` and `Format`: the cause in
// words, its name after it
import std.fs as fs
from std.fs import IoError, from_errno

fun main() {
    match fs.read_to_string("/no/such/dir/file.txt") {
        Ok(s) => { print(s) },
        Err(e) => {
            print(f"cannot read: {e}")
            print(e)
            print(e.message() == f"{e}")
        },
    }
    for code in [1, 2, 17, 20, 21, 39, 4, 125, 38, 32, 22, 111, 104, 103, 107, 98, 99, 110, 113, 101, 74, 5] {
        print(from_errno(code))
    }
    let r: Result<str, IoError> = Err(IoError.Other(-3))
    match r {
        Ok(s) => { print(s) },
        Err(e) => { print(f"<{e}>") },
    }
}
""",
    # MYLA-379: `==` on `Option` and `Result` whose payloads are `Eq`
    "option_result_equality": r"""// MYLA-379: `==` and `!=` on `Option` and `Result` whose payloads are `Eq`:
// literals on either side, nested, in tuples, lists, derived structs and
// generic code, a map's `get`, a float's NaN unequal to itself
#derive(Eq)
struct P {
    x: int,
    name: str,
}

#derive(Eq)
struct Holder {
    tag: Option<str>,
    res: Result<int, str>,
}

#derive(Eq)
enum Shape {
    Dot,
    Sized(Option<int>),
}

fun same<T: Eq>(a: Option<T>, b: Option<T>) -> bool {
    return a == b
}

fun both<T: Eq, E: Eq>(a: Result<T, E>, b: Result<T, E>) -> bool {
    return a == b && !(a != b)
}

fun first_even(xs: [int]) -> Option<int> {
    for x in xs {
        if x % 2 == 0 { return Some(x) }
    }
    return None
}

fun main() {
    let a: Option<int> = Some(3)
    print(a == Some(3))
    print(a == Some(4))
    print(a == None)
    print(a != None)
    print(None == a)
    let n: Option<int> = None
    print(n == None)
    print(n != Some(0))
    let r: Result<int, str> = Ok(1)
    print(r == Ok(1))
    print(r == Err("x"))
    let e: Result<int, str> = Err("bad")
    print(e == Err("bad"))
    print(e != Err("worse"))
    print(Ok(1) == r)
    let nested: Option<Option<P>> = Some(Some(P { x: 1, name: "a" }))
    print(nested == Some(Some(P { x: 1, name: "a" })))
    print(nested == Some(Some(P { x: 1, name: "b" })))
    print(nested == Some(None))
    let rs: Result<Option<str>, int> = Ok(None)
    print(rs == Ok(None))
    print(rs == Ok(Some("")))
    let xs: [Option<int>] = [Some(1), None]
    print(xs == [Some(1), None])
    print(xs == [None, Some(1)])
    let t: (Option<str>, Result<int, str>) = (Some("a"), Ok(2))
    print(t == (Some("a"), Ok(2)))
    print(t == (Some("a"), Err("2")))
    let h = Holder { tag: Some("t"), res: Ok(2) }
    print(h == Holder { tag: Some("t"), res: Ok(2) })
    print(h == Holder { tag: None, res: Ok(2) })
    print(Shape.Sized(Some(2)) == Shape.Sized(Some(2)))
    print(Shape.Sized(None) != Shape.Sized(Some(2)))
    print(Shape.Dot == Shape.Sized(None))
    print(same(Some("x"), Some("x")))
    print(same<int>(None, Some(1)))
    print(same(Some([1, 2]), Some([1, 2])))
    let ok: Result<int, str> = Ok(5)
    print(both(ok, Ok(5)))
    print(both(ok, Err("5")))
    print(first_even([1, 3, 4]) == Some(4))
    print(first_even([1, 3]) == None)
    let m = ["a": 1]
    print(m.get("a") == Some(1))
    print(m.get("b") == None)
    print(xs.contains(None))
    let zero = 0.0
    let nan: Option<float> = Some(zero / zero)
    print(nan == nan)
    print(Some(0.0) == Some(-0.0))
    var count = 0
    for v in [Some(1), None, Some(1), Some(2)] {
        if v == Some(1) { count += 1 }
    }
    print(count)
}
""",
    # MYLA-379: `#derive(Eq, Hash)` on generic structs and enums, as `==` and map keys
    "derive_on_generic_types": r"""// MYLA-379: `#derive(Eq, Hash)` on generic structs and enums, the impl
// bounded by `T: Eq` / `T: Hash`: `==`, map keys, nesting, recursion,
// generic code and a derived type holding a generic one
#derive(Eq, Hash)
struct Pair<A, B> {
    a: A,
    b: B,
}

#derive(Eq, Hash)
enum Tree<T> {
    Leaf,
    Node(T, [Tree<T>]),
}

#derive(Eq)
struct Grid<T> {
    w: int,
    cells: [T],
}

#derive(Eq, Hash)
enum Either<L, R> {
    Left(L),
    Right(R),
}

#derive(Eq, Hash)
struct Unit<T> {
}

#derive(Eq, Hash)
struct Cell {
    at: Pair<int, int>,
    mark: Either<char, str>,
}

#derive(Eq)
struct Measured<T> {
    value: T,
    weight: float,
}

fun count_distinct<K: Eq + Hash>(xs: [K]) -> int {
    var seen: [K: bool] = [:]
    for x in xs { seen[x] = true }
    return seen.len()
}

fun eq_twice<T: Eq>(a: T, b: T) -> bool {
    return a == b && !(a != b)
}

fun main() {
    let p = Pair { a: 1, b: "x" }
    print(p == Pair { a: 1, b: "x" })
    print(p == Pair { a: 2, b: "x" })
    print(p != Pair { a: 1, b: "y" })
    let deep = Pair { a: Pair { a: 'c', b: [1, 2] }, b: Some(true) }
    print(deep == Pair { a: Pair { a: 'c', b: [1, 2] }, b: Some(true) })
    print(deep == Pair { a: Pair { a: 'c', b: [1] }, b: Some(true) })
    let t1: Tree<int> = Tree.Node(1, [Tree.Leaf, Tree.Node(2, [])])
    let t2: Tree<int> = Tree.Node(1, [Tree.Leaf, Tree.Node(2, [])])
    let t3: Tree<int> = Tree.Node(1, [Tree.Leaf, Tree.Node(3, [])])
    print(t1 == t2)
    print(t1 == t3)
    let leaf: Tree<int> = Tree.Leaf
    print(leaf == Tree.Leaf)
    let g = Grid { w: 2, cells: ["a", "b", "c", "d"] }
    print(g == Grid { w: 2, cells: ["a", "b", "c", "d"] })
    print(g == Grid { w: 4, cells: ["a", "b", "c", "d"] })
    let l: Either<int, str> = Either.Left(1)
    print(l == Either.Left(1))
    print(l == Either.Right("1"))
    let u1: Unit<str> = Unit {}
    let u2: Unit<str> = Unit {}
    print(u1 == u2)
    let c = Cell { at: Pair { a: 0, b: 1 }, mark: Either.Left('#') }
    print(c == Cell { at: Pair { a: 0, b: 1 }, mark: Either.Left('#') })
    print(c == Cell { at: Pair { a: 0, b: 1 }, mark: Either.Right("#") })
    let zero = 0.0
    let m1 = Measured { value: "w", weight: zero / zero }
    print(m1 == m1)
    print(Measured { value: 1, weight: 0.5 } == Measured { value: 1, weight: 0.5 })
    print(eq_twice(p, Pair { a: 1, b: "x" }))
    print(eq_twice(t1, t3))
    // map keys
    var at: [Pair<int, int>: str] = [:]
    at[Pair { a: 1, b: 2 }] = "one-two"
    at[Pair { a: 2, b: 1 }] = "two-one"
    at[Pair { a: 1, b: 2 }] = "again"
    print(at.len())
    print(at[Pair { a: 1, b: 2 }])
    print(at.contains(Pair { a: 2, b: 1 }))
    print(at.contains(Pair { a: 2, b: 2 }))
    var trees: [Tree<str>: int] = [:]
    trees[Tree.Node("r", [Tree.Leaf])] = 1
    trees[Tree.Leaf] = 2
    trees[Tree.Node("r", [Tree.Leaf])] = 3
    print(trees.len())
    print(trees.get_or(Tree.Node("r", [Tree.Leaf]), 0))
    var cells: [Cell: int] = [:]
    cells[c] = 7
    print(cells.get_or(Cell { at: Pair { a: 0, b: 1 }, mark: Either.Left('#') }, 0))
    print(cells.get_or(Cell { at: Pair { a: 0, b: 1 }, mark: Either.Right("#") }, 0))
    let es: [Either<int, str>] = [Either.Left(1), Either.Right("a"), Either.Left(1), Either.Right("b")]
    print(count_distinct(es))
    print(count_distinct([(Pair { a: 1, b: 'a' }, 2), (Pair { a: 1, b: 'a' }, 2)]))
    let h1 = Hasher { state: 0 }.add(Pair { a: 1, b: "x" }).finish()
    let h2 = Hasher { state: 0 }.add(Pair { a: 1, b: "x" }).finish()
    print(h1 == h2)
}
""",
    # MYLA-379: `#derive(Json)` on generic structs and enums, round trips
    "json_derive_generic": r"""// MYLA-379: `#derive(Json)` on generic structs and enums, bounded by
// `T: ToJson` and `T: FromJson`
import std.json as json
from std.json import JsonError

#derive(Json, Eq)
struct Page<T> {
    items: [T],
    next: Option<str>,
}

#derive(Json, Eq)
struct Point {
    x: int,
    y: int,
}

#derive(Json, Eq)
enum Tagged<A, B> {
    Nothing,
    One(A),
    Two(A, B),
}

fun main() {
    let p = Page { items: [Point { x: 1, y: 2 }, Point { x: 3, y: 4 }], next: Some("p2") }
    let text = json.encode(p)
    print(text)
    let back: Result<Page<Point>, JsonError> = json.decode<Page<Point>>(text)
    match back {
        Ok(q) => { print(q == p) },
        Err(e) => { print(e.message()) },
    }
    let words = Page { items: ["a", "b"], next: None }
    print(json.encode(words))
    match json.decode<Page<str>>("{\"items\": [\"x\"]}") {
        Ok(q) => { print(q.items[0]) },
        Err(e) => { print(e.message()) },
    }
    match json.decode<Page<int>>("{\"items\": [\"x\"]}") {
        Ok(q) => { print(q.items.len()) },
        Err(e) => { print(e.message()) },
    }
    let ts: [Tagged<int, str>] = [Tagged.Nothing, Tagged.One(1), Tagged.Two(2, "b")]
    let tt = json.encode(ts)
    print(tt)
    match json.decode<[Tagged<int, str>]>(tt) {
        Ok(back2) => { print(back2 == ts) },
        Err(e) => { print(e.message()) },
    }
    let nested: Page<Page<Tagged<Point, bool>>> = Page { items: [Page { items: [Tagged.One(Point { x: 0, y: 0 })], next: None }], next: None }
    let nt = json.encode(nested)
    print(nt)
    let nb: Result<Page<Page<Tagged<Point, bool>>>, JsonError> = json.decode<Page<Page<Tagged<Point, bool>>>>(nt)
    match nb {
        Ok(v) => { print(v == nested) },
        Err(e) => { print(e.message()) },
    }
}
""",
    # D172 (MYLA-385): `#derive(Json)`, nested structs, lists, maps, an `Option` field absent and present, every built-in type, round trips
    "json_derive_structs": r"""// D172 (MYLA-385): `#derive(Json)` on structs: nested structs, lists, maps,
// an `Option` field absent and present, the built-in types, round trips
import std.json as json
from std.json import Json, JsonError, ToJson

#derive(Json)
struct Point {
    x: int,
    y: int,
}

#derive(Json)
struct Item {
    name: str,
    at: Point,
    tags: [str],
    label: Option<str>,
    counts: [str: int64],
}

#derive(Json)
struct Order {
    id: uint32,
    items: [Item],
    note: Option<Point>,
}

#derive(Json)
struct Scalars {
    small: int8,
    byte: uint8,
    wide: int64,
    huge: uint64,
    ratio: float64,
    single: float32,
    flag: bool,
    letter: char,
    raw: Json,
    maybe: Option<[int]>,
}

#derive(Json)
struct Empty {}

fun show<T: ToJson>(v: T) {
    print(json.encode(v))
}

fun main() {
    let p = Point { x: 1, y: -2 }
    show(p)
    let a = Item { name: "a", at: p, tags: ["t1", "t2"], label: None, counts: ["k": 3, "j": 4] }
    let b = Item { name: "b\"q", at: Point { x: 0, y: 0 }, tags: [], label: Some("lbl"), counts: [:] }
    let o = Order { id: 4000000000, items: [a, b], note: None }
    let text = json.encode(o)
    print(text)
    // back again, and written the same
    match json.decode<Order>(text) {
        Ok(back) => {
            print(json.encode(back) == text)
            print(back.items[1].label.unwrap_or("none"))
            print(back.items[0].label.is_none())
            print(back.items[0].counts["j"])
            print(back.id)
        }
        Err(e) => print(f"error {e}")
    }
    // the expected type gives the type, too
    let q: Result<Point, JsonError> = json.decode("{\"y\": 5, \"x\": 4, \"z\": [true]}")
    match q {
        Ok(v) => print(f"{v.x} {v.y}")
        Err(e) => print(f"error {e}")
    }
    // an Option field from null, and from absent
    match json.decode<Order>("{\"id\": 1, \"items\": [], \"note\": null}") {
        Ok(v) => print(v.note.is_none())
        Err(e) => print(f"error {e}")
    }
    match json.decode<Order>("{\"id\": 2, \"items\": [], \"note\": {\"x\": 7, \"y\": 8}}") {
        Ok(v) => print(v.note.map((n: Point) => n.x + n.y).unwrap_or(0))
        Err(e) => print(f"error {e}")
    }
    let nan = 0.0 / 0.0
    let s = Scalars { small: -128, byte: 255, wide: -9000000000, huge: 18446744073709551615, ratio: nan, single: 0.1, flag: true, letter: 'é', raw: Json.Array([Json.Null, Json.Int(1)]), maybe: Some([1, 2]) }
    print(json.encode(s))
    let s2 = Scalars { small: 127, byte: 0, wide: 9223372036854775807, huge: 9223372036854775808, ratio: 2.5, single: 1.5, flag: false, letter: 'x', raw: Json.Null, maybe: None }
    let t2 = json.encode(s2)
    print(t2)
    match json.decode<Scalars>(t2) {
        Ok(v) => {
            print(json.encode(v) == t2)
            print(v.huge)
            print(v.single)
            print(v.letter)
        }
        Err(e) => print(f"error {e}")
    }
    // an integer reads as a float
    match json.decode<Scalars>("{\"small\":1,\"byte\":2,\"wide\":3,\"huge\":4,\"ratio\":5,\"single\":6,\"flag\":true,\"letter\":\"z\",\"raw\":{}}") {
        Ok(v) => print(f"{v.ratio} {v.single} {v.huge}")
        Err(e) => print(f"error {e}")
    }
    show(Empty {})
    print(json.decode<Empty>("{\"anything\": 1}").is_ok())
    // the built-in types alone
    show([[1, 2], [3]])
    show(["a": Some(1), "b": None])
    show('c')
    let none: Option<int> = None
    show(none)
    print(json.decode<[str: [bool]]>("{\"x\": [true, false], \"y\": []}").map((m: [str: [bool]]) => m["x"].len()).unwrap_or(-1))
    print(int8.from_json(Json.Int(-5)).unwrap_or(0))
    print(json.decode<Option<int>>("null").map((v: Option<int>) => v.is_none()).unwrap_or(false))
}
""",
    # D172 (MYLA-385): `#derive(Json)`, enums externally tagged, every variant shape, inside structs and lists
    "json_derive_enums": r"""// D172 (MYLA-385): `#derive(Json)` on enums, externally tagged: `"Red"`
// for a variant without payload, `{"Dot": x}` for one, `{"Line": [a, b]}`
// for several; inside structs and lists, and back
import std.json as json
from std.json import Json

#derive(Json)
struct Point {
    x: int,
    y: int,
}

#derive(Json)
enum Shape {
    Empty,
    Dot(Point),
    Circle(Point, float64),
    Line(Point, Point, str),
    Tagged(Option<str>),
}

#derive(Json)
enum Color {
    Red,
    Green,
    Blue,
}

#derive(Json)
struct Layer {
    color: Color,
    shapes: [Shape],
    hidden: Option<Color>,
}

fun main() {
    let o = Point { x: 0, y: 0 }
    let shapes = [Shape.Empty, Shape.Dot(Point { x: 1, y: 2 }), Shape.Circle(o, 1.5), Shape.Line(o, Point { x: 3, y: 4 }, "edge"), Shape.Tagged(None), Shape.Tagged(Some("t"))]
    for s in shapes {
        print(json.encode(s))
    }
    let layer = Layer { color: Color.Green, shapes: shapes, hidden: Some(Color.Blue) }
    let text = json.encode(layer)
    print(text)
    match json.decode<Layer>(text) {
        Ok(back) => {
            print(json.encode(back) == text)
            print(back.shapes.len())
            match back.shapes[3] {
                Line(a, b, label) => print(f"{b.x} {b.y} {label}")
                _ => print("not a line")
            }
            match back.color {
                Green => print("green")
                _ => print("other")
            }
        }
        Err(e) => print(f"error {e}")
    }
    // Option of an enum, and the `Some` payload of one
    let c: Option<Color> = Some(Color.Red)
    print(json.encode(c))
    print(json.encode([Color.Red, Color.Blue]))
    match json.decode<[Color]>("[\"Blue\", \"Red\", \"Green\"]") {
        Ok(cs) => print(json.encode(cs))
        Err(e) => print(f"error {e}")
    }
    match json.decode<Shape>("{\"Circle\": [{\"x\": 5, \"y\": 6}, 2]}") {
        Ok(s) => print(json.encode(s))
        Err(e) => print(f"error {e}")
    }
    print(json.pretty(Shape.Dot(o).to_json()))
}
""",
    # D172 (MYLA-385): `#derive(Json)`, recursive types: a tree of structs, an enum through lists, mutual recursion
    "json_derive_recursive": r"""// D172 (MYLA-385): `#derive(Json)` on recursive types: a tree of structs
// through a list, an enum through a list and an Option, mutual recursion
import std.json as json

#derive(Json)
struct Tree {
    label: str,
    kids: [Tree],
}

#derive(Json)
enum Expr {
    Num(int64),
    Neg([Expr]),
    Sum([Expr]),
    Call(str, [Expr]),
}

#derive(Json)
struct Dir {
    name: str,
    files: [File],
    parent: Option<[Dir]>,
}

#derive(Json)
struct File {
    name: str,
    owner: Option<[Dir]>,
}

fun size(t: Tree) -> int {
    var n = 1
    for k in t.kids { n += size(k) }
    return n
}

fun eval(e: Expr) -> int64 {
    return match e {
        Num(n) => n
        Neg(xs) => -eval(xs[0])
        Sum(xs) => {
            var s: int64 = 0
            for x in xs { s += eval(x) }
            s
        }
        Call(name, args) => args.len() as int64
    }
}

fun main() {
    let t = Tree { label: "root", kids: [Tree { label: "a", kids: [] }, Tree { label: "b", kids: [Tree { label: "c", kids: [] }] }] }
    let text = json.encode(t)
    print(text)
    match json.decode<Tree>(text) {
        Ok(back) => print(f"{size(back)} {json.encode(back) == text}")
        Err(e) => print(f"error {e}")
    }
    let e = Expr.Sum([Expr.Num(1), Expr.Neg([Expr.Num(5)]), Expr.Call("f", [Expr.Num(2), Expr.Num(3)])])
    let et = json.encode(e)
    print(et)
    match json.decode<Expr>(et) {
        Ok(back) => print(eval(back))
        Err(err) => print(f"error {err}")
    }
    let d = Dir { name: "src", files: [File { name: "a.my", owner: None }], parent: Some([Dir { name: "/", files: [], parent: None }]) }
    let dt = json.encode(d)
    print(dt)
    match json.decode<Dir>(dt) {
        Ok(back) => print(json.encode(back) == dt)
        Err(err) => print(f"error {err}")
    }
}
""",
    # D172 (MYLA-385): `#derive(Json)`, decoding errors with their paths and kinds
    "json_derive_errors": r"""// D172 (MYLA-385): decoding errors carry their path: a missing field, a
// wrong type, an integer out of range, an unknown variant, a payload of the
// wrong size, a syntax error, each with its kind
import std.json as json
from std.json import Json, JsonError, JsonErrorKind

#derive(Json)
struct Item {
    label: str,
    level: int8,
}

#derive(Json)
enum Kind {
    Plain,
    Pair(int, int),
    One(Item),
}

#derive(Json)
struct Doc {
    items: [Item],
    kinds: [Kind],
    extra: [str: uint8],
    note: Option<Item>,
}

fun kind_name(k: JsonErrorKind) -> str {
    return match k {
        Syntax => "syntax"
        MissingField => "missing field"
        WrongType => "wrong type"
        OutOfRange => "out of range"
        UnknownVariant => "unknown variant"
    }
}

fun try_doc(text: str) {
    match json.decode<Doc>(text) {
        Ok(d) => print(f"ok {d.items.len()}")
        Err(e) => print(f"{kind_name(e.kind)} at {e.path}: {e.msg} | {e}")
    }
}

fun main() {
    let good = "{\"items\": [{\"label\": \"a\", \"level\": 1}], \"kinds\": [\"Plain\", {\"Pair\": [1, 2]}], \"extra\": {}}"
    try_doc(good)
    try_doc("{\"items\": [{\"label\": \"a\", \"level\": 1}, {\"label\": \"b\", \"level\": 2}, {\"level\": 3}], \"kinds\": [], \"extra\": {}}")
    try_doc("{\"items\": [{\"label\": \"a\", \"level\": 1}, {\"label\": \"b\", \"level\": 2}, {\"label\": 5, \"level\": 3}], \"kinds\": [], \"extra\": {}}")
    try_doc("{\"items\": [{\"label\": \"a\", \"level\": 128}], \"kinds\": [], \"extra\": {}}")
    try_doc("{\"items\": [{\"label\": \"a\", \"level\": -129}], \"kinds\": [], \"extra\": {}}")
    try_doc("{\"items\": [{\"label\": \"a\", \"level\": 1.5}], \"kinds\": [], \"extra\": {}}")
    try_doc("{\"items\": [], \"kinds\": [\"Plain\", \"Square\"], \"extra\": {}}")
    try_doc("{\"items\": [], \"kinds\": [{\"Pair\": [1]}], \"extra\": {}}")
    try_doc("{\"items\": [], \"kinds\": [{\"Pair\": [1, true]}], \"extra\": {}}")
    try_doc("{\"items\": [], \"kinds\": [\"Pair\"], \"extra\": {}}")
    try_doc("{\"items\": [], \"kinds\": [{\"Plain\": 1}], \"extra\": {}}")
    try_doc("{\"items\": [], \"kinds\": [{\"One\": {\"label\": \"x\"}}], \"extra\": {}}")
    try_doc("{\"items\": [], \"kinds\": [{\"a\": 1, \"b\": 2}], \"extra\": {}}")
    try_doc("{\"items\": [], \"kinds\": [], \"extra\": {\"ok\": 1, \"a b\": 300}}")
    try_doc("{\"items\": [], \"kinds\": [], \"extra\": {}, \"note\": {\"label\": null, \"level\": 0}}")
    try_doc("{\"items\": {}, \"kinds\": [], \"extra\": {}}")
    try_doc("{\"kinds\": [], \"extra\": {}}")
    try_doc("[]")
    try_doc("{\"items\": [,]}")
    let r: Result<char, JsonError> = json.decode("\"ab\"")
    match r {
        Ok(c) => print(c)
        Err(e) => print(f"{e}")
    }
    match json.decode<uint64>("1e30") {
        Ok(n) => print(n)
        Err(e) => print(f"{e}")
    }
    match json.decode<uint64>("-1") {
        Ok(n) => print(n)
        Err(e) => print(f"{e}")
    }
    match json.decode<int>("2147483648") {
        Ok(n) => print(n)
        Err(e) => print(f"{e}")
    }
    match json.decode<uint64>("18446744073709549568.0") {
        Ok(n) => print(n)
        Err(e) => print(f"{e}")
    }
    // a hand-built error, as a FromJson impl written by hand makes one
    let mine = json.wrong_type("a color", Json.Int(3))
    print(f"{mine}")
}
""",
    # MYLA-407: `#derive(Toml)` on structs: nested, lists, maps, arrays of tables, `Option` fields, dates, the built-in types, round trips
    "toml_derive_structs": r"""// MYLA-407: `#derive(Toml)` on structs: nested structs, lists, maps, arrays
// of tables, an `Option` field absent and present, dates and times, the
// built-in types, round trips through the document's text
import std.toml as toml
from std.toml import Toml, TomlError, TomlDate, TomlDateTime, ToToml

#derive(Toml, Eq)
struct Point {
    x: int,
    y: int,
}

#derive(Toml)
struct Server {
    name: str,
    at: Point,
    ports: [uint16],
    labels: [str: str],
    backup: Option<str>,
}

#derive(Toml)
struct Config {
    title: str,
    version: int64,
    ratio: float64,
    enabled: bool,
    letter: char,
    created: TomlDateTime,
    day: TomlDate,
    servers: [Server],
    owner: Option<Point>,
    tags: [str: [int8]],
}

#derive(Toml)
struct Scalars {
    small: int8,
    byte: uint8,
    wide: int64,
    huge: uint64,
    single: float32,
    limit: float64,
    raw: Toml,
}

#derive(Toml, Eq)
struct Empty {}

fun show(r: Result<str, TomlError>) {
    match r {
        Ok(t) => { print(t) },
        Err(e) => { print(f"{e}") },
    }
}

fun main() {
    let text = "title = \"demo\"\nversion = 3\nratio = 0.5\nenabled = true\nletter = 'é'\ncreated = 1979-05-27T07:32:00-08:00\nday = 2024-02-29\nowner = { x = 1, y = 2 }\n\n[[servers]]\nname = \"alpha\"\nat = { x = 10, y = 20 }\nports = [80, 443]\nlabels = { env = \"prod\", \"a b\" = \"c\" }\n\n[[servers]]\nname = \"beta\"\nat.x = 0\nat.y = -1\nports = []\nlabels = {}\nbackup = \"alpha\"\nextra = [true]\n\n[tags]\na = [1, -2]\n"
    match toml.decode<Config>(text) {
        Ok(c) => {
            print(f"{c.title} {c.version} {c.ratio} {c.enabled} {c.letter}")
            print(c.created.offset == Some(-480))
            print(c.day.year * 10000 + c.day.month * 100 + c.day.day)
            print(c.servers.len())
            print(c.servers[0].backup == None)
            print(c.servers[1].backup == Some("alpha"))
            print(c.servers[1].at == Point { x: 0, y: -1 })
            print(c.servers[0].labels["a b"])
            match c.owner {
                Some(p) => { print(p.x + p.y) },
                None => { print("no owner") },
            }
            let written = toml.encode(c)
            show(written)
            match written {
                Ok(t) => {
                    match toml.decode<Config>(t) {
                        Ok(d) => { print(toml.encode(d) == written) },
                        Err(e) => { print(f"{e}") },
                    }
                },
                Err(e) => {},
            }
        },
        Err(e) => { print(f"{e}") },
    }
    let s = Scalars { small: -128, byte: 255, wide: -9000000000, huge: 9223372036854775808u64, single: 0.1f32, limit: -1.0 / 0.0, raw: Toml.Array([Toml.Int(1), Toml.Str("x")]) }
    let st = toml.encode(s)
    show(st)
    match st {
        Ok(t) => {
            match toml.decode<Scalars>(t) {
                Ok(b) => { print(f"{b.small} {b.byte} {b.wide} {b.huge} {b.single} {b.limit} {toml.inline_string(b.raw)}") },
                Err(e) => { print(f"{e}") },
            }
        },
        Err(e) => {},
    }
    // beyond int64, a uint64 is the nearest float, read back only if exact
    print(toml.inline_string(18446744073709551615u64.to_toml()))
    show(toml.encode(Empty {}))
    print(toml.decode<Empty>("") == Ok(Empty {}))
    // keys the type hasn't are ignored
    print(toml.decode<Point>("x = 1\ny = 2\nz = [true]") == Ok(Point { x: 1, y: 2 }))
    // a map of derived values
    let ps: [str: Point] = ["a": Point { x: 1, y: 2 }, "b c": Point { x: 3, y: 4 }]
    show(toml.encode(ps))
}
""",
    # MYLA-407: `#derive(Toml)` on enums, externally tagged; a variant with a payload is a document, one without isn't
    "toml_derive_enums": r"""// MYLA-407: `#derive(Toml)` on enums, externally tagged as `#derive(Json)`
// is: `"Red"` for a variant without payload, `{ Dot = x }` for one with
// one, `{ Line = [a, b, c] }` for one with more; a variant with a payload is
// a table, so a document of its own, one without isn't
import std.toml as toml
from std.toml import Toml, TomlError, ToToml

#derive(Toml, Eq)
enum Color {
    Red,
    Green,
    Blue,
}

#derive(Toml, Eq)
struct Point {
    x: int,
    y: int,
}

#derive(Toml, Eq)
enum Shape {
    Empty,
    Dot(Point),
    Circle(Point, float64),
    Line(Point, Point, str),
}

#derive(Toml, Eq)
struct Scene {
    color: Color,
    shapes: [Shape],
    hidden: Option<Color>,
}

fun show(r: Result<str, TomlError>) {
    match r {
        Ok(t) => { print(t) },
        Err(e) => { print(f"{e}") },
    }
}

fun main() {
    let shapes = [Shape.Empty, Shape.Dot(Point { x: 1, y: 2 }), Shape.Circle(Point { x: 0, y: 0 }, 1.5), Shape.Line(Point { x: 0, y: 0 }, Point { x: 3, y: 4 }, "edge")]
    for s in shapes { print(toml.inline_string(s.to_toml())) }
    let scene = Scene { color: Color.Green, shapes: shapes, hidden: Some(Color.Blue) }
    let text = toml.encode(scene)
    show(text)
    match text {
        Ok(t) => {
            match toml.decode<Scene>(t) {
                Ok(back) => { print(back == scene) },
                Err(e) => { print(f"{e}") },
            }
        },
        Err(e) => {},
    }
    show(toml.encode(Shape.Dot(Point { x: 5, y: 6 })))
    show(toml.encode(Color.Red))
    match toml.decode<Shape>("Line = [{ x = 1, y = 1 }, { x = 2, y = 2 }, \"d\"]") {
        Ok(Shape.Line(a, b, label)) => { print(f"{b.x - a.x} {label}") },
        Ok(other) => { print("another shape") },
        Err(e) => { print(f"{e}") },
    }
    // written by hand: an integer where a float goes
    match toml.decode<Scene>("color = \"Red\"\nshapes = [\"Empty\", { Circle = [{ x = 5, y = 6 }, 2] }]\n") {
        Ok(s) => {
            print(s.hidden == None)
            print(toml.inline_string(s.shapes.to_toml()))
        },
        Err(e) => { print(f"{e}") },
    }
    print(toml.inline_string([Color.Blue, Color.Red].to_toml()))
}
""",
    # MYLA-407: `#derive(Toml)` on generic types (bounded per parameter, MYLA-379) and recursive ones
    "toml_derive_generic": r"""// MYLA-407: `#derive(Toml)` on generic structs and enums, bounded by
// `T: ToToml` and `T: FromToml` (as MYLA-379 bounds Eq, Hash and Json), and
// on recursive types
import std.toml as toml
from std.toml import Toml, TomlError, ToToml

#derive(Toml, Eq)
struct Page<T> {
    items: [T],
    next: Option<str>,
}

#derive(Toml, Eq)
struct Point {
    x: int,
    y: int,
}

#derive(Toml, Eq)
enum Tagged<A, B> {
    Nothing,
    One(A),
    Two(A, B),
}

#derive(Toml, Eq)
struct Tree {
    label: str,
    kids: [Tree],
}

#derive(Toml, Eq)
enum Expr {
    Num(int64),
    Sum([Expr]),
    Call(str, [Expr]),
}

fun eval(e: Expr) -> int64 {
    return match e {
        Num(n) => n
        Sum(xs) => {
            var t: int64 = 0
            for x in xs { t += eval(x) }
            t
        }
        Call(f, xs) => -eval(Expr.Sum(xs))
    }
}

fun show(r: Result<str, TomlError>) {
    match r {
        Ok(t) => { print(t) },
        Err(e) => { print(f"{e}") },
    }
}

fun main() {
    let p = Page { items: [Point { x: 1, y: 2 }, Point { x: 3, y: 4 }], next: Some("p2") }
    let text = toml.encode(p)
    show(text)
    match text {
        Ok(t) => {
            let back: Result<Page<Point>, TomlError> = toml.decode<Page<Point>>(t)
            match back {
                Ok(q) => { print(q == p) },
                Err(e) => { print(f"{e}") },
            }
        },
        Err(e) => {},
    }
    show(toml.encode(Page { items: ["a", "b"], next: None }))
    match toml.decode<Page<int>>("items = [\"x\"]") {
        Ok(q) => { print(q.items.len()) },
        Err(e) => { print(f"{e}") },
    }
    let ts: [Tagged<int, str>] = [Tagged.Nothing, Tagged.One(1), Tagged.Two(2, "b")]
    print(toml.inline_string(ts.to_toml()))
    let wrapped = Page { items: ts, next: None }
    match toml.encode(wrapped) {
        Ok(t) => {
            match toml.decode<Page<Tagged<int, str>>>(t) {
                Ok(b) => { print(b == wrapped) },
                Err(e) => { print(f"{e}") },
            }
        },
        Err(e) => { print(f"{e}") },
    }
    let tree = Tree { label: "root", kids: [Tree { label: "a", kids: [] }, Tree { label: "b", kids: [Tree { label: "c", kids: [] }] }] }
    let tt = toml.encode(tree)
    show(tt)
    match tt {
        Ok(t) => {
            match toml.decode<Tree>(t) {
                Ok(b) => { print(f"{b.kids[1].kids[0].label} {b == tree}") },
                Err(e) => { print(f"{e}") },
            }
        },
        Err(e) => {},
    }
    let e = Expr.Sum([Expr.Num(1), Expr.Call("neg", [Expr.Num(5)]), Expr.Num(2)])
    print(toml.inline_string(e.to_toml()))
    match toml.decode<Expr>(toml.to_string(e.to_toml())) {
        Ok(b) => { print(f"{eval(b)} {b == e}") },
        Err(err) => { print(f"{err}") },
    }
}
""",
    # MYLA-407: decoding errors with their paths, a syntax error's position, encoding a value that isn't a table, an impl by hand
    "toml_derive_errors": r"""// MYLA-407: decoding errors carry their path, a syntax error its line and
// column: a missing field, a wrong type, an integer out of range, a float
// for an integer, an unknown variant, a payload of the wrong size, a variant
// with or without the payload it hasn't, a quoted key, not a table; encoding
// a value that isn't a table; an impl written by hand
import std.toml as toml
from std.toml import Toml, TomlError, TomlErrorKind, ToToml, FromToml

#derive(Toml)
enum Kind {
    Plain,
    Pair(int, int),
    One(Item),
}

#derive(Toml)
struct Item {
    label: str,
    level: int8,
}

#derive(Toml)
struct Doc {
    items: [Item],
    kinds: [Kind],
    extra: [str: uint8],
    note: Option<Item>,
}

struct Celsius {
    degrees: float64,
}

impl ToToml for Celsius {
    fun to_toml(self) -> Toml {
        return Toml.Str(f"{self.degrees}C")
    }
}

impl FromToml for Celsius {
    fun from_toml(t: Toml) -> Result<Celsius, TomlError> {
        return match t {
            Toml.Float(f) => Ok(Celsius { degrees: f })
            _ => Err(toml.wrong_type("a temperature", t))
        }
    }
}

#derive(Toml)
struct Weather {
    at: Celsius,
}

fun kind_name(k: TomlErrorKind) -> str {
    return match k {
        Syntax => "syntax"
        MissingField => "missing field"
        WrongType => "wrong type"
        OutOfRange => "out of range"
        UnknownVariant => "unknown variant"
    }
}

fun try(text: str) {
    match toml.decode<Doc>(text) {
        Ok(d) => { print(f"ok {d.items.len()}") },
        Err(e) => { print(f"{kind_name(e.kind)} at {e.path}: {e.message()} | {e}") },
    }
}

fun main() {
    let base = "kinds = []\nextra = {}\n"
    try(base + "items = [{ label = \"a\", level = 1 }]")
    try(base + "items = [{ label = \"a\", level = 1 }, { label = \"b\", level = 2 }, { level = 3 }]")
    try(base + "[[items]]\nlabel = \"a\"\nlevel = 1\n[[items]]\nlabel = \"b\"\nlevel = 2\n[[items]]\nlabel = 5\nlevel = 3\n")
    try(base + "items = [{ label = \"a\", level = 128 }]")
    try(base + "items = [{ label = \"a\", level = -129 }]")
    try(base + "items = [{ label = \"a\", level = 1.0 }]")
    try("items = []\nextra = {}\nkinds = [\"Plain\", \"Square\"]")
    try("items = []\nextra = {}\nkinds = [{ Pair = [1] }]")
    try("items = []\nextra = {}\nkinds = [{ Pair = [1, true] }]")
    try("items = []\nextra = {}\nkinds = [\"Pair\"]")
    try("items = []\nextra = {}\nkinds = [{ Plain = 1 }]")
    try("items = []\nextra = {}\nkinds = [{ One = { label = \"x\" } }]")
    try("items = []\nextra = {}\nkinds = [{ Plain = 1, Pair = 2 }]")
    try("items = []\nkinds = []\nextra = { \"a b\" = 300 }")
    try(base + "items = []\nnote = { label = 1979-05-27 }")
    try(base + "items = { a = 1 }")
    try(base)
    try(base + "items = [\n  { label = \"a\", level = 1 },\n  { label = \"b\" level = 2 },\n]")
    match toml.decode<[str: int32]>("n = 2147483648") {
        Ok(m) => { print("fits") },
        Err(e) => { print(f"{e}") },
    }
    match toml.decode<[str: uint64]>("n = -1") {
        Ok(m) => { print("fits") },
        Err(e) => { print(f"{e}") },
    }
    match toml.decode<[str: char]>("c = \"ab\"") {
        Ok(m) => { print("one") },
        Err(e) => { print(f"{e}") },
    }
    match toml.encode(Kind.Plain) {
        Ok(t) => { print(t) },
        Err(e) => { print(f"{kind_name(e.kind)}: {e}") },
    }
    match toml.encode([1, 2]) {
        Ok(t) => { print(t) },
        Err(e) => { print(f"{e}") },
    }
    match toml.encode(Weather { at: Celsius { degrees: 21.5 } }) {
        Ok(t) => { print(t) },
        Err(e) => { print(f"{e}") },
    }
    match toml.decode<Weather>("at = 21.5") {
        Ok(w) => { print(w.at.degrees) },
        Err(e) => { print(f"{e}") },
    }
    match toml.decode<Weather>("at = \"21.5C\"") {
        Ok(w) => { print(w.at.degrees) },
        Err(e) => { print(f"{e}") },
    }
}
""",
    # D172 (MYLA-384): the task's `Zero`: `int.zero()`, a type keyword's
    # `int64.zero()`, a struct's, and `T.zero()` under `T: Zero + Add`
    "trait_functions_zero": """// D172 (MYLA-384): a trait function without `self`, called on a type
// (`int.zero()`, `int64.zero()`, `Money.zero()`) and on a type parameter
// bounded by the trait (`T.zero()`)
trait Zero {
    fun zero() -> Self
}

impl Zero for int {
    fun zero() -> int { return 0 }
}

impl Zero for int64 {
    fun zero() -> int64 { return 0 }
}

impl Zero for float {
    fun zero() -> float { return 0.0 }
}

impl Zero for str {
    fun zero() -> str { return "" }
}

struct Money {
    cents: int64,
}

impl Zero for Money {
    fun zero() -> Money { return Money { cents: 0 } }
}

impl Add for Money {
    fun add(self, other: Money) -> Money { return Money { cents: self.cents + other.cents } }
}

fun total<T: Zero + Add>(xs: [T]) -> T {
    var s = T.zero()
    for x in xs { s = s + x }
    return s
}

fun main() {
    print(int.zero())
    print(int64.zero() + 5000000000)
    print(total([1, 2, 3]))
    print(total([5000000000i64, 1i64]))
    print(total([1.5, 2.25]))
    print(total(["ab", "c"]).len())
    print(total([Money { cents: 150 }, Money { cents: 250 }]).cents)
    let none: [Money] = []
    print(total(none).cents)
    let empty: [int] = []
    print(total(empty))
    print(Money.zero().cents)
}
""",
    # a `Default` over structs, enums and built-in types; `T.default()` in a
    # generic function, a generic method, a generic impl's own function, a
    # list's impl, a lambda keeping its function's `T`
    "trait_functions_default": """// D172 (MYLA-384): a `Default` trait over structs, enums and built-in
// types; `T.default()` in a generic function, a generic method, a generic
// impl's own function (`Box<T>`'s calls its `T`'s), a list's impl, and a
// lambda that keeps its function's `T`
trait Default {
    fun default() -> Self
}

#derive(Eq)
enum Color {
    Red,
    Green,
    Blue,
}

impl Default for Color {
    fun default() -> Color { return Color.Green }
}

impl Default for bool {
    fun default() -> bool { return false }
}

impl Default for int {
    fun default() -> int { return 7 }
}

impl Default for str {
    fun default() -> str { return "none" }
}

impl Default for char {
    fun default() -> char { return 'x' }
}

struct Point {
    x: int,
    y: int,
}

impl Default for Point {
    fun default() -> Point { return Point { x: int.default(), y: 1 } }
}

struct Box<T> {
    v: T,
}

impl<T: Default> Default for Box<T> {
    fun default() -> Box<T> { return Box { v: T.default() } }
}

impl<T: Default> Box<T> {
    fun reset(var self) { self.v = T.default() }

    fun or_default(self, keep: bool) -> T {
        if keep { return self.v }
        return T.default()
    }
}

impl<T: Default> Default for [T] {
    fun default() -> [T] { return [T.default(), T.default()] }
}

fun make<T: Default>() -> T {
    return T.default()
}

fun pair<T: Default>() -> (T, T) {
    return (make(), T.default())
}

fun later<T: Default>() -> () -> T {
    return () => T.default()
}

fun boxed<T: Default>() -> Box<T> {
    return Box.default()
}

fun main() {
    print(Color.default() == Color.Green)
    print(bool.default())
    print(char.default())
    let p = Point.default()
    print(f"{p.x} {p.y}")
    let b: Box<int> = Box.default()
    print(b.v)
    let bs: Box<str> = boxed()
    print(bs.v)
    let bb = boxed<Box<Color>>()
    print(bb.v.v == Color.Green)
    var c = Box { v: 3 }
    c.reset()
    print(c.v)
    print(Box { v: "kept" }.or_default(false))
    print(Box { v: "kept" }.or_default(true))
    let ps = pair<Point>()
    print(ps.0.x + ps.1.y)
    let xs = make<[int]>()
    print(xs.len())
    let nested = make<[Box<char>]>()
    print(nested[1].v)
    let f = later<str>()
    print(f())
    print(later<[Color]>()().len())
}
""",
    # a function taking arguments and returning `Result<Self, E>`, the
    # shape MYLA-385's `FromJson` takes: `?` through nested types, a generic
    # impl for lists
    "trait_functions_parse": """// D172 (MYLA-384): a trait function taking arguments and returning
// `Result<Self, E>`, the shape `FromJson` takes (MYLA-385): a value made
// from text with no value in hand, by its type, `?` through nested
// types, a generic impl for lists, and `T.parse` in generic code
#derive(Eq)
enum ParseError {
    Empty,
    Bad(str),
}

trait Parse {
    fun parse(text: str) -> Result<Self, ParseError>
}

impl Parse for int {
    fun parse(text: str) -> Result<int, ParseError> {
        if text.len() == 0 { return Err(ParseError.Empty) }
        var n = 0
        for c in text {
            if c < '0' || c > '9' { return Err(ParseError.Bad(text)) }
            n = n * 10 + (c - '0')
        }
        return Ok(n)
    }
}

impl Parse for bool {
    fun parse(text: str) -> Result<bool, ParseError> {
        if text == "true" { return Ok(true) }
        if text == "false" { return Ok(false) }
        return Err(ParseError.Bad(text))
    }
}

struct Point {
    x: int,
    y: int,
}

impl Parse for Point {
    fun parse(text: str) -> Result<Point, ParseError> {
        let parts = text.split(",")
        if parts.len() != 2 { return Err(ParseError.Bad(text)) }
        return Ok(Point { x: int.parse(parts[0])?, y: int.parse(parts[1])? })
    }
}

impl<T: Parse> Parse for [T] {
    fun parse(text: str) -> Result<[T], ParseError> {
        var out: [T] = []
        if text.len() == 0 { return Ok(out) }
        for part in text.split(";") { out.push(T.parse(part)?) }
        return Ok(out)
    }
}

fun decode<T: Parse>(text: str) -> Result<T, ParseError> {
    return T.parse(text)
}

fun decode_or<T: Parse>(text: str, fallback: T) -> T {
    return match T.parse(text) {
        Ok(v) => v
        Err(e) => fallback
    }
}

fun why(e: ParseError) -> str {
    return match e {
        Empty => "empty"
        Bad(t) => f"bad '{t}'"
    }
}

fun show(r: Result<Point, ParseError>) -> str {
    return match r {
        Ok(p) => f"({p.x}, {p.y})"
        Err(e) => why(e)
    }
}

fun main() {
    print(int.parse("42").unwrap_or(-1))
    print(int.parse("4x").is_err())
    print(show(Point.parse("3,4")))
    print(show(Point.parse("3,")))
    print(show(Point.parse("3")))
    print(show(decode("10,20")))
    let r: Result<bool, ParseError> = decode("true")
    print(r.unwrap_or(false))
    print(decode_or("nope", true))
    let ps: Result<[Point], ParseError> = decode("1,2;3,4;5,6")
    match ps {
        Ok(xs) => print(xs[2].x + xs[0].y)
        Err(e) => print(why(e))
    }
    let bad: Result<[Point], ParseError> = decode("1,2;x,4")
    match bad {
        Ok(xs) => print(xs.len())
        Err(e) => print(why(e))
    }
    let deep = decode_or<[[int]]>("", [[9]])
    print(deep.len())
    let flags = decode<[bool]>("true;false;true")
    print(flags.is_ok())
    let wrong = decode<[bool]>("true;maybe")
    match wrong {
        Ok(xs) => print(xs.len())
        Err(e) => print(why(e))
    }
}
""",
    # a trait with both methods and functions without `self`, in generic
    # functions, a generic struct's methods and a method's own type parameter
    "trait_functions_with_methods": """// D172 (MYLA-384): a trait with both methods and functions without
// `self`; `T.f()` beside `x.m()` in a generic function, in a generic
// struct's methods (its impl's `T`), in a method with its own type
// parameter, and an operator through the impl
trait Shape {
    fun unit() -> Self
    fun named(label: str, size: int) -> Self
    fun kind() -> str
    fun area(self) -> int
    fun scaled(self, k: int) -> Self
}

struct Sq {
    side: int,
}

struct Rect {
    w: int,
    h: int,
}

impl Shape for Sq {
    fun unit() -> Sq { return Sq { side: 1 } }
    fun named(label: str, size: int) -> Sq { return Sq { side: size + label.len() } }
    fun kind() -> str { return "square" }
    fun area(self) -> int { return self.side * self.side }
    fun scaled(self, k: int) -> Sq { return Sq { side: self.side * k } }
}

impl Shape for Rect {
    fun unit() -> Rect { return Rect { w: 1, h: 2 } }
    fun named(label: str, size: int) -> Rect { return Rect { w: size, h: label.len() } }
    fun kind() -> str { return "rectangle" }
    fun area(self) -> int { return self.w * self.h }
    fun scaled(self, k: int) -> Rect { return Rect { w: self.w * k, h: self.h * k } }
}

fun describe<T: Shape>(x: T) -> str {
    return f"{T.kind()} of {x.area()}, unit {T.unit().area()}"
}

fun grown<T: Shape>(times: int) -> T {
    var s = T.unit()
    var i = 0
    while i < times {
        s = s.scaled(2)
        i += 1
    }
    return s
}

struct Shelf<T> {
    items: [T],
}

impl<T: Shape> Shelf<T> {
    fun add_unit(var self) { self.items.push(T.unit()) }

    fun add_named(var self, label: str) { self.items.push(T.named(label, self.items.len())) }

    fun total(self) -> int {
        var n = 0
        for x in self.items { n += x.area() }
        return n
    }

    fun label(self) -> str { return f"a shelf of {T.kind()}s" }

    fun paired<U: Shape>(self) -> (T, U) { return (T.unit(), U.unit()) }
}

fun main() {
    print(describe(Sq { side: 3 }))
    print(describe(Rect { w: 2, h: 5 }))
    print(grown<Sq>(3).side)
    let r: Rect = grown(2)
    print(r.area())
    var shelf = Shelf { items: [Sq { side: 2 }] }
    shelf.add_unit()
    shelf.add_named("ab")
    print(shelf.total())
    print(shelf.label())
    let empty: Shelf<Rect> = Shelf { items: [] }
    print(empty.label())
    let (a, b) = shelf.paired<Rect>()
    print(a.area() + b.area())
    print(Sq.named("abc", 1).area())
    print(Rect.kind())
}
""",
    # a generic function with `T.default()` that calls itself by `become`
    "trait_functions_become": """// D172 (MYLA-384): `T.default()` in a generic function that `become`s
// itself: the tail call keeps the type its frame binds
trait Default {
    fun default() -> Self
}

impl Default for int {
    fun default() -> int { return 7 }
}

impl Default for str {
    fun default() -> str { return "s" }
}

fun count_down<T: Default>(n: int, acc: [T]) -> [T] {
    if n == 0 { return acc }
    var more = acc
    more.push(T.default())
    become count_down(n - 1, more)
}

fun main() {
    let empty: [str] = []
    print(count_down(3, empty).len())
    let none: [int] = []
    let xs = count_down(100000, none)
    print(xs[99999])
}
""",
    # `T.zero()` in async code: across an `await`, in a child task, in an
    # async function's lambda (the interpreter's async evaluator)
    "trait_functions_async": """// D172 (MYLA-384): `T.zero()` in async code: an async generic function,
// across an `await`, in a child task, and in an async function's lambda
import std.task as task

trait Zero {
    fun zero() -> Self
    fun label() -> str
}

impl Zero for int {
    fun zero() -> int { return 0 }
    fun label() -> str { return "int" }
}

impl Zero for str {
    fun zero() -> str { return "" }
    fun label() -> str { return "str" }
}

struct Pair<T> {
    a: T,
    b: T,
}

impl<T: Zero> Zero for Pair<T> {
    fun zero() -> Pair<T> { return Pair { a: T.zero(), b: T.zero() } }
    fun label() -> str { return "pair of " + T.label() }
}

async fun sum<T: Zero + Add>(xs: [T]) -> T {
    var s = T.zero()
    for x in xs {
        await task.yield()
        s = s + x
    }
    return s
}

async fun named<T: Zero>() -> str {
    await task.yield()
    let f = () => T.label()
    return f()
}

#main
async fun main() {
    print(await sum([1, 2, 3]))
    print(await sum(["a", "b", "c"]))
    async let n = sum([10, 20])
    async let l = named<Pair<Pair<str>>>()
    print(await n)
    print(await l)
    let p: Pair<int> = Pair.zero()
    print(p.a)
}
""",
    # `for c in s` visits a string's characters as `s.chars()` gives them,
    # U+FFFD for a byte that isn't UTF-8 (MYLA-318): ASCII and longer
    # sequences, an empty string, a temporary, break, continue, a return from
    # the loop, the string changed in the body, nested loops, a closure
    # capturing the character, a struct's field
    "for_over_a_string": """// `for c in s` visits the characters of a string, as `s.chars()` does
// (MYLA-318), U+FFFD for a byte that isn't part of a well-formed sequence
fun vowels(s: str) -> int {
    var n = 0
    for c in s {
        if c == 'a' || c == 'e' || c == 'i' || c == 'o' || c == 'u' { n += 1 }
    }
    return n
}

fun first_upper(s: str) -> Option<char> {
    for c in s {
        if c >= 'A' && c <= 'Z' { return Some(c) }
    }
    return None
}

fun greeting(name: str) -> str {
    return "hi " + name
}

fun main() {
    let s = "héllo, wörld 😀!"
    var n = 0
    var sb = StringBuilder()
    for c in s {
        n += 1
        sb.append(f"{c}|")
    }
    print(n)
    print(s.chars().len())
    print(sb.build())
    print(vowels("education"))
    print(first_upper("abcDef").unwrap_or('-'))
    print(first_upper("abc").unwrap_or('-'))
    // an empty string, a temporary, break and continue
    for c in "" { print(c) }
    for c in greeting("bob") {
        if c == ' ' { continue }
        if c == 'b' && n > 100 { break }
        print(c)
    }
    for c in "abcdef" {
        if c == 'd' { break }
        print(c)
    }
    // the loop sees the string it started with
    var t = "xy"
    for c in t {
        t = t + "z"
        print(c)
    }
    print(t)
    // bytes that aren't UTF-8 are U+FFFD each, as in chars()
    var bad = StringBuilder()
    bad.append("a")
    bad.append_byte(255u8)
    bad.append_byte(0xC3u8)
    bad.append("b")
    bad.append_byte(0xE2u8)
    bad.append_byte(0x82u8)
    let b = bad.build()
    var codes: [int] = []
    for c in b { codes.push(c as int) }
    var same: [int] = []
    for c in b.chars() { same.push(c as int) }
    print(codes.map((x: int) => f"{x}").join(","))
    print(codes == same)
    // nested, and a closure capturing the character
    var pairs = 0
    for a in "abc" {
        for z in "xyz" {
            if a != z { pairs += 1 }
        }
    }
    print(pairs)
    var fs: [() -> char] = []
    for c in "qr" { fs.push(() => c) }
    print(fs[1]())
    // a struct's field
    print(count_in(Line { text: "a-b-c", sep: '-' }))
}

struct Line {
    text: str,
    sep: char,
}

fun count_in(l: Line) -> int {
    var k = 0
    for c in l.text {
        if c == l.sep { k += 1 }
    }
    return k
}
""",
    # (the async interpreter's loop holds the characters; native code walks
    # the bytes in the frame)
    "for_over_a_string_async": """import std.task as task

async fun count(s: str) -> int {
    var n = 0
    for c in s {
        await task.yield()
        if c == 'é' { continue }
        n += 1
    }
    return n
}

#main
async fun main() {
    async let a = count("héllo")
    async let b = count("😀😀")
    print(await a + await b)
    for c in "ab" {
        await task.yield()
        print(c)
    }
}
""",
    "wait_with_no_descriptor": """// `await __wait_readable(fd)` with no descriptor to watch (-1) returns at
// once, as natively: the poller can't watch it, so it counts as ready; the
// same for `__wait_either` with its first one -1
import std.task as task

async fun other() -> int {
    await task.yield()
    return 2
}

#allow(primitive)
#main
async fun main() {
    print("before")
    await __wait_readable(-1)
    print("after")
    async let o = other()
    await __wait_either(-1, -1)
    print(await o)
}
""",
    "method_on_a_generic_temporary": """// a method on a temporary whose type is a type parameter: the interpreter
// keys it by the value, as it has no type to go by (MYLA-391)
trait Shape {
    fun area(self) -> int
    fun scaled(self, k: int) -> Self
}
struct Sq {
    side: int,
}
impl Shape for Sq {
    fun area(self) -> int { return self.side * self.side }
    fun scaled(self, k: int) -> Sq { return Sq { side: self.side * k } }
}
fun bigger<T: Shape>(x: T) -> int {
    return x.scaled(2).area()
}
fun twice<T: Shape>(x: T) -> T {
    return x.scaled(2)
}

fun main() {
    print(bigger(Sq { side: 3 }))
    print(twice(Sq { side: 1 }).scaled(5).area())
}
""",
    "generic_code_per_width": """// generic code typed by a type parameter, per integer width and float
// size: arithmetic, comparison, sorting and formatting use the concrete
// type, as natively (MYLA-414, H1)
import std.iter as iter

fun add<T: Add>(a: T, b: T) -> T { return a + b }
fun sub<T: Sub>(a: T, b: T) -> T { return a - b }
fun mul<T: Mul>(a: T, b: T) -> T { return a * b }
fun div<T: Div>(a: T, b: T) -> T { return a / b }
fun rem<T: Rem>(a: T, b: T) -> T { return a % b }
fun less<T: Ord>(a: T, b: T) -> bool { return a < b }
fun show<T: Format>(v: T) -> str { return f"{v}" }
fun shown<T: Format>(o: Option<T>) -> str {
    return match o {
        Some(v) => f"S{v}"
        None => "N"
    }
}
fun largest<T: Ord>(xs: [T]) -> T {
    var m = xs[0]
    for x in xs { if x > m { m = x } }
    return m
}

// each operation on `hi`, the type's largest value, and `lo`, its
// smallest, through the generic functions
fun row<T: Add + Sub + Mul + Div + Rem + Ord + Format>(name: str, hi: T, lo: T, one: T, two: T) {
    let s = [hi, lo, one].sorted()
    let line = f"{name}: {show(sub(hi, one))} {show(add(lo, one))} {show(div(hi, two))} {show(rem(hi, two))} {show(mul(one, two))} {less(lo, hi)} {less(hi, lo)} {show(s[0])} {show(s[2])} {show(largest([one, hi, lo]))} {shown(Some(hi))} {[lo, hi].is_sorted()}"
    print(line)
}

struct Cell<T> { v: T }

impl<T: Add + Ord + Format> Cell<T> {
    fun plus(self, w: T) -> Cell<T> { return Cell { v: self.v + w } }
    fun below(self, w: T) -> bool { return self.v < w }
    fun text(self) -> str { return f"<{self.v}>" }
}

fun main() {
    row("int8", 127i8, -128i8, 1i8, 2i8)
    row("int16", 32767i16, -32768i16, 1i16, 2i16)
    row("int32", 2147483647, -2147483648, 1, 2)
    row("int64", 9223372036854775807i64, -9223372036854775807i64 - 1, 1i64, 2i64)
    row("uint8", 255u8, 0u8, 1u8, 2u8)
    row("uint16", 65535u16, 0u16, 1u16, 2u16)
    row("uint32", 4294967295u32, 0u32, 1u32, 2u32)
    row("uint64", 18446744073709551615u64, 0u64, 1u64, 2u64)
    // the sums of std.list and std.iter, which fit
    let us: [uint64] = [9223372036854775808, 9223372036854775806]
    print(us.sum(0))
    print(us.iter() |> iter.sum(0u64))
    let bs: [uint8] = [100, 155]
    print(bs.sum(0u8))
    print(us.max_by((a, b) => a < b) == Some(9223372036854775808u64))
    // float32 in generic code: rounded to single precision at each step
    let a: float32 = 16777216.0
    print(add(a, 1.0f32) == a)
    print(mul(0.1f32, 0.1f32) as float64)
    let fs: [float32] = [0.1, 0.2, 0.3]
    print(fs.sum(0.0f32) as float64)
    print((fs.iter() |> iter.sum(0.0f32)) as float64)
    print(show(div(1.0f32, 3.0f32)))
    print(show(div(1.0, 3.0)))
    // a generic struct's methods on a uint64 and an int8
    let c = Cell { v: 18446744073709551614u64 }
    print(c.plus(1).text())
    print(c.below(18446744073709551615u64))
    let d = Cell { v: -100i8 }
    print(d.plus(-28).text())
}
""",
    "receivers_of_type_parameter_type": """// receivers of type-parameter type (MYLA-414, H6 and M4): a `var self`
// method on an element of a list or a map changes it there, and a field of
// a call's result finds its method
trait Bump {
    fun bump(var self)
    fun get(self) -> int
}
struct A {
    n: int,
}
impl Bump for A {
    fun bump(var self) { self.n += 1 }
    fun get(self) -> int { return self.n }
}
struct Wrap<R> {
    items: [R],
    m: [int: R],
    inner: R,
}
fun mk<R>(r: R) -> Wrap<R> {
    return Wrap { items: [r], m: [:], inner: r }
}
impl<R: Bump> Wrap<R> {
    fun bump_item(var self, i: int) { self.items[i].bump() }
    fun bump_map(var self, k: int) { self.m[k].bump() }
    fun bump_inner(var self) { self.inner.bump() }
    fun copy(self) -> Wrap<R> { return self }
    fun of_a_call(self) -> int { return mk(self.inner).inner.get() }
    fun of_a_method(self) -> int { return self.copy().inner.get() }
    fun of_an_element(self) -> int { return mk(self.items[0]).items[0].get() }
}
fun bump_first<T: Bump>(xs: [T]) -> int {
    var ys = xs
    ys[0].bump()
    ys[^1].bump()
    return ys[0].get()
}
fun main() {
    var w = Wrap { items: [A { n: 3 }], m: [1: A { n: 10 }], inner: A { n: 30 } }
    w.bump_item(0)
    w.bump_map(1)
    w.bump_inner()
    print(f"{w.items[0].get()} {w.m[1].get()} {w.inner.get()}")
    print(f"{bump_first([A { n: 20 }])} {w.of_a_call()} {w.of_a_method()} {w.of_an_element()}")
}
""",
    "generic_var_self_past_a_written_key": """// MYLA-414 (B6): a `var self` method of generic code called on a map's
// element whose key has a written `eq` or `hash`: finding the key runs it,
// and the method's frame still binds its type parameters
trait Twice {
    fun twice(self) -> Self
}

impl Twice for uint64 {
    fun twice(self) -> uint64 { return self * 2 }
}

#derive(Eq)
struct K {
    v: int,
}

impl Hash for K {
    fun hash(self, h: Hasher) -> Hasher { return h.add(self.v) }
}

#derive(Hash)
struct E {
    v: int,
}

impl Eq for E {
    fun eq(self, other: E) -> bool { return self.v == other.v }
}

struct Cell<T> {
    v: T,
}

impl<T: Twice + Ord> Cell<T> {
    fun grow(var self) { self.v = self.v.twice() }
    fun below(var self, w: T) -> bool { return self.v < w }
}

fun main() {
    // a written `hash`
    var m = [K { v: 1 }: Cell { v: 3u64 }]
    m[K { v: 1 }].grow()
    print(m[K { v: 1 }].v)
    print(m[K { v: 1 }].below(18446744073709551615u64))
    // a written `eq`: std.list's `sort` on a [uint64]
    var n = [E { v: 1 }: [5u64, 18446744073709551615u64, 1u64]]
    n[E { v: 1 }].sort()
    for x in n[E { v: 1 }] { print(x) }
    // two keys deep
    var d = [K { v: 2 }: [E { v: 3 }: [9223372036854775808u64, 7u64]]]
    d[K { v: 2 }][E { v: 3 }].sort()
    for x in d[K { v: 2 }][E { v: 3 }] { print(x) }
    // a plain key, for comparison
    var p = ["a": Cell { v: 9223372036854775807u64 }]
    p["a"].grow()
    print(p["a"].v)
}
""",
    "generic_eq_and_hash_the_interpreter_calls": """// A written `eq` or `hash` of a generic impl, which the interpreter calls
// itself (an element's `==`, a map's key), binds its type parameters
// (MYLA-436): `<` on a uint64 compares unsigned, a uint64 formats unsigned
struct W<T> {
    v: T,
}

impl<T: Ord> Eq for W<T> {
    fun eq(self, other: W<T>) -> bool {
        return !(self.v < other.v)
    }
}

impl<T: Ord + Format> Hash for W<T> {
    fun hash(self, h: Hasher) -> Hasher {
        print(f"hash {self.v}")
        return h.add_str(f"{self.v}")
    }
}

// equal when both are below their bound or both aren't: every key in one
// bucket, so a lookup compares by `eq`
struct K<T> {
    v: T,
    z: T,
}

impl<T: Ord> Eq for K<T> {
    fun eq(self, other: K<T>) -> bool {
        return (self.v < self.z) == (other.v < other.z)
    }
}

impl<T> Hash for K<T> {
    fun hash(self, h: Hasher) -> Hasher {
        return h.add_i32(0)
    }
}

#derive(Eq)
struct P {
    w: W<uint64>,
}

#derive(Eq)
enum E {
    A(W<uint64>),
    B,
}

// an `eq` that finds any two equal
struct A {
    v: int,
}

impl Eq for A {
    fun eq(self, other: A) -> bool {
        return true
    }
}

#derive(Eq)
struct Q {
    a: A,
}

fun main() {
    let x = W { v: 0u64 }
    let y = W { v: 18446744073709551615u64 }
    print(x == y)
    print([x] == [y])
    print((x, 1) == (y, 1))
    print(P { w: x } == P { w: y })
    print([P { w: x }] == [P { w: y }])
    print(P { w: x }.eq(P { w: y }))
    print(E.A(x) == E.A(y))
    print(Some(x) == Some(y))
    print([Some(x)] == [Some(y)])
    print([x].contains(y))
    let m = [y: 1]
    print(m.contains(y))
    print((y, 3).hash(Hasher { state: 0 }).state == (y, 3).hash(Hasher { state: 0 }).state)

    let lo = K { v: 0u64, z: 1u64 }
    let hi = K { v: 18446744073709551615u64, z: 1u64 }
    print(lo == hi)
    print([lo] == [hi])
    var n = [lo: 1]
    print(n.contains(hi))
    n[hi] = 2
    print(n.len())
    n[hi] += 3
    print(n[hi])
    print(n.get_or(lo, 0))
    n.remove(hi)
    print(n.len())
    let t = [(lo, 1): "a"]
    print(t.contains((hi, 1)))

    print(Q { a: A { v: 1 } } == Q { a: A { v: 2 } })
    print(Q { a: A { v: 1 } }.eq(Q { a: A { v: 2 } }))
}
""",
    "map_keys_hashed_once": """// How often a map's key is hashed and compared, by its written `hash` and
// `eq`, which say so: once per index on both runners (MYLA-506)
struct K {
    v: int,
}

impl Eq for K {
    fun eq(self, other: K) -> bool {
        print("eq")
        return self.v == other.v
    }
}

impl Hash for K {
    fun hash(self, h: Hasher) -> Hasher {
        print("hash")
        return h.add(self.v)
    }
}

struct Cell {
    n: int,
    name: str,
}

impl [int] {
    fun bump(var self) {
        self.push(9)
    }
}

impl [K: [int]] {
    fun drop_below(var self, n: int) -> int {
        var i = 0
        while i < n {
            self.remove(K { v: i })
            i += 1
        }
        return n
    }
}

fun one() -> int {
    return 1
}

fun main() {
    let k = K { v: 2 }
    var m = [K { v: 1 }: 1]
    print("-- set")
    m[k] = 2
    print("-- get")
    print(m[k])
    print("-- +=")
    m[k] += 1
    print("-- += of a computed key")
    m[K { v: 2 }] *= 2
    print("-- += of a call")
    m[k] += one()
    print("-- contains, get_or")
    print(m.contains(k))
    print(m.get_or(k, 0))
    var s = [k: "a"]
    print("-- += of a string")
    s[k] += "b"
    print(s[k])
    var n = [k: [1, 2]]
    print("-- nested set")
    n[k][0] = 5
    print("-- push")
    n[k].push(3)
    print("-- nested get")
    print(n[k][2])
    print("-- nested +=")
    n[k][1] += 4
    print("-- var self")
    n[k].bump()
    print(n[k].len())
    var cs = [k: Cell { n: 1, name: "c" }]
    print("-- field set")
    cs[k].n = 3
    print("-- field +=")
    cs[k].n += 4
    cs[k].name += "d"
    print(cs[k].n)
    print(cs[k].name)
    var mm = [k: [k: 1]]
    print("-- map in a map")
    mm[k][k] = 3
    mm[k][k] += 3
    print(mm[k][k])
    var t = [(k, 1): 0]
    print("-- tuple key")
    t[(k, 1)] += 5
    print(t[(k, 1)])
    var big: [K: [int]] = [:]
    var i = 0
    while i < 20 {
        big[K { v: i }] = [i]
        i += 1
    }
    let last = K { v: 19 }
    print("-- keys moved by the argument")
    big[last].push(big.drop_below(17))
    print(big[last][1])
    print("-- remove")
    m.remove(k)
    print(m.contains(k))
}
""",
    "written_hash_and_eq_run_alike": """// MYLA-546: a key's written `hash` and `eq` run in the same order and as
// often on both runners: keys whose hashes collide are compared oldest
// first, a key removed and another added leave that order, and a map
// literal hashes each key after its value, in a nested literal too
struct K {
    v: int,
}

impl Eq for K {
    fun eq(self, other: K) -> bool {
        print(f"eq {self.v} {other.v}")
        return self.v == other.v
    }
}

impl Hash for K {
    fun hash(self, h: Hasher) -> Hasher {
        print(f"hash {self.v}")
        return h.add(self.v % 3)
    }
}

fun key(v: int) -> K {
    print(f"key {v}")
    return K { v: v }
}

fun val(v: int) -> int {
    print(f"val {v}")
    return v
}

fun show(m: [K: int]) {
    var sb = StringBuilder()
    for k in m { sb.append(f"{k.v} ") }
    print(sb.build())
}

fun main() {
    var m: [K: int] = [:]
    for i in 0..7 {
        m[K { v: i }] = i
    }
    show(m)
    print("-- lookups")
    print(m[K { v: 6 }])
    print(m.contains(K { v: 9 }))
    print("-- removed, then added")
    m.remove(K { v: 3 })
    m[K { v: 9 }] = 9
    m[K { v: 12 }] = 12
    show(m)
    print(m[K { v: 12 }])
    print(m.get_or(K { v: 15 }, -1))
    print("-- many removed")
    for i in 0..40 {
        m[K { v: 100 + i }] = i
    }
    for i in 0..36 {
        m.remove(K { v: 100 + i })
    }
    m[K { v: 30 }] = 30
    show(m)
    print(m[K { v: 30 }])
    print("-- literals")
    let n = [key(1): val(1), key(4): val(4), key(1): val(9)]
    print(f"{n.len()} {n[K { v: 1 }]}")
    let d = [key(2): [key(5): val(50), key(8): val(80)], key(11): [key(14): val(140)]]
    print(d.len())
}
""",
    "actor_function_field": """// an actor's field that holds a function, called from the actor's own
// method (MYLA-414, the 2026-11-10 review's L3)
actor A {
    on: (int) -> int,
    n: int,
}

impl A {
    fun run(self, k: int) -> int {
        return self.on(k) + self.n
    }
}

#main
async fun main() {
    let a = A { on: (x: int) => x * 100, n: 5 }
    print(await a.run(12))
}
""",
    "char_literal_typed_uint8": """// a `char` literal where a `uint8` is expected is that number (MYLA-414,
// the 2026-11-10 review's L4)
fun main() {
    let h = ['a', 98u8]
    print(h[0])
    let g = [98u8, 'a']
    print(g[1])
    let x: uint8 = 'a'
    print(x)
    let xs: [uint8] = ['a', 'b']
    print(xs[1])
    print(f"{x} {xs[0] + 1}")
    let s = "abc"
    print(s[0] == 'a')
    print(s[2] - 'a')
    let c = 'a'
    print(c)
}
""",
    "packed_byte_lists": """// a `[uint8]` from `bytes.from_str` and from a stream: the interpreter
// holds it packed (MYLA-414, the 2026-11-10 review's S2), and every use
// of a list works on it as on any other
import std.bytes as bytes
import std.io as io
from std.io import Read

fun main() {
    var b = bytes.from_str("hello")
    print(b.len())
    print(b[1])
    print(b[^1])
    print(bytes.to_str(b[1:3]))
    print(bytes.to_str(b[::-1]))
    print(b == [104u8, 101, 108, 108, 111])
    print([104u8, 101, 108, 108, 111] == b)
    print(b == bytes.from_str("hello"))
    print(b != bytes.from_str("help"))
    var total = 0
    for x in b { total += x as int }
    print(total)
    print(b.contains(108))
    print(b.index_of(111) == Some(4))
    var m: [[uint8]: int] = [:]
    m[b] = 1
    m[[104u8, 105]] = 2
    print(m.get(bytes.from_str("hello")) == Some(1))
    print(m.get(bytes.from_str("hi")) == Some(2))
    b.push(33)
    print(bytes.to_str(b))
    b[0] = 72
    print(bytes.to_str(b))
    print(b.pop())
    print(b.len())
    let s = b.sorted()
    print(s[0])
    var src = io.from_str("abcdef")
    match src.read(4) {
        Ok(c) => {
            print(c.len())
            print(c[3])
            print(bytes.to_str(c))
            print(c == [97u8, 98, 99, 100])
        }
        Err(e) => print("error")
    }
    let e = bytes.from_str("")
    print(e.len())
    print(e == [])
}
""",
    "operators_of_generic_impls": """// `==`, `!=`, `<` and the others, and a format hole, on a generic struct
// whose `Eq`, `Ord` and `Format` impls are generic: the operator calls the
// method's instance for the struct's type arguments (MYLA-367)
struct Box<T> {
    v: T,
}

impl<T: Eq> Eq for Box<T> {
    fun eq(self, other: Box<T>) -> bool {
        return self.v == other.v
    }
}

struct Rev<T> {
    v: T,
}

impl<T: Ord> Ord for Rev<T> {
    fun cmp(self, other: Rev<T>) -> int {
        if self.v < other.v { return 1 }
        if self.v > other.v { return -1 }
        return 0
    }
}

impl<T: Format> Format for Box<T> {
    fun format(self, spec: str) -> str {
        return f"<{self.v}>"
    }
}

fun same<T: Eq>(a: Box<T>, b: Box<T>) -> bool {
    return a == b
}

fun main() {
    print(Box { v: 1 } == Box { v: 1 })
    print(Box { v: 1 } != Box { v: 2 })
    print(Box { v: "a" } == Box { v: "b" })
    print(same(Box { v: 'x' }, Box { v: 'x' }))
    print(Rev { v: 1 } < Rev { v: 2 })
    print(Rev { v: "b" } < Rev { v: "a" })
    print(Rev { v: 3 } >= Rev { v: 3 })
    let b = Box { v: 'a' }
    print(f"{b} {Box { v: 42 }:>5} {Box { v: "s" }}")
    print(b)
}
""",
    # D171, MYLA-380: the prelude's Iterator<T>, bounds naming a generic trait
    # with its arguments, `for` over an iterator
    "iterators": """// The prelude's `Iterator<T>` (D171, MYLA-380): a user iterator, generic
// adapters with bounded impls (`impl<I: Iterator<T>, T, U> Iterator<U> for
// Map<I, T, U>`), `for` over them with `break`, `continue` and `return`, a
// copied iterator keeping its own position, bounded generic functions and a
// method, and a `T` that only the bound's impl fixes (D55)
struct Countdown {
    n: int,
}

impl Iterator<int> for Countdown {
    fun next(var self) -> Option<int> {
        if self.n == 0 { return None }
        self.n -= 1
        return Some(self.n + 1)
    }
}

struct Upto {
    i: int,
    stop: int,
}

impl Iterator<int> for Upto {
    fun next(var self) -> Option<int> {
        if self.i >= self.stop { return None }
        self.i += 1
        return Some(self.i - 1)
    }
}

fun upto(a: int, b: int) -> Upto {
    return Upto { i: a, stop: b }
}

struct Map<I, T, U> {
    inner: I,
    f: (T) -> U,
}

impl<I: Iterator<T>, T, U> Iterator<U> for Map<I, T, U> {
    fun next(var self) -> Option<U> {
        return match self.inner.next() {
            Some(v) => Some(self.f(v))
            None => None
        }
    }
}

struct Filter<I, T> {
    inner: I,
    keep: (T) -> bool,
}

impl<I: Iterator<T>, T> Iterator<T> for Filter<I, T> {
    fun next(var self) -> Option<T> {
        while let Some(v) = self.inner.next() {
            if self.keep(v) { return Some(v) }
        }
        return None
    }
}

fun map<I: Iterator<T>, T, U>(it: I, f: (T) -> U) -> Map<I, T, U> {
    return Map { inner: it, f: f }
}

fun filter<I: Iterator<T>, T>(it: I, keep: (T) -> bool) -> Filter<I, T> {
    return Filter { inner: it, keep: keep }
}

struct ListIter<T> {
    xs: [T],
    i: int,
}

impl<T> Iterator<T> for ListIter<T> {
    fun next(var self) -> Option<T> {
        if self.i >= self.xs.len() { return None }
        self.i += 1
        return Some(self.xs[self.i - 1])
    }
}

fun iter_of<T>(xs: [T]) -> ListIter<T> {
    return ListIter { xs: xs, i: 0 }
}

// The words of a string, each a new string
struct Words {
    s: str,
    i: int,
}

impl Iterator<str> for Words {
    fun next(var self) -> Option<str> {
        while self.i < self.s.len() && self.s[self.i] == ' ' { self.i += 1 }
        if self.i >= self.s.len() { return None }
        let start = self.i
        while self.i < self.s.len() && self.s[self.i] != ' ' { self.i += 1 }
        return Some(self.s[start:self.i])
    }
}

fun words(s: str) -> Words {
    return Words { s: s, i: 0 }
}

fun total<I: Iterator<int>>(it: I) -> int {
    var s = 0
    for x in it { s += x }
    return s
}

// `T` is fixed by `I`'s one impl of `Iterator` (D55): nothing else names it
fun count<I: Iterator<T>, T>(it: I) -> int {
    var n = 0
    var c = it
    while let Some(_) = c.next() { n += 1 }
    return n
}

fun to_list<I: Iterator<T>, T>(it: I) -> [T] {
    var out: [T] = []
    for x in it { out.push(x) }
    return out
}

fun first_over<I: Iterator<int>>(it: I, limit: int) -> Option<int> {
    for x in it {
        if x > limit { return Some(x) }
    }
    return None
}

struct Acc {
    sum: int,
}

impl Acc {
    fun add_all<I: Iterator<int>>(var self, it: I) {
        for x in it { self.sum += x }
    }
}

fun main() {
    for x in (Countdown { n: 3 }) { print(x) }
    print(total(upto(0, 5)))
    print(total(Countdown { n: 4 }))
    // an adapter over an adapter, with break and continue
    let evens = filter(map(upto(0, 20), (x: int) => x * 3), (x: int) => x % 2 == 0)
    for x in evens {
        if x == 6 { continue }
        if x > 40 { break }
        print(x)
    }
    print(total(evens))
    print(count(evens))
    print(count(words("one two  three ")))
    // a copy keeps its own position; `for` loops over a copy
    var a = Countdown { n: 5 }
    let first = a.next().unwrap_or(-1)
    var b = a
    let second = b.next().unwrap_or(-1)
    print(f"{first} {second} {a.next().unwrap_or(-1)} {b.next().unwrap_or(-1)}")
    for x in a {
        print(f"in the loop {x}")
        break
    }
    print(a.next().unwrap_or(-1))
    // strings through the adapters
    let long = filter(words("a quick brown fox jumps"), (w: str) => w.len() > 3)
    print(to_list(long).join(","))
    let lens = to_list(map(words("ab cde f"), (w: str) => w.len()))
    print(lens.len())
    for w in map(words("x yy zzz"), (w: str) => w + "!") { print(w) }
    // a generic iterator over a list's elements
    for s in iter_of(["p", "q"]) { print(s) }
    print(total(iter_of([10, 20, 30])))
    // nested loops, a return from inside one, a lambda, a method's bound
    var pairs = 0
    for i in upto(0, 4) {
        for j in upto(0, i) { pairs += j + 1 }
    }
    print(pairs)
    print(first_over(Countdown { n: 9 }, 6).unwrap_or(-1))
    print(first_over(Countdown { n: 3 }, 6).unwrap_or(-1))
    let sum_to = (n: int) => total(upto(0, n + 1))
    print(sum_to(10))
    var acc = Acc { sum: 1 }
    acc.add_all(Countdown { n: 3 })
    acc.add_all(iter_of([100]))
    print(acc.sum)
    // ranges, lists, maps and strings keep their own loops
    var t = 0
    for i in 0..3 { t += i }
    for x in [4, 5] { t += x }
    for k in ["k": 1] { t += k.len() }
    for c in "ab" { t += c as int }
    print(t)
}
""",
    # MYLA-387: tasks parked on notifiers until another task wakes them, on
    # every number of workers the same output
    "notifier_ping_pong": """// MYLA-387: two tasks play ping-pong through two notifiers; an actor's
// log sees the turns alternate, every wait woken
import std.task as task

actor Log {
    turns: [int],
}

impl Log {
    fun turn(var self, who: int) {
        self.turns.push(who)
    }

    fun alternated(self) -> bool {
        var i = 0
        while i < self.turns.len() {
            if self.turns[i] != i % 2 { return false }
            i += 1
        }
        return true
    }

    fun count(self) -> int {
        return self.turns.len()
    }
}

async fun ping(log: Log, mine: task.Notifier, theirs: task.Notifier, n: int) -> int {
    var woken = 0
    for i in 0..n {
        await log.turn(0)
        theirs.notify_one()
        if await mine.wait() { woken += 1 }
    }
    return woken
}

async fun pong(log: Log, mine: task.Notifier, theirs: task.Notifier, n: int) -> int {
    var woken = 0
    for i in 0..n {
        if await mine.wait() { woken += 1 }
        await log.turn(1)
        theirs.notify_one()
    }
    return woken
}

#main
async fun main() {
    let log = Log { turns: [] }
    let a = task.notifier()
    let b = task.notifier()
    async let x = ping(log, a, b, 500)
    async let y = pong(log, b, a, 500)
    print(await x + await y)
    print(await log.count())
    print(await log.alternated())
    // the handles are values: a copy reaches the same notifier
    let c = a
    c.notify_one()
    print(await a.wait_timeout(0))
    print(a == c && a != b)
}
""",
    "notifier_notify_all": """// MYLA-387: a hundred waiters, each listening before it says it is
// there, all woken by one `notify_all`; a second round on the same notifier
import std.task as task

actor Door {
    here: int,
}

impl Door {
    fun arrive(var self) -> int {
        self.here += 1
        return self.here
    }
}

async fun waiter(door: Door, go: task.Notifier, all_here: task.Notifier, k: int, i: int) -> int {
    let l = go.listen()
    if (await door.arrive()) == k { all_here.notify_one() }
    if await l.wait() { return i }
    return -1000
}

async fun round(k: int, go: task.Notifier) -> int {
    let door = Door { here: 0 }
    let all_here = task.notifier()
    var fs: [async () -> int] = []
    for i in 0..k {
        fs.push(async () => await waiter(door, go, all_here, k, i))
    }
    async let rs = task.all(fs)
    let ok = await all_here.wait()
    go.notify_all()
    var sum = 0
    for r in await rs { sum += r }
    return sum
}

#main
async fun main() {
    let go = task.notifier()
    print(await round(100, go))
    print(await round(7, go))
    // nothing left behind: no permit
    print(await go.wait_timeout(0))
}
""",
    "notifier_wake_before_wait": """// MYLA-387: a wake before the wait isn't lost: each `notify_one` leaves a
// permit when nobody waits, which a later wait takes at once; a
// `notify_all` leaves none, but a listener taken before it sees it
import std.task as task

async fun late_waiter(n: task.Notifier) -> bool {
    await task.sleep(5)
    return await n.wait()
}

#main
async fun main() {
    let p = task.notifier()
    p.notify_one()
    p.notify_one()
    p.notify_one()
    var got = 0
    for i in 0..3 {
        if await p.wait() { got += 1 }
    }
    print(got)
    print(await p.wait_timeout(0))
    p.notify_all()
    print(await p.wait_timeout(0))
    let l = p.listen()
    p.notify_all()
    print(await l.wait())
    print(await l.wait_timeout(0))
    // the wake comes before the other task waits
    let q = task.notifier()
    async let w = late_waiter(q)
    q.notify_one()
    print(await w)
}
""",
    "notifier_cancelled_waiter": """// MYLA-387: a waiter asked to stop (D96) stops waiting at once, its wait
// giving false, and sees that it was asked; one asked before it waits
// doesn't wait at all; a notify after that is a permit for the next wait
import std.task as task

async fun forever(n: task.Notifier) -> str {
    let woken = await n.wait()
    return f"woken {woken}, cancelled {task.cancelled()}"
}

async fun nested(n: task.Notifier) -> str {
    async let inner = forever(n)
    return await inner
}

#main
async fun main() {
    let c = task.notifier()
    async let w = forever(c)
    await task.yield()
    task.cancel(w)
    print(await w)
    async let w2 = forever(c)
    task.cancel(w2)
    print(await w2)
    // the request reaches a child of the cancelled task
    async let w3 = nested(c)
    await task.sleep(2)
    task.cancel(w3)
    print(await w3)
    c.notify_one()
    print(await c.wait_timeout(0))
}
""",
    "notifier_timed_out_wait": """// MYLA-387: a wait with a time limit ends when it passes (false), or when
// it is woken first (true); a timed-out wait leaves nothing behind
import std.task as task

async fun limited(n: task.Notifier, ms: int) -> bool {
    return await n.wait_timeout(ms)
}

async fun later(n: task.Notifier) {
    await task.sleep(5)
    n.notify_one()
}

#main
async fun main() {
    let t = task.notifier()
    async let late = limited(t, 20)
    print(await late)
    async let early = limited(t, 60000)
    async let waker = later(t)
    print(await early)
    await waker
    t.notify_one()
    print(await t.wait_timeout(0))
    print(await t.wait_timeout(-3))
    // several limits on one notifier, the shortest first
    async let a = limited(t, 30)
    async let b = limited(t, 10)
    async let c = limited(t, 60000)
    await task.sleep(50)
    t.notify_one()
    print(f"{await a} {await b} {await c}")
}
""",
    "notifier_wakes_a_receiver": """// MYLA-387: a channel's way: a receiver that finds the queue empty leaves
// its notifier with the actor in the same call, and a send wakes the one
// that has waited longest; closing wakes them all
import std.task as task

actor Queue {
    items: [int],
    head: int,
    waiting: [task.Notifier],
    closed: bool,
}

impl Queue {
    fun take(var self, me: task.Notifier) -> Option<int> {
        if self.head < self.items.len() {
            self.head += 1
            return Some(self.items[self.head - 1])
        }
        if self.closed { return Some(-1) }
        self.waiting.push(me)
        return None
    }

    fun put(var self, x: int) {
        self.items.push(x)
        if self.waiting.len() > 0 {
            let n = self.waiting[0]
            self.waiting = self.waiting[1:]
            n.notify_one()
        }
    }

    fun close(var self) {
        self.closed = true
        for n in self.waiting { n.notify_one() }
        self.waiting = []
    }
}

async fun receive(q: Queue) -> int {
    let me = task.notifier()
    var sum = 0
    while true {
        match await q.take(me) {
            Some(x) => {
                if x < 0 { return sum }
                sum += x
            }
            None => { let woken = await me.wait() }
        }
    }
    return sum
}

async fun send(q: Queue, base: int, n: int) {
    for i in 0..n {
        await q.put(base + i)
        if i % 7 == 0 { await task.yield() }
    }
}

#main
async fun main() {
    let q = Queue { items: [], head: 0, waiting: [], closed: false }
    var rs: [async () -> int] = []
    for k in 0..4 {
        rs.push(async () => await receive(q))
    }
    async let got = task.all(rs)
    async let s1 = send(q, 0, 300)
    async let s2 = send(q, 1000, 300)
    await s1
    await s2
    await q.close()
    var total = 0
    for x in await got { total += x }
    print(total)
}
""",
    "iterators_async": """// `for` over an iterator in an async function (D171, MYLA-380): an `await`
// in the body, `break` and `continue`, and a loop without an `await`
import std.task as task

struct Upto {
    i: int,
    stop: int,
}

impl Iterator<int> for Upto {
    fun next(var self) -> Option<int> {
        if self.i >= self.stop { return None }
        self.i += 1
        return Some(self.i - 1)
    }
}

async fun double(x: int) -> int {
    await task.yield()
    return x * 2
}

async fun sum_doubled(n: int) -> int {
    var s = 0
    for x in (Upto { i: 0, stop: n }) {
        if x == 2 { continue }
        if x == 6 { break }
        s += await double(x)
    }
    return s
}

async fun plain(n: int) -> int {
    var s = 0
    for x in (Upto { i: 0, stop: n }) { s += x }
    return s + await double(1)
}

#main
async fun main() {
    async let a = sum_doubled(10)
    async let b = plain(4)
    print(await a)
    print(await b)
    print(await sum_doubled(4))
}
""",
    "iterator_adapters": """// Adapters over adapters (D171, MYLA-380): a chain whose `next` calls its
// parts', a lambda whose parameter only the bound types, `for _`, a
// `T: Add` beside `I: Iterator<T>`, a loop over a field, twice, a `defer`
// in the body, a lambda with a loop
struct Upto {
    i: int,
    stop: int,
}

impl Iterator<int> for Upto {
    fun next(var self) -> Option<int> {
        if self.i >= self.stop { return None }
        self.i += 1
        return Some(self.i - 1)
    }
}

fun upto(a: int, b: int) -> Upto {
    return Upto { i: a, stop: b }
}

struct Map<I, T, U> {
    inner: I,
    f: (T) -> U,
}

impl<I: Iterator<T>, T, U> Iterator<U> for Map<I, T, U> {
    fun next(var self) -> Option<U> {
        return match self.inner.next() {
            Some(v) => Some(self.f(v))
            None => None
        }
    }
}

fun map<I: Iterator<T>, T, U>(it: I, f: (T) -> U) -> Map<I, T, U> {
    return Map { inner: it, f: f }
}

// a chain whose own loop goes over its parts
struct Chain<A, B, T> {
    a: A,
    b: B,
    first: bool,
}

impl<A: Iterator<T>, B: Iterator<T>, T> Iterator<T> for Chain<A, B, T> {
    fun next(var self) -> Option<T> {
        if self.first {
            match self.a.next() {
                Some(v) => { return Some(v) },
                None => { self.first = false },
            }
        }
        return self.b.next()
    }
}

fun chain<A: Iterator<T>, B: Iterator<T>, T>(a: A, b: B) -> Chain<A, B, T> {
    return Chain { a: a, b: b, first: true }
}

// an iterator of strings
struct Steps {
    n: int,
}

impl Iterator<str> for Steps {
    fun next(var self) -> Option<str> {
        if self.n == 0 { return None }
        self.n -= 1
        return Some(f"step {self.n + 1}")
    }
}

fun sum_all<I: Iterator<T>, T: Add>(it: I, zero: T) -> T {
    var s = zero
    for x in it { s = s + x }
    return s
}

struct Holder {
    it: Upto,
}

impl Holder {
    fun twice(self) -> int {
        var n = 0
        for x in self.it { n += x }
        for x in self.it { n += x }
        return n
    }
}

fun main() {
    // a lambda whose parameter's type only the bound gives
    for x in map(upto(0, 3), (x) => x * 10) { print(x) }
    for _ in upto(0, 2) { print("tick") }
    for s in chain(upto(0, 2), upto(7, 9)) { print(s) }
    for s in chain(map(upto(1, 3), (n) => f"<{n}>"), Steps { n: 2 }) { print(s) }
    print(sum_all(upto(1, 5), 0))
    print(sum_all(map(upto(1, 4), (n) => n as float * 0.5), 0.0))
    print(Holder { it: upto(0, 4) }.twice())
    var steps = Steps { n: 3 }
    for s in steps { print(s) }
    print(steps.next().unwrap_or("none"))
    let f = (n: int) => {
        var t = 0
        for x in upto(0, n) { t += x }
        return t
    }
    print(f(5))
    var count = 0
    for x in upto(0, 10) {
        defer { count += 1 }
        if x % 3 == 0 { continue }
        if x == 8 { break }
    }
    print(count)
}
""",
    # std.iter (MYLA-381): the library's adapters and consumers from a program,
    # which also covers the implicit `xs.iter()` (std.list) and `m.iter()` (std.map)
    "std_iter_pipelines": """// `std.iter` from a program (D171, MYLA-381): pipelines with `|>` into the
// module's functions, the implicit `xs.iter()` and `m.iter()`, a user
// iterator and a user `Add` type in them, a function returning a pipeline
// by its module's type names, adapters over adapters
import std.iter as iter
import std.list as list

struct Countdown {
    n: int,
}

impl Iterator<int> for Countdown {
    fun next(var self) -> Option<int> {
        if self.n == 0 { return None }
        self.n -= 1
        return Some(self.n + 1)
    }
}

struct V2 {
    x: int,
    y: int,
}

impl Add for V2 {
    fun add(self, other: V2) -> V2 {
        return V2 { x: self.x + other.x, y: self.y + other.y }
    }
}

fun evens(n: int) -> iter.Filter<iter.Range, int> {
    return iter.range(0, n) |> iter.filter((x) => x % 2 == 0)
}

fun squares(xs: [int]) -> iter.Map<list.ListIter<int>, int, int> {
    return xs.iter() |> iter.map((x) => x * x)
}

fun main() {
    let xs = [1, 2, 3, 4, 5, 6]
    let k = 3
    print(xs.iter() |> iter.map((x) => x * k) |> iter.filter((x) => x % 2 == 0) |> iter.sum(0))
    print(iter.range(0, 10) |> iter.map((x) => (x as int64) * 1000000000) |> iter.sum(0))
    print(evens(10) |> iter.count())
    for s in squares([1, 2, 3]) |> iter.map((n) => f"<{n}>") { print(s) }
    let v = [V2 { x: 1, y: 2 }, V2 { x: 3, y: 4 }].iter() |> iter.sum(V2 { x: 0, y: 0 })
    print(f"{v.x} {v.y}")
    print(Countdown { n: 4 } |> iter.map((x) => f"{x}") |> iter.fold("", (a, s) => a + s))
    var m: [str: int] = [:]
    m["b"] = 2
    m["a"] = 1
    m["c"] = 3
    print(m.iter() |> iter.map((kv) => f"{kv.0}{kv.1}") |> iter.to_list() |> list_join())
    print(m.iter() |> iter.filter((kv) => kv.1 > 1) |> iter.map((kv) => kv.0) |> iter.chain(["z"].iter()) |> iter.to_list() |> list_join())
    let lines = ["one two", "", "three four five"]
    let words = lines.iter() |> iter.flat_map((l) => l.words().iter()) |> iter.enumerate() |> iter.map((p) => f"{p.0}:{p.1}") |> iter.to_list()
    print(list_join(words))
    let pairs = iter.zip(iter.repeat("x"), Countdown { n: 3 }) |> iter.map((p) => f"{p.0}{p.1}") |> iter.to_list()
    print(list_join(pairs))
    let fib = iter.from_fn((0, 1), (s) => Some((s.0, (s.1, s.0 + s.1))))
    print(fib |> iter.skip(5) |> iter.take(5) |> iter.map((n) => f"{n}") |> iter.to_list() |> list_join())
    print(fib |> iter.take_while((n) => n < 30) |> iter.count())
    print(fib |> iter.skip_while((n) => n < 30) |> iter.find((n) => n % 2 == 0) |> show())
    print(xs.iter() |> iter.any((x) => x > 5))
    print(xs.iter() |> iter.all((x) => x > 5))
    print(["pear", "fig", "plum"].iter() |> iter.min() |> show_str())
    print(["pear", "fig", "plum"].iter() |> iter.max() |> show_str())
    let none: [int] = []
    print(none.iter() |> iter.max() |> show())
    // a pipeline is a value: each consumer runs its own copy
    let odd = xs.iter() |> iter.filter((x) => x % 2 == 1)
    print(f"{odd |> iter.count()} {odd |> iter.sum(0)}")
}

fun list_join(xs: [str]) -> str {
    return xs.join(",")
}

fun show(o: Option<int>) -> str {
    return match o {
        Some(v) => f"{v}"
        None => "none"
    }
}

fun show_str(o: Option<str>) -> str {
    return match o {
        Some(v) => v
        None => "none"
    }
}
""",
    # `<` `<=` `>` `>=` on strings, byte by byte (unsigned) as list_dir sorts,
    # past whole words of eight, and `str` is `Ord`: sort, sorted,
    # sort_unstable, binary_search, a generic `T: Ord`, a Heap<str> (MYLA-318)
    "string_ordering": """import std.heap as heap
from std.heap import Heap

// `<`, `<=`, `>`, `>=` on strings order them byte by byte, as list_dir
// sorts, and `str` is `Ord` (MYLA-318): sort, sorted, a Heap<str>, a
// generic `T: Ord`
fun largest<T: Ord>(xs: [T]) -> T {
    var best = xs[0]
    for x in xs {
        if x > best { best = x }
    }
    return best
}

fun order(a: str, b: str) -> str {
    return f"{a < b} {a <= b} {a > b} {a >= b}"
}

struct Named {
    name: str,
}

fun main() {
    print(order("apple", "banana"))
    print(order("ab", "abc"))
    print(order("abc", "ab"))
    print(order("", "a"))
    print(order("", ""))
    print(order("same", "same"))
    print(order("Zebra", "apple"))
    // bytes above 127 order after ASCII, unsigned
    print(order("é", "z"))
    print(order("\\u{1F600}", "\\u{FFFF}"))
    // past the first 8 and 16 bytes
    print(order("abcdefghij", "abcdefghik"))
    print(order("abcdefgh12345678x", "abcdefgh12345678y"))
    print(order("abcdefgh", "abcdefgh\\0"))
    var words = ["pear", "Apple", "fig", "apple", "", "banana", "apples", "é", "z"]
    print(words.sorted().join(","))
    words.sort()
    print(words.join(","))
    print(words.is_sorted())
    var u = ["d", "b", "a", "c", "b"]
    u.sort_unstable()
    print(u.join(","))
    print(words.binary_search("fig").unwrap_or(-1))
    print(largest(["kiwi", "lime", "date"]))
    var h: Heap<str> = heap.new()
    for w in ["m", "c", "x", "a"] { h.push(w) }
    var out: [str] = []
    while let Some(w) = h.pop() { out.push(w) }
    print(out.join(","))
    let n = Named { name: "bo" }
    print(n.name < "bob" && "bob" > n.name)
    let m = ["b": 1, "a": 2]
    var ks = m.keys()
    ks.sort()
    print(ks.join(","))
}
""",
    # `char - char` is an int32, `char + int32` and `char - int32` a char
    # (MYLA-318); a char literal before an integer of another type, or in an
    # integer context, is still that integer
    "char_arithmetic": """// `char - char` is the distance, an int32; `char + int32` and
// `char - int32` move a char, checked to stay a Unicode scalar (MYLA-318)
fun caesar(s: str, k: int) -> str {
    var sb = StringBuilder()
    for c in s {
        if c >= 'a' && c <= 'z' {
            sb.append(f"{'a' + (c - 'a' + k) % 26}")
        } else {
            sb.append(f"{c}")
        }
    }
    return sb.build()
}

fun letter(i: int) -> char {
    return 'a' + i
}

fun main() {
    print('p' - 'a')
    print('a' - 'p')
    let c = 'x'
    let d: int = c - 'a'
    print(d)
    print(c + 1)
    print(c - 23)
    print('a' + 1)
    let n = 2
    print('a' + n)
    print(letter(25))
    var e = 'a'
    e += 3
    e -= 1
    print(e)
    print('é' - 'e')
    print('\\u{1F600}' + 1)
    print(('\\u{10FFFF}' - '\\0') == 1114111)
    print(caesar("hello, world", 13))
    // an int context still makes a char literal an integer, and a byte a byte
    let k: int = 'a' + 1
    print(k)
    let s = "az"
    print(s[1] - 'a')
    var counts = [0, 0, 0]
    for ch in "abacab" { counts[ch - 'a'] += 1 }
    print(counts.map((x: int) => f"{x}").join(","))
}
""",
    # the library side of MYLA-318: std.list's `filled`, std.set, std.map's
    # `get_or`, std.option's `unwrap_or` on parse_int's result
    "aoc_library_helpers": """import std.list as list
import std.set as set
import std.num as num
from std.set import Set

// The library side of MYLA-318's gaps: a list of n equal values
// (std.list's `filled`), a set (std.set), a lookup with a default
// (std.map's `get_or`) and `unwrap_or` on an `Option` (std.option)
fun main() {
    var grid = list.filled(3, list.filled(4, '.'))
    grid[1][2] = '#'
    for row in grid {
        var sb = StringBuilder()
        for c in row { sb.append(f"{c}") }
        print(sb.build())
    }
    var seen: Set<(int, int)> = set.new()
    print(seen.insert((1, 2)))
    print(seen.insert((1, 2)))
    print(seen.contains((1, 2)))
    print(seen.len())
    var counts: [char: int] = [:]
    for c in "hello" { counts[c] = counts.get_or(c, 0) + 1 }
    print(counts.get_or('l', 0))
    print(counts.get_or('z', 0))
    print(num.parse_int("42").unwrap_or(-1))
    print(num.parse_int("4x2").unwrap_or(-1))
}
""",
    # a `?` in a call's argument returns from the caller in the interpreter
    # too, instead of calling with the arguments it has (MYLA-366)
    "try_in_a_call_argument": 'fun inner() -> Result<int, str> { return Err("bad") }\nfun twice(x: int) -> int { return x * 2 }\nfun outer() -> Result<int, str> {\n    return Ok(twice(inner()?))\n}\n#main\nfun main() {\n    match outer() {\n        Ok(v) => print(f"ok {v}"),\n        Err(e) => print(f"err {e}"),\n    }\n}\n',
    # a method called on a field whose type is a type parameter is found in
    # the interpreter too (MYLA-365)
    "method_on_a_type_parameter_field": 'trait Step { fun step(self) -> int }\nstruct One { n: int }\nimpl Step for One { fun step(self) -> int { return self.n + 1 } }\nstruct Wrap<R> { inner: R }\nimpl<R: Step> Wrap<R> {\n    fun go(self) -> int { return self.inner.step() }\n}\n#main\nfun main() {\n    let w = Wrap { inner: One { n: 4 } }\n    print(w.go())\n}\n',
    # map keys of any Eq + Hash type (D163, MYLA-313): a grid's breadth-first
    # search on `(int, int)` keys, a struct key with a string, an enum key, a
    # list key, removed keys added again going last (D105), a type with its own
    # Eq and Hash, a generic `K: Eq + Hash`, std.map's methods and a copy
    "compound_map_keys": (
        "import std.map as maps\n"
        "\n"
        "#derive(Eq, Hash)\n"
        "struct Who {\n"
        "    name: str,\n"
        "    age: int,\n"
        "}\n"
        "\n"
        "#derive(Eq, Hash)\n"
        "enum Dir {\n"
        "    North,\n"
        "    East,\n"
        "    Step(int, int),\n"
        "}\n"
        "\n"
        "// equal when the names agree but for case, and hashed to agree with that\n"
        "struct Tag {\n"
        "    text: str,\n"
        "}\n"
        "\n"
        "fun lower(s: str) -> str {\n"
        "    var sb = StringBuilder()\n"
        "    var i = 0\n"
        "    while i < s.len() {\n"
        "        var b = s[i]\n"
        "        if b >= 'A' && b <= 'Z' { b = b + 32 }\n"
        "        sb.append_byte(b)\n"
        "        i += 1\n"
        "    }\n"
        "    return sb.build()\n"
        "}\n"
        "\n"
        "impl Eq for Tag {\n"
        "    fun eq(self, other: Tag) -> bool {\n"
        "        return lower(self.text) == lower(other.text)\n"
        "    }\n"
        "}\n"
        "\n"
        "impl Hash for Tag {\n"
        "    fun hash(self, h: Hasher) -> Hasher {\n"
        "        return h.add(lower(self.text))\n"
        "    }\n"
        "}\n"
        "\n"
        "// the steps from (0, 0) to every open cell of the grid, breadth first\n"
        "fun bfs(grid: [str]) -> [(int, int): int] {\n"
        "    var dist: [(int, int): int] = [:]\n"
        "    dist[(0, 0)] = 0\n"
        "    var queue = [(0, 0)]\n"
        "    var head = 0\n"
        "    while head < queue.len() {\n"
        "        let (x, y) = queue[head]\n"
        "        head += 1\n"
        "        for d in [(1, 0), (-1, 0), (0, 1), (0, -1)] {\n"
        "            let next = (x + d.0, y + d.1)\n"
        "            if next.1 < 0 || next.1 >= grid.len() || next.0 < 0 || next.0 >= grid[next.1].len() { continue }\n"
        "            if grid[next.1][next.0] == '#' || dist.contains(next) { continue }\n"
        "            dist[next] = dist[(x, y)] + 1\n"
        "            queue.push(next)\n"
        "        }\n"
        "    }\n"
        "    return dist\n"
        "}\n"
        "\n"
        "fun tally<K: Eq + Hash>(xs: [K]) -> [K: int] {\n"
        "    var out: [K: int] = [:]\n"
        "    for x in xs {\n"
        "        if out.contains(x) { out[x] += 1 } else { out[x] = 1 }\n"
        "    }\n"
        "    return out\n"
        "}\n"
        "\n"
        "fun main() {\n"
        "    let grid = [\"..#....\", \".##.##.\", \"....#..\", \"#.#...#\"]\n"
        "    let dist = bfs(grid)\n"
        "    print(f\"{dist.len()} cells, (6, 2) at {dist[(6, 2)]}, (3, 0) at {dist[(3, 0)]}\")\n"
        "    print(dist.contains((2, 0)))\n"
        "\n"
        "    // a struct key with a string in it\n"
        "    var ages: [Who: str] = [:]\n"
        "    ages[Who { name: \"ann\", age: 31 }] = \"first\"\n"
        "    ages[Who { name: \"bob\", age: 27 }] = \"second\"\n"
        "    ages[Who { name: \"a\" + \"nn\", age: 31 }] = \"again\"\n"
        "    print(f\"{ages.len()} {ages[Who { name: \"ann\", age: 31 }]}\")\n"
        "    print(ages.contains(Who { name: \"ann\", age: 32 }))\n"
        "\n"
        "    // removed and added again: last (D105)\n"
        "    var order: [(str, int): bool] = [:]\n"
        "    for i in 0..6 {\n"
        "        order[(f\"k{i}\", i)] = true\n"
        "    }\n"
        "    order.remove((\"k1\", 1))\n"
        "    order.remove((\"k4\", 4))\n"
        "    order[(\"k1\", 1)] = false\n"
        "    order[(\"k2\", 2)] = false\n"
        "    var shown: [str] = []\n"
        "    for k in order { shown.push(f\"{k.0}={order[k]}\") }\n"
        "    print(shown.join(\" \"))\n"
        "    var i = 0\n"
        "    while i < 100 {\n"
        "        order[(\"x\", i)] = true\n"
        "        if i % 3 == 0 { order.remove((\"x\", i)) }\n"
        "        i += 1\n"
        "    }\n"
        "    print(f\"{order.len()} {order.keys()[4].0} {order.keys()[5].1}\")\n"
        "\n"
        "    // an enum key\n"
        "    var moves: [Dir: int] = [Dir.North: 1, Dir.Step(1, 2): 2]\n"
        "    moves[Dir.East] = 3\n"
        "    moves[Dir.Step(1, 2)] += 10\n"
        "    print(f\"{moves[Dir.Step(1, 2)]} {moves[Dir.North]} {moves.contains(Dir.Step(2, 1))}\")\n"
        "\n"
        "    // a list key, and a nested tuple\n"
        "    var paths: [[int]: str] = [:]\n"
        "    paths[[1, 2, 3]] = \"a\"\n"
        "    paths[[1, 2]] = \"b\"\n"
        "    paths[[1, 2, 3]] = \"c\"\n"
        "    print(f\"{paths.len()} {paths[[1, 2, 3]]} {paths[[1, 2]]}\")\n"
        "    var deep: [((int, char), [str]): int] = [:]\n"
        "    deep[((1, 'x'), [\"p\", \"q\"])] = 5\n"
        "    print(deep[((1, 'x'), [\"p\", \"q\"])])\n"
        "\n"
        "    // a type with its own Eq and Hash\n"
        "    var tags: [Tag: int] = [:]\n"
        "    tags[Tag { text: \"Red\" }] = 1\n"
        "    tags[Tag { text: \"RED\" }] = 2\n"
        "    tags[Tag { text: \"blue\" }] = 3\n"
        "    print(f\"{tags.len()} {tags[Tag { text: \"red\" }]}\")\n"
        "\n"
        "    // generic code, std.map's methods and the prelude's get\n"
        "    let t = tally([(1, 'a'), (2, 'b'), (1, 'a')])\n"
        "    print(f\"{t[(1, 'a')]} {t[(2, 'b')]}\")\n"
        "    print(maps.counts([\"x\", \"y\", \"x\"])[\"x\"])\n"
        "    print(ages.get_or(Who { name: \"cy\", age: 1 }, \"none\"))\n"
        "    match moves.get(Dir.East) {\n"
        "        Some(v) => print(v),\n"
        "        None => print(\"missing\"),\n"
        "    }\n"
        "    var grid_counts: [(int, int): int] = [:]\n"
        "    grid_counts.update((0, 0), 0, (n) => n + 5)\n"
        "    grid_counts.update((0, 0), 0, (n) => n + 5)\n"
        "    print(grid_counts[(0, 0)])\n"
        "    for kv in tags.items() { print(f\"{kv.0.text} {kv.1}\") }\n"
        "\n"
        "    // a copy is a value: changing it leaves the original\n"
        "    var copy = ages\n"
        "    copy[Who { name: \"dee\", age: 9 }] = \"new\"\n"
        "    copy.remove(Who { name: \"bob\", age: 27 })\n"
        "    print(f\"{ages.len()} {copy.len()} {ages.contains(Who { name: \"bob\", age: 27 })}\")\n"
        "}\n"
    ),
    # the `Hash` trait (D163, MYLA-313): the built-in types' impls (integers by
    # value, a list with its length), a tuple's, `#derive(Hash)` of structs and
    # enums (the fields in order, a variant's index first), a hand-written impl,
    # and `Hasher.add`, each against the hasher's own adds
    "hash_trait_and_derive": (
        "import std.hash as hash\n"
        "\n"
        "#derive(Eq, Hash)\n"
        "struct Pos {\n"
        "    x: int,\n"
        "    y: int,\n"
        "}\n"
        "\n"
        "#derive(Eq, Hash)\n"
        "struct Named {\n"
        "    name: str,\n"
        "    at: Pos,\n"
        "    tags: [str],\n"
        "    pair: (int64, char),\n"
        "}\n"
        "\n"
        "#derive(Eq, Hash)\n"
        "enum Cell {\n"
        "    Wall,\n"
        "    Open(int),\n"
        "    Door(str, Pos),\n"
        "}\n"
        "\n"
        "// a hand-written impl, and a float hashed through its bits\n"
        "struct Reading {\n"
        "    at: int,\n"
        "    value: float,\n"
        "}\n"
        "\n"
        "impl Eq for Reading {\n"
        "    fun eq(self, other: Reading) -> bool {\n"
        "        return self.at == other.at\n"
        "    }\n"
        "}\n"
        "\n"
        "impl Hash for Reading {\n"
        "    fun hash(self, h: Hasher) -> Hasher {\n"
        "        return h.add(self.at)\n"
        "    }\n"
        "}\n"
        "\n"
        "fun digest<T: Hash>(x: T) -> uint64 {\n"
        "    return x.hash(hash.new()).finish()\n"
        "}\n"
        "\n"
        "fun main() {\n"
        "    print(f\"{digest(5):#x} {digest(5i64):#x} {digest(255u8):#x} {digest(-1i8):#x}\")\n"
        "    print(f\"{digest('a'):#x} {digest(true):#x} {digest(\"abc\"):#x}\")\n"
        "    let big: int64 = 5000000000\n"
        "    let top: uint64 = 18446744073709551615\n"
        "    print(f\"{digest(big):#x} {digest(top):#x} {digest([big, 1]):#x}\")\n"
        "    print(f\"{digest([1, 2, 3]):#x} {digest([\"a\", \"b\"]):#x}\")\n"
        "    // a list adds its length: these differ\n"
        "    print(digest(([1], [2, 3])) != digest(([1, 2], [3])))\n"
        "    let p = Pos { x: 1, y: 2 }\n"
        "    print(digest(p) == hash.new().add_i32(1).add_i32(2).finish())\n"
        "    print(digest(p) == digest((1, 2)))\n"
        "    print(f\"{digest(p):#x}\")\n"
        "    let n = Named { name: \"n\", at: p, tags: [\"a\", \"b\"], pair: (big, 'z') }\n"
        "    print(f\"{digest(n):#x}\")\n"
        "    print(digest(n) == hash.new().add_str(\"n\").add(p).add([\"a\", \"b\"]).add_i64(big).add_char('z').finish())\n"
        "    print(digest(Cell.Wall) == hash.new().add_u64(0).finish())\n"
        "    print(f\"{digest(Cell.Open(3)):#x} {digest(Cell.Door(\"d\", p)):#x}\")\n"
        "    print(digest(Cell.Door(\"d\", p)) == hash.new().add_u64(2).add_str(\"d\").add(p).finish())\n"
        "    print(f\"{digest(((1, 'a'), [true, false], ())):#x}\")\n"
        "    print(f\"{(1, \"x\").hash(hash.new()).finish():#x}\")\n"
        "    print(f\"{[(1, 2), (3, 4)].hash(hash.new()).finish():#x}\")\n"
        "    print(digest(Reading { at: 3, value: 0.5 }) == digest(Reading { at: 3, value: 9.0 }))\n"
        "    print(hash.new().add(7) == hash.new().add_i32(7))\n"
        "    var h = hash.new()\n"
        "    h = h.add(p).add((3, \"q\")).add(Cell.Wall)\n"
        "    print(f\"{h.finish():#x}\")\n"
        "}\n"
    ),
    # `==` and `!=` on tuples and lists whose elements are Eq (D163, MYLA-313):
    # nested, with strings, floats (NaN unequal, 0.0 and -0.0 equal), packed
    # lists, a struct's own `eq`, derived Eq over tuple and list fields, a bound
    # `T: Eq` and `contains`
    "tuple_and_list_equality": (
        "#derive(Eq)\n"
        "struct P {\n"
        "    x: int,\n"
        "    name: str,\n"
        "}\n"
        "\n"
        "struct Loose {\n"
        "    v: int,\n"
        "}\n"
        "\n"
        "// equal when their values agree modulo 10\n"
        "impl Eq for Loose {\n"
        "    fun eq(self, other: Loose) -> bool {\n"
        "        return self.v % 10 == other.v % 10\n"
        "    }\n"
        "}\n"
        "\n"
        "#derive(Eq)\n"
        "enum Shape {\n"
        "    Dot,\n"
        "    Line((int, int), (int, int)),\n"
        "}\n"
        "\n"
        "#derive(Eq)\n"
        "struct Path {\n"
        "    steps: [(int, int)],\n"
        "    tag: (str, bool),\n"
        "}\n"
        "\n"
        "fun same<T: Eq>(a: T, b: T) -> bool {\n"
        "    return a == b\n"
        "}\n"
        "\n"
        "fun main() {\n"
        "    let a = (1, 2)\n"
        "    print(a == (1, 2))\n"
        "    print(a != (1, 2))\n"
        "    print(a == (2, 1))\n"
        "    let s = (1, \"x\", 'c', true)\n"
        "    print(s == (1, \"x\", 'c', true))\n"
        "    print(s == (1, \"y\", 'c', true))\n"
        "    let n = ((1, 2), (3, (4, \"five\")))\n"
        "    print(n == ((1, 2), (3, (4, \"five\"))))\n"
        "    print(n == ((1, 2), (3, (4, \"six\"))))\n"
        "    let big: (int64, uint8) = (5000000000, 200)\n"
        "    print(big == (5000000000, 200))\n"
        "    print((0.0, 1.5) == (-0.0, 1.5))\n"
        "    let nan = 0.0 / 0.0\n"
        "    print((nan, 1) == (nan, 1))\n"
        "    print((P { x: 1, name: \"a\" }, 2) == (P { x: 1, name: \"a\" }, 2))\n"
        "    print((Loose { v: 3 }, 1) == (Loose { v: 13 }, 1))\n"
        "    print((Loose { v: 3 }, 1) == (Loose { v: 14 }, 1))\n"
        "    print([1, 2, 3] == [1, 2, 3])\n"
        "    print([1, 2, 3] == [1, 2])\n"
        "    print([1, 2, 3] != [1, 2, 4])\n"
        "    let bytes: [uint8] = [1, 2, 255]\n"
        "    print(bytes == [1, 2, 255])\n"
        "    let fs: [float32] = [1.5, 2.5]\n"
        "    print(fs == [1.5, 2.5])\n"
        "    print([\"a\", \"b\"] == [\"a\", \"b\"])\n"
        "    print([(1, \"a\"), (2, \"b\")] == [(1, \"a\"), (2, \"b\")])\n"
        "    print([[1], [2, 3]] == [[1], [2, 3]])\n"
        "    print([[1], [2, 3]] == [[1], [2, 4]])\n"
        "    let empty: [int] = []\n"
        "    print(empty == [])\n"
        "    print(Shape.Line((0, 0), (1, 2)) == Shape.Line((0, 0), (1, 2)))\n"
        "    print(Shape.Line((0, 0), (1, 2)) == Shape.Line((0, 0), (1, 3)))\n"
        "    print(Shape.Dot == Shape.Dot)\n"
        "    let p = Path { steps: [(0, 0), (0, 1)], tag: (\"t\", true) }\n"
        "    print(p == Path { steps: [(0, 0), (0, 1)], tag: (\"t\", true) })\n"
        "    print(p == Path { steps: [(0, 0)], tag: (\"t\", true) })\n"
        "    print(same((1, \"a\"), (1, \"a\")))\n"
        "    print(same([(1, 2)], [(1, 3)]))\n"
        "    print([(1, 2), (3, 4)].contains((3, 4)))\n"
        "    let l = [Loose { v: 1 }, Loose { v: 22 }]\n"
        "    print(l == [Loose { v: 11 }, Loose { v: 2 }])\n"
        "}\n"
    ),
    # an unsuffixed literal left of an unsigned operator takes the right
    # operand's type, natively too (MYLA-358: 10 / m divided as signed)
    "literal_left_of_unsigned_division": (
        "#main\nfun main() {\n"
        "    let m: uint64 = 18446744073709551615u64\n"
        "    print(10 / m)\n    print(10 % m)\n"
        "    let big: uint64 = 9223372036854775808u64\n"
        "    print(100 / big)\n    print(100 % big)\n"
        "    let n: uint32 = 4000000000u32\n"
        "    print(7 / n)\n    print(5 + n)\n"
        "    let k: uint8 = 200u8\n"
        "    print(255 / k)\n    print(100 < k)\n"
        "}\n"
    ),
    # a lambda's parameters typed from a generic call's argument types known
    # so far, its result inferred and binding the rest (MYLA-356)
    "lambda_parameters_from_known_arguments": (
        "struct Box<T> {\n    v: T,\n}\n"
        "impl<T> Box<T> {\n    fun map<U>(self, f: (T) -> U) -> Box<U> {\n        return Box { v: f(self.v) }\n    }\n}\n"
        "fun apply<T, U>(x: T, f: (T) -> U) -> U {\n    return f(x)\n}\n"
        "#main\nfun main() {\n"
        "    print(apply(3, (x) => x * 2))\n"
        "    print(apply(\"abc\", (s) => s.len()))\n"
        "    let b = Box { v: 4 }\n"
        "    print(b.map((x) => x + 1).v)\n"
        "    let c = b.map((x) => {\n        return x > 3\n    })\n"
        "    print(c.v)\n"
        "    print(b.map((x) => f\"<{x}>\").map((s) => s.len()).v)\n"
        "}\n"
    ),
    # generic constructors (MYLA-315): the expected type (here the return type
    # `B<T>`) types a struct literal's empty list, map and `None` inside
    # generic code, and a call's expected type (an annotation, a parameter, a
    # return type, a field, a list's element) fixes the type parameters its
    # arguments leave open, of functions and of generic methods; an argument
    # takes it as its hint, so `5000000000` is an `int64` there
    "generic_constructors_from_the_expected_type": (
        "struct B<T> {\n    items: [T],\n}\n"
        "struct Q<T> {\n    front: [T],\n    names: [str: T],\n    top: Option<T>,\n}\n"
        "struct Holder {\n    b: B<int>,\n    q: Q<str>,\n}\n"
        "struct Pair<T> {\n    left: B<T>,\n    right: B<T>,\n}\n"
        "fun mk<T>() -> B<T> {\n    return B { items: [] }\n}\n"
        "fun new_q<T>() -> Q<T> {\n    return Q { front: [], names: [:], top: None }\n}\n"
        "fun of<T>(xs: [T]) -> B<T> {\n    return B { items: xs }\n}\n"
        "fun pair<T>() -> Pair<T> {\n    return Pair { left: mk(), right: mk() }\n}\n"
        "impl<T> B<T> {\n"
        "    fun add(var self, x: T) {\n        self.items.push(x)\n    }\n"
        "    fun size(self) -> int {\n        return self.items.len()\n    }\n"
        "    fun emptied<U>(self) -> B<U> {\n        return mk()\n    }\n"
        "}\n"
        "fun total(b: B<int>) -> int {\n    var t = 0\n    for x in b.items {\n        t += x\n    }\n    return t\n}\n"
        "fun twice<T>(x: T) -> B<T> {\n    var b: B<T> = mk()\n    b.add(x)\n    b.add(x)\n    return b\n}\n"
        "fun names() -> B<str> {\n    return mk()\n}\n"
        "#main\nfun main() {\n"
        "    let a: B<int> = mk()\n    print(a.size())\n"
        "    var s: B<str> = mk()\n    s.add(\"x\")\n    print(s.size())\n"
        "    print(total(mk()))\n"
        "    var h = Holder { b: mk(), q: new_q() }\n    h.b.add(4)\n    h.q.front.push(\"q\")\n"
        "    print(total(h.b))\n    print(h.q.front[0])\n    print(h.q.top.unwrap_or(\"no top\"))\n"
        "    h.b = mk()\n    print(h.b.size())\n"
        "    var n = names()\n    n.add(\"a\")\n    n.add(\"b\")\n    print(n.items[1])\n"
        "    let t = twice(\"hi\")\n    print(t.items[0] + t.items[1])\n"
        "    let e: B<bool> = a.emptied()\n    print(e.size())\n"
        "    let bs: [B<int>] = [mk(), of([1, 2])]\n    print(total(bs[1]))\n"
        "    let big: B<int64> = of([5000000000])\n    print(big.items[0])\n"
        "    let w: Option<int64> = Some(5000000000)\n    print(w.unwrap_or(0))\n"
        "    let p: Pair<char> = pair()\n    print(p.left.size() + p.right.size())\n"
        "    let q: Q<int> = new_q()\n    print(q.top.unwrap_or(7))\n"
        "}\n"
    ),
    # what MYLA-315 gives in passing: an argument whose parameter's type the
    # arguments before it leave open takes the expected type's hint (a
    # literal's width); a type parameter mapped to the enclosing function's is
    # known, so a lambda there takes its parameter types; a generic literal's
    # lambda field takes them like a call's lambda argument (MYLA-356)
    "generic_arguments_hinted_by_the_expected_type": (
        "struct W<T, U> {\n    x: T,\n    f: (T) -> U,\n}\n"
        "struct Box<T> {\n    v: T,\n}\n"
        "impl<T> Box<T> {\n    fun map<U>(self, f: (T) -> U) -> Box<U> {\n        return Box { v: f(self.v) }\n    }\n}\n"
        "enum Maybe<T> {\n    Just(T),\n    Nothing,\n}\n"
        "fun first<T>(xs: [T]) -> T {\n    return xs[0]\n}\n"
        "fun same<T>(b: Box<T>) -> Box<T> {\n    return b.map((x) => x)\n}\n"
        "fun nothing<T>() -> Maybe<T> {\n    return Maybe.Nothing\n}\n"
        "fun pick<T>(c: bool, a: T, b: T) -> T {\n    return if c { a } else { b }\n}\n"
        "#main\nfun main() {\n"
        "    let w = W { x: 3, f: (x) => x + 1 }\n    print(w.f(w.x))\n"
        "    let x: int64 = first([5000000000])\n    print(x)\n"
        "    print(same(Box { v: \"s\" }).v)\n"
        "    let m: Maybe<int> = nothing()\n"
        "    let k = match m {\n        Just(v) => v\n        Nothing => -1\n    }\n    print(k)\n"
        "    let big: int64 = 10\n    print(big + first([2]))\n"
        "    let p: uint8 = pick(true, 200, 3)\n    print(p)\n"
        "}\n"
    ),
    # MYLA-373 (D169): explicit type arguments on a call, a function's and a
    # method's own, where nothing else fixes them (a call statement, `let`
    # without an annotation, an argument of a generic call); `a < b` and
    # `f(a < b, c > d)` stay comparisons
    "explicit_type_arguments": """// explicit type arguments on a call (D169, MYLA-373): a function's and a
// method's own, a call statement, an argument whose parameter's type is
// still open, nested arguments closed by `>>`, a type parameter of the
// enclosing function; comparisons keep their meaning
struct B<T> {
    items: [T],
}

impl<T> B<T> {
    fun size(self) -> int {
        return self.items.len()
    }

    fun mapped<U>(self, f: (T) -> U) -> B<U> {
        var out: [U] = []
        for x in self.items {
            out.push(f(x))
        }
        return B { items: out }
    }

    fun emptied<U>(self) -> B<U> {
        return B { items: [] }
    }
}

fun mk<T>() -> B<T> {
    return B { items: [] }
}

fun pair<A, C>(a: A, c: C) -> (A, C) {
    return (a, c)
}

fun widen<T>(x: T) -> T {
    return x
}

fun count<T>(xs: [T]) -> int {
    return xs.len()
}

fun twice<T>(x: T) -> B<T> {
    var b = mk<T>()
    b.items.push(x)
    b.items.push(x)
    return b
}

fun both(a: bool, b: bool) -> bool {
    return a && b
}

fun main() {
    let d = mk<int>()
    print(d.size())
    var s = mk<str>()
    s.items.push("x")
    print(s.size())
    mk<bool>()
    print(count<int64>([]))
    let big = widen<int64>(5000000000)
    print(big)
    let p = pair<int64, str>(7, "seven")
    print(p.0 + 1)
    print(p.1)
    let b = B { items: [1, 2, 3] }
    let m = b.mapped<str>((x) => f"<{x}>")
    print(m.items[2])
    print(b.emptied<char>().size())
    let nested = mk<B<int>>()
    print(nested.size())
    print(widen(mk<int>()).size())
    print(twice<str>("hi").items[1])
    let one: uint8 = widen<uint8>(200)
    print(one)
    // comparisons
    let x = 1
    let y = 2
    print(x < y)
    print(both(x < y, y > x))
    print(x < y && y > x)
    print(if x < y { "lt" } else { "ge" })
    print(x << 3 > y)
    print(f"{widen<int>(x) < y}")
}
""",
    # MYLA-371 (D170): the standard library's types named through their
    # modules, `args.Spec`, `num.ParseIntError`, `deque.Deque<int>`, and
    # `std.deque.Deque<int>` through a module bound by its whole path
    "std_module_types_by_the_module_name": """// a module's type by its module's name in a type position (D170, MYLA-371):
// a return type, a parameter, an annotation, a field, a list's element, a
// generic type's argument, a function type, a module bound by its whole path
import std.args as args
import std.num as num
import std.deque as deque
import std.deque

struct Tool {
    spec: args.Spec,
    queue: deque.Deque<int>,
}

fun cli() -> args.Spec {
    return args.spec("tool", "does things").flag("verbose", 'v')
}

fun why(e: num.ParseIntError) -> str {
    return match e {
        Empty => "empty"
        InvalidDigit(i) => f"digit at {i}"
        Overflow => "overflow"
    }
}

fun total(qs: [deque.Deque<int>]) -> int {
    var n = 0
    for q in qs {
        n += q.len()
    }
    return n
}

fun main() {
    let e: num.ParseIntError = num.ParseIntError.InvalidDigit(2)
    print(why(e))
    let r: Result<int32, num.ParseIntError> = num.parse_int32("")
    match r {
        Ok(v) => print(v)
        Err(x) => print(why(x))
    }
    var t = Tool { spec: cli(), queue: deque.new() }
    t.queue.push_back(4)
    t.queue.push_back(5)
    let qs: [deque.Deque<int>] = [t.queue, deque.of([1])]
    print(total(qs))
    let f: (std.deque.Deque<int>) -> int = (q) => q.len()
    print(f(t.queue))
    let argv = ["-v"]
    match args.parse(t.spec, argv) {
        Ok(a) => print(a.flag("verbose"))
        Err(x) => print("bad")
    }
    let big = deque.new<deque.Deque<str>>()
    print(big.len())
}
""",
    # a receiver and every argument are taken in order, before a later
    # argument writes their variable through a `var self` method (MYLA-237)
    "argument_values_before_later_writes": (
        "struct C {\n    n: int,\n}\nimpl C {\n    fun bump_get(var self) -> int {\n        self.n = self.n + 1\n        return self.n\n    }\n    fun plus(self, k: int) -> int {\n        return self.n * 100 + k\n    }\n    fun with(self, o: C, k: int) -> int {\n        return self.n * 10000 + o.n * 100 + k\n    }\n}\nfun outer(c: C, k: int) -> int {\n    return c.n * 100 + k\n}\n#main\nfun main() {\n    var c = C { n: 1 }\n    print(c.plus(c.bump_get()))\n    var d = C { n: 1 }\n    print(outer(d, d.bump_get()))\n    var xs = [C { n: 1 }]\n    print(xs[0].plus(xs[0].bump_get()))\n    var e = C { n: 1 }\n    var f = C { n: 5 }\n    print(e.with(f, f.bump_get()))\n    let g = (x: C, k: int) => x.n * 100 + k\n    var h = C { n: 1 }\n    print(g(h, h.bump_get()))\n    var p = C { n: 1 }\n    print(p.n * 100 + p.bump_get())\n}\n"
    ),
    # wrapping on purpose, through the wrapping methods (D175: `+` past the
    # maximum is an overflow where it is checked)
    "unsigned_wrap": (
        "#main\nfun main() {\n"
        "    var b: uint8 = 255u8\n    b = b.wrapping_add(1u8)\n    print(b)\n"
        "    let m: uint64 = 18446744073709551615\n    print(m.wrapping_add(1u64))\n}\n"
    ),
    "signed_wrap_and_div": (
        "#main\nfun main() {\n"
        "    var x: int8 = 127i8\n    x = x.wrapping_add(1i8)\n    print(x)\n"
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
        "        self.n = self.n + 1\n        self.log.push(self.n)\n    }\n"
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
        "    print(xs.len())\n    print(xs[0])\n    print(xs[2])\n    print(total(xs))\n"
        "    let empty: [int] = []\n    print(empty.len())\n}\n"
    ),
    "list_value_semantics_cow": (
        # mutating a copy (and a shared nested cell) must not affect the original.
        "#main\nfun main() {\n"
        "    var a = [1, 2, 3]\n    var b = a\n    b[0] = 99\n    b.push(4)\n"
        "    print(a[0])\n    print(a.len())\n    print(b[0])\n    print(b.len())\n"
        "    var g = [[1, 2], [3, 4]]\n    var h = g\n    h[0][0] = 7\n"
        "    print(g[0][0])\n    print(h[0][0])\n}\n"
    ),
    "list_push_pop_build": (
        "fun make(n: int) -> [int] {\n"
        "    var out: [int] = []\n"
        "    for i in 0..n {\n        out.push(i * i)\n    }\n    return out\n}\n"
        "#main\nfun main() {\n"
        "    var xs = make(6)\n    print(xs.len())\n    print(xs[5])\n"
        "    print(xs.pop())\n    print(xs.len())\n}\n"
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
        '    print(m.len())\n    print(m["a"])\n    print(m["c"])\n'
        '    m["a"] = 10\n    m["d"] = 4\n'
        '    print(m["a"])\n    print(m.len())\n'
        "    let e: [int: int] = [:]\n    print(e.len())\n}\n"
    ),
    "map_value_semantics_cow": (
        # mutating a copy (write, remove, insert) must not affect the original.
        "#main\nfun main() {\n"
        "    var a = [1: 10, 2: 20]\n    var b = a\n"
        "    b[1] = 99\n    b.remove(2)\n    b[3] = 30\n"
        "    print(a[1])\n    print(a.len())\n    print(b[1])\n    print(b.len())\n}\n"
    ),
    "map_get_contains": (
        "fun probe(m: [int: int], k: int) -> int {\n"
        "    var r = -1\n"
        "    match m.get(k) {\n        Some(v) => { r = v }\n        None => { r = -1 }\n    }\n"
        "    return r\n}\n"
        "#main\nfun main() {\n"
        "    let m = [1: 100, 2: 200]\n"
        "    print(probe(m, 1))\n    print(probe(m, 9))\n"
        "    print(m.contains(2))\n    print(m.contains(7))\n}\n"
    ),
    "map_build_keys_and_for": (
        # grow past the load factor, then sum keys and values (order-independent).
        "fun make(n: int) -> [int: int] {\n"
        "    var m: [int: int] = [:]\n"
        "    var i = 0\n    while i < n {\n        m[i] = i * i\n        i = i + 1\n    }\n"
        "    return m\n}\n"
        "#main\nfun main() {\n"
        "    let m = make(50)\n    print(m.len())\n"
        "    var ks = 0\n    for k in m.keys() {\n        ks = ks + k\n    }\n    print(ks)\n"
        "    var vs = 0\n    for k in m {\n        vs = vs + m[k]\n    }\n    print(vs)\n}\n"
    ),
    "map_remove_reinsert": (
        "#main\nfun main() {\n"
        "    var m = [1: 10, 2: 20, 3: 30]\n"
        "    m.remove(2)\n    m.remove(999)\n"
        "    print(m.len())\n    print(m.contains(2))\n"
        "    m[2] = 42\n    print(m[2])\n    print(m.len())\n}\n"
    ),
    "map_of_lists_cow": (
        # heap-owning values retained/dropped correctly across copy and remove.
        "#main\nfun main() {\n"
        "    var m: [int: [int]] = [:]\n"
        "    m[1] = [2, 3]\n    m[1].push(4)\n"
        "    var c = m\n    c.remove(1)\n"
        "    print(m[1][0])\n    print(m[1][2])\n    print(c.len())\n}\n"
    ),
    "string_equality": (
        "#main\nfun main() {\n"
        '    print("abc" == "abc")\n    print("abc" == "abd")\n'
        '    print("abc" != "abd")\n}\n'
    ),
    # --- v0.3.5a strings: len, byte indexing, char literals ---
    "string_len_and_index": (
        "fun blen(s: str) -> int {\n    return s.len()\n}\n"
        "#main\nfun main() {\n"
        '    let s = "Myla"\n'
        "    print(s.len())\n    print(s[0] as int)\n    print(s[3] as int)\n"
        '    print(blen(""))\n    print(blen("hello"))\n}\n'
    ),
    # --- v0.3.5b strings: concat + format ---
    "string_concat": (
        "fun greet(name: str) -> str {\n"
        '    return "Hello, " + name + "!"\n}\n'
        "#main\nfun main() {\n"
        '    print(greet("Myla"))\n'
        '    print("a" + "b" + "c")\n'
        '    let s = "foo" + "bar"\n    print(s.len())\n    print(s[3] as int)\n}\n'
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
        "        sb.append_byte(('0' as int + i) as uint8)\n    }\n"
        "    return sb.build()\n}\n"
        "#main\nfun main() {\n"
        "    var sb = StringBuilder()\n"
        '    sb.append("Hello")\n    sb.append_byte(\',\')\n'
        '    sb.append_byte(\' \')\n    sb.append("world")\n    sb.append_byte(\'!\')\n'
        "    print(sb.len())\n    print(sb.build())\n"
        "    print(digits(10))\n"
        # value semantics: a copy keeps building independently
        "    var a = StringBuilder()\n    a.append(\"seed\")\n"
        "    var b = a\n    b.append(\" more\")\n"
        "    print(a.build())\n    print(b.build())\n}\n"
    ),
    # MYLA-85: append(sb, s, start, end) appends a byte range
    "string_builder_append_range": (
        "fun field(line: str, n: int) -> str {\n"
        "    var start = 0\n    var k = 0\n    var i = 0\n"
        "    while i <= line.len() {\n"
        "        if i == line.len() || line[i] == ',' {\n"
        "            if k == n {\n"
        "                var sb = StringBuilder()\n"
        "                sb.append(line, start, i)\n"
        "                return sb.build()\n            }\n"
        "            k = k + 1\n            start = i + 1\n        }\n"
        "        i = i + 1\n    }\n"
        "    return \"\"\n}\n"
        "#main\nfun main() {\n"
        "    let line = \"alpha,,λ ö,omega\"\n"
        "    for n in 0..5 { print(format(\"[{}]\", field(line, n))) }\n"
        "    var sb = StringBuilder()\n"
        "    sb.append(line, 0, 0)\n"
        "    sb.append(line, line.len() - 5, line.len())\n"
        "    sb.append(\"aö\", 0, 2)\n"
        "    sb.append(\"aö\", 2, 3)\n"
        "    let s = sb.build()\n"
        "    print(s)\n    print(s.len())\n"
        "    var copy = sb\n    copy.append(line, 0, 5)\n"
        "    print(sb.build())\n    print(copy.build())\n}\n"
    ),
    # MYLA-84: a const string made with `+` read inside a function: the
    # self-hosted backend evaluated the concatenation at each use, into a
    # temporary its frame had no slot for, and the function's return crashed
    # MYLA-152: a local closure shadows a builtin of the same name too, with
    # and without a result, in calls; outside its scope the builtin is back
    "local_closure_shadows_a_builtin": (
        "#main\nfun main() {\n"
        "    if true {\n"
        "        let build = (n: int32) => n + 1\n"
        "        print(build(41))\n"
        "        let len = (s: str) => 7\n"
        "        print(len(\"abc\"))\n"
        "        let keys = (n: int32) => [n, n]\n"
        "        print(keys(3)[1])\n"
        "        let push = (s: str) => { print(s + \"!\") }\n"
        "        push(\"pushed\")\n"
        "    }\n"
        "    print(\"abc\".len())\n"
        "    var xs = [1]\n"
        "    xs.push(2)\n"
        "    print(xs.len())\n"
        "}\n"
    ),
    # MYLA-102: a local binding shadows a top-level function of the same name
    # in calls too (a closure, a parameter of function type); outside its
    # scope the function is called again
    "local_closure_shadows_a_function": (
        "fun fail(m: str) -> int32 {\n    print(\"the function\")\n    return 1\n}\n"
        "fun twice(n: int32) -> int32 {\n    return 2 * n\n}\n"
        "fun apply(twice: (int32) -> int32, x: int32) -> int32 {\n    return twice(x)\n}\n"
        "#main\nfun main() {\n"
        "    if true {\n"
        "        let fail = (m: str) => m.len()\n"
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
        "        if i == 0 && a.len() > 3 { return a }\n"
        "        if i == 1 && b.len() > 3 { return b }\n"
        "    }\n"
        "    return c\n"
        "}\n"
        "\n"
        "#main\n"
        "fun main() {\n"
        "    var s = GREETING\n"
        '    s = s + ", " + "world"\n'
        "    print(s)\n"
        "    print(s.len())\n"
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
        "        if piece.len() > 9 {\n"
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
        '        out.push(it.name + "!")\n'
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
        "        self.items.push(Item { name: name, qty: qty })\n"
        "        self.tags.push(name)\n"
        "    }\n"
        "}\n"
        "\n"
        "#main\n"
        "fun main() {\n"
        "    var xs = [3, 1, 4]\n"
        "    xs.push(1)\n"
        "    xs.push(5)\n"
        "    print(xs.len())\n"
        "    print(total(xs))\n"
        "    print(xs[2])\n"
        "    xs[2] = 40\n"
        "    print(first_big(xs))\n"
        "    let ys = xs\n"
        "    xs[0] = 0\n"
        "    print(ys[0])\n"
        "    print(xs[0])\n"
        "    print(xs.pop())\n"
        "    print(xs.len())\n"
        '    var bag = Bag { items: [], tags: ["start"] }\n'
        '    bag.add("apple", 2)\n'
        '    bag.add("pear", 5)\n'
        "    let ns = names(bag)\n"
        "    print(ns[0] + ns[1])\n"
        "    print(bag.tags.len())\n"
        "    bag.items[1].qty = 9\n"
        "    print(bag.items[1].qty)\n"
        "    let copy = bag\n"
        "    bag.items[1].qty = 10\n"
        "    print(copy.items[1].qty)\n"
        "    print(bag.items[1].qty)\n"
        "    var grid = [[1, 2], [3]]\n"
        "    grid[1][0] = 30\n"
        "    grid[0].push(7)\n"
        "    print(grid[0].len() + grid[1][0])\n"
        '    let s = "hello"\n'
        "    print(s[1])\n"
        "    var words: [str] = []\n"
        "    var i = 0\n"
        "    while i < 5 {\n"
        '        words.push("w")\n'
        "        i = i + 1\n"
        "    }\n"
        "    let last = words.pop()\n"
        "    print(last + words[0])\n"
        "    print(words.len())\n"
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
        "    return match m.get(k) {\n"
        '        Some(v) => f"{k}={v}"\n'
        '        None => f"{k} missing"\n'
        "    }\n"
        "}\n"
        "\n"
        "fun joined(parts: [str]) -> str {\n"
        "    var sb = StringBuilder()\n"
        "    for p in parts {\n"
        "        if sb.len() > 0 { sb.append_byte(44) }\n"
        "        sb.append(p)\n"
        "    }\n"
        "    return sb.build()\n"
        "}\n"
        "\n"
        "#main\n"
        "fun main() {\n"
        '    var m = ["a": 1, "b": 2]\n'
        '    m["c"] = 3\n'
        '    m["a"] = 10\n'
        "    print(m.len())\n"
        '    print(m["a"] + m["c"])\n'
        '    print(m.contains("b"))\n'
        "    let saved = m\n"
        '    m.remove("b")\n'
        '    print(m.contains("b"))\n'
        '    print(saved.contains("b"))\n'
        "    print(count(m))\n"
        "    print(count(saved))\n"
        '    print(describe(m, "c"))\n'
        '    print(describe(m, "z"))\n'
        "    print(saved.keys().len())\n"
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
        '    lists["xs"].push(3)\n'
        '    lists["xs"][0] = 100\n'
        '    print(lists["xs"][0] + lists["xs"].len())\n'
        '    print(joined(["x", "yy", "zzz"]))\n'
        "    var sb = StringBuilder()\n"
        '    sb.append("hello world", 6, 11)\n'
        "    sb.append_byte(33)\n"
        "    let built = sb.build()\n"
        "    print(built)\n"
        "    print(sb.len())\n"
        "    var vowels = 0\n"
        '    for c in "héllo wörld".chars() {\n'
        "        if c == 'o' || c == 'ö' || c == 'é' { vowels = vowels + 1 }\n"
        "    }\n"
        "    print(vowels)\n"
        "    let f: float64 = 2.5\n"
        "    let ok = true\n"
        "    let ch = 'q'\n"
        '    print(f"{vowels} {f} {ok} {ch} {built}!")\n'
        '    print(format("[{}|{}]", m.len(), "s"))\n'
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
        "        Named(s, inner) => s.len() + sum(inner)\n"
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
        "    h.spare.push(t)\n"
        "    h.spare.push(Tree.Named(\"xyz\", Tree.Leaf(1)))\n"
        "    var total = 0\n"
        "    for s in h.spare {\n"
        "        total = total + sum(s)\n"
        "    }\n"
        "    print(total)\n"
        "    let last = h.spare.pop()\n"
        "    print(sum(last) + h.spare.len())\n"
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
        "    if s.len() == 0 { return Err(\"empty\") }\n"
        "    var n = 0\n"
        "    for c in s.chars() {\n"
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
        "        seen.push(p + \"!\")\n"
        "        sum = sum + pair(p)?.n\n"
        "    }\n"
        "    return Ok(sum + seen.len())\n"
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
        "    fs.push(h)\n"
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
        "        words.push(w(\"x\"))\n"
        "    }\n"
        "    print(words[2])\n"
        "    let big = [1, 2, 3]\n"
        "    let s = (k: int) => big[k] + big.len()\n"
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
        "        flags.push(i % 2 == 0 && i > 0)\n"
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
        "fun size() -> int32 {\n    return TABLE.len() + N\n}\n"
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
        "    if xs.len() == 0 { return None }\n"
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
        "    while i < s.len() {\n        if s[i] == b {\n            n = n + 1\n        }\n"
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
        "    xs.push(1)\n    xs.push(2)\n"
        "    let snapshot = (i: int) => xs[i]\n"
        "    xs.push(3)\n    xs[0] = 99\n"
        "    print(snapshot(0))\n"                      # 1
        "    print(snapshot(1))\n"                      # 2
        "    print(xs.len())\n"                          # 3
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
        "    for c in s.chars() {\n"
        "        if c == 'a' || c == 'e' || c == 'i' || c == 'o' || c == 'u' {\n"
        "            n = n + 1\n        }\n    }\n    return n\n}\n"
        "#main\nfun main() {\n"
        "    let s = \"h\u00e9\u03bb\U0001f600w\u00f6\"\n"  # raw multibyte UTF-8
        "    print(s.len())\n"                  # 1+2+2+4+1+2 = 12 bytes
        "    print(s.chars().len())\n"           # 6 scalars
        "    for c in s.chars() { print(c as uint32) }\n"
        "    print(vowels(\"education\"))\n"   # 5
        "    print(\"\".chars().len())\n}\n"     # 0
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
        "            self.items.push([upto(i, 2)?])\n"
        "            i = i + 1\n        }\n"
        "        return Ok(self.items.len())\n    }\n}\n"
        "fun lists(n: int) -> Result<int, str> {\n"
        "    var xs: [[int]] = []\n"
        "    for i in 0..n { xs.push([upto(i, 2)?]) }\n"
        "    return Ok(xs.len())\n}\n"
        "fun structs(n: int) -> Result<int, str> {\n"
        "    var ps: [P] = []\n"
        "    for i in 0..n { ps.push(P { name: \"p\", tags: [upto(i, 2)?] }) }\n"
        "    return Ok(ps.len())\n}\n"
        "fun trees(n: int) -> Result<int, str> {\n"
        "    var ts: [Tree] = []\n"
        "    for i in 0..n { ts.push(Tree.Leaf(upto(i, 2)?)) }\n"
        "    return Ok(ts.len())\n}\n"
        "fun show(r: Result<int, str>) {\n"
        "    match r { Ok(k) => print(k), Err(e) => print(e) }\n}\n"
        "#main\nfun main() {\n"
        "    var b = Bag { items: [] }\n"
        "    show(b.fill(5))\n"
        "    print(b.items.len())\n"            # 2: no half-pushed third item
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
        "        return Ok(self.m.len())\n    }\n}\n"
        "#main\nfun main() {\n"
        "    var ix = Index { m: [:] }\n"
        "    match ix.fill(5) { Ok(k) => print(k), Err(e) => print(e) }\n"
        "    print(ix.m.len())\n"
        "    for k in ix.m.keys() { print(ix.m[k].len()) }\n}\n"
    ),
    "try_inside_append_byte_leaves_the_builder_intact": (
        "struct Out { sb: StringBuilder }\n"
        "fun upto(n: int, limit: int) -> Result<int, str> {\n"
        "    if n >= limit { return Err(\"stop\") }\n    return Ok(n)\n}\n"
        "impl Out {\n"
        "    fun fill(var self, n: int) -> Result<int, str> {\n"
        "        for i in 0..n { self.sb.append_byte((65 + upto(i, 2)?) as uint8) }\n"
        "        return Ok(n)\n    }\n}\n"
        "#main\nfun main() {\n"
        "    var o = Out { sb: StringBuilder() }\n"
        "    match o.fill(5) { Ok(k) => print(k), Err(e) => print(e) }\n"
        "    print(o.sb.build())\n}\n"
    ),
    "push_evaluates_its_value_before_the_list": (
        "#main\nfun main() {\n"
        "    var xs = [1, 2, 3]\n"
        "    xs.push(xs.pop() * 10)\n"         # [1, 2, 30]
        "    print(xs.len())\n"
        "    for x in xs { print(x) }\n"
        "    var m: [int: int] = [:]\n"
        "    m[1] = 5\n"
        "    m[2] = m.len() * 100\n"            # the size before the insert
        "    print(m[2])\n}\n"
    ),
    # MYLA-72: `?` in a lambda is checked against the lambda's result type,
    # so the enclosing function needn't return an Option
    "try_in_lambdas_checks_against_the_lambda": (
        "fun half(x: int) -> Option<int> {\n"
        "    if x % 2 == 1 { return None }\n    return Some(x / 2)\n}\n"
        "fun parse(s: str) -> Result<int, str> {\n"
        "    if s == \"\" { return Err(\"empty\") }\n    return Ok(s.len())\n}\n"
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
        "    xs.push(-2.0f64)\n"
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
        "    let k = xs.len()\n"
        "    return (i: int) => xs[i] + k\n}\n"
        "fun pick(xs: [int], i: int) -> int {\n    return xs[i]\n}\n"
        "fun double(x: int) -> int {\n    return x * 2\n}\n"
        "fun churn() {\n"                       # reuses freed cells, if any
        "    var big: [[int]] = []\n"
        "    for i in 0..50 { big.push([i, i, i, i, i, i]) }\n}\n"
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
        "    fs.push(make_adder([4, 5]))\n"
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
        "    print(show(c))\n    print(xs.len())\n    print(s)\n"
        "    var keep: [[int]] = []\n"
        "    for i in 0..3 {\n"
        "        let (v, n) = (V.VI(i), [i, i])\n"
        "        keep.push(n)\n"
        "        print(show(v))\n    }\n"
        "    print(keep[2].len())\n}\n"
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
        "    for i in 0..50 { big.push([i, i, i, i]) }\n}\n"
        "#main\nfun main() {\n"
        "    var xs = [1]\n"
        "    match xs {\n"
        "        ys => {\n"
        "            xs.push(2)\n            xs.push(3)\n"
        "            xs.push(4)\n            xs.push(5)\n"
        "            churn()\n"
        "            print(ys.len())\n"
        "            print(ys[0])\n        }\n    }\n"
        "    var b = Bag { items: [1, 2], name: \"b\" }\n"
        "    match b {\n"
        "        Bag { items, name } => {\n"
        "            b.items = [9]\n"
        "            churn()\n"
        "            print(items.len())\n"
        "            print(items[1])\n        }\n    }\n"
        "    var m: [int: int] = [1: 10]\n"
        "    match m {\n"
        "        mm => {\n"
        "            m[2] = 20\n            m[3] = 30\n"
        "            m[4] = 40\n            m[5] = 50\n            m[6] = 60\n"
        "            churn()\n"
        "            print(mm.len())\n        }\n    }\n"
        "    var bx = Box.Full([7, 7, 7])\n"
        "    match bx {\n"
        "        Full(vs) => {\n"
        "            bx = Box.Empty\n"
        "            churn()\n"
        "            print(vs.len())\n        },\n"
        "        Empty => print(0),\n    }\n"
        "    print(xs.len())\n}\n"
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
        "    print(o.inner.xs.len())\n"
        "    var d = Deep { outer: o }\n"
        "    d.outer.inner = Inner { xs: [4, 5, 6] }\n"
        "    print(d.outer.inner.xs.len())\n"
        "    print(o.inner.xs.len())\n"          # value semantics: still 2
        "    var os = [o, o]\n"
        "    os[1].inner = Inner { xs: [7, 7, 7, 7] }\n"
        "    print(os[0].inner.xs.len())\n"
        "    print(os[1].inner.xs.len())\n"
        "    var m: [int: Outer] = [1: o]\n"
        "    m[1].inner = Inner { xs: [8] }\n"
        "    print(m[1].inner.xs.len())\n"
        "    print(o.inner.xs.len())\n}\n"
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
        "    print(a[0].ys.len())\n"
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
        "    for i in 0..50 { big.push(f\"cell {i}\") }\n}\n"
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
        "    if i == xs.len() { return acc }\n"
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
        "    if i + 1 == xs.len() { return xs[i] }\n"
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
        "    for i in 0..1000 { xs.push(i % 7) }\n"
        "    print(total(xs, 0, 0))\n"
        "    print(via(total, xs))\n"
        "    print(label(1000, \"\").len())\n"
        "    print(last([\"a\", \"b\", \"c\"], 0))\n"
        "    print(relay(\"ab\" + \"c\", deep))\n"
        "    print(pick(Pair { a: 4, b: 2 }, deep))\n"
        "    print(apply2(add3(7, _, _), 8, 9))\n"
        "    shout(deep)\n"
        "}\n"
    ),
    "become_passes_aggregates_by_value": (
        # MYLA-131, D88: `become` hands a struct, tuple or enum its function
        # made over by value: a state machine, a struct per step (owning heap
        # values, or not), a tuple, a type parameter, a part of `self` to a
        # `var self` method; the same functions called as usual, through a
        # function value and a partial application, their value kept
        "enum State { Start, Count(int), Done(str) }\n"
        "struct Pos { x: int, y: int }\n"
        "struct Named { name: str, steps: [int] }\n"
        "struct Walker { at: Pos, home: Pos, moves: int }\n"
        "\n"
        "fun step(s: State, n: int) -> str {\n"
        "    match s {\n"
        "        State.Start => { become step_on(State.Count(0), n) },\n"
        "        State.Count(k) => { become step(next_state(k, n), n) },\n"
        "        State.Done(msg) => { return msg },\n"
        "    }\n"
        "    unreachable()\n"
        "}\n"
        "\n"
        "fun next_state(k: int, n: int) -> State {\n"
        "    if k < n { return State.Count(k + 1) }\n"
        "    return State.Done(f\"counted {k}\")\n"
        "}\n"
        "\n"
        "fun step_on(s: State, n: int) -> str {\n"
        "    become step(s, n)\n"
        "}\n"
        "\n"
        "fun walk(p: Pos, n: int) -> Pos {\n"
        "    if n == 0 { return p }\n"
        "    become walk(Pos { x: p.x + 1, y: p.y + 2 }, n - 1)\n"
        "}\n"
        "\n"
        "fun rename(t: Named, n: int) -> Named {\n"
        "    if n == 0 { return t }\n"
        "    become rename(Named { name: t.name + \"\", steps: t.steps }, n - 1)\n"
        "}\n"
        "\n"
        "fun grow(t: Named, n: int) -> Named {\n"
        "    if n == 0 { return t }\n"
        "    var steps = t.steps\n"
        "    steps.push(n)\n"
        "    become grow(Named { name: t.name + \".\", steps: steps }, n - 1)\n"
        "}\n"
        "\n"
        "fun pair_sum(t: (int, Pos), n: int) -> int {\n"
        "    if n == 0 { return t.0 + t.1.x }\n"
        "    become pair_sum((t.0 + 1, Pos { x: t.1.x + 2, y: 0 }), n - 1)\n"
        "}\n"
        "\n"
        "fun echo<T>(x: T, n: int) -> T {\n"
        "    if n == 0 { return x }\n"
        "    become echo(x, n - 1)\n"
        "}\n"
        "\n"
        "impl Walker {\n"
        "    fun go(var self, to: Pos, n: int) {\n"
        "        self.at = to\n"
        "        self.moves = self.moves + 1\n"
        "        if n == 0 { return }\n"
        "        become self.go(self.home, n - 1)\n"
        "    }\n"
        "}\n"
        "\n"
        "fun total(p: Pos) -> int {\n"
        "    return p.x + p.y\n"
        "}\n"
        "\n"
        "fun keep(t: Named) -> Named {\n"
        "    let kept = t\n"
        "    return kept\n"
        "}\n"
        "\n"
        "#main\n"
        "fun main() {\n"
        "    let deep = 20000\n"
        "    print(step(State.Start, deep))\n"
        "    let p = walk(Pos { x: 0, y: 0 }, deep)\n"
        "    print(p.x + p.y)\n"
        "    let r = rename(Named { name: \"r\" + \"s\", steps: [1, 2] }, deep)\n"
        "    print(r.name)\n"
        "    print(r.steps.len())\n"
        "    let g = grow(Named { name: \"n\", steps: [] }, 1000)\n"
        "    print(g.name.len())\n"
        "    print(g.steps.len())\n"
        "    print(pair_sum((0, Pos { x: 0, y: 0 }), deep))\n"
        "    print(echo(Pos { x: 4, y: 5 }, deep).y)\n"
        "    print(echo(\"text\" + \"!\", deep))\n"
        "    var w = Walker { at: Pos { x: 9, y: 9 }, home: Pos { x: 1, y: 2 }, moves: 0 }\n"
        "    w.go(Pos { x: 5, y: 5 }, deep)\n"
        "    print(w.at.x + w.at.y + w.moves)\n"
        "    print(total(walk(Pos { x: 1, y: 1 }, 3)))\n"
        "    let f = walk\n"
        "    print(total(f(Pos { x: 2, y: 2 }, 2)))\n"
        "    let h = walk(_, 4)\n"
        "    print(total(h(Pos { x: 0, y: 1 })))\n"
        "    print(keep(rename(Named { name: \"k\", steps: [] }, 2)).name)\n"
        "}\n"
    ),
    "derived_eq_called_by_name": (
        # MYLA-132: a derived `eq` called by name (and by `become`), of a
        # struct and of an enum, as `==` calls it
        "#derive(Eq)\n"
        "struct P { x: int, s: str }\n"
        "#derive(Eq)\n"
        "enum Light { Red, Green, Dim(int) }\n"
        "fun same(a: P, b: P) -> bool {\n"
        "    return a.eq(b)\n"
        "}\n"
        "fun lit(l: Light) -> bool {\n"
        "    become l.eq(Light.Green)\n"
        "}\n"
        "fun near(a: P, x: int) -> bool {\n"
        "    become a.eq(P { x: x, s: \"k\" + \"\" })\n"
        "}\n"
        "#main\n"
        "fun main() {\n"
        "    print(same(P { x: 1, s: \"k\" }, P { x: 1, s: \"k\" }))\n"
        "    print(same(P { x: 1, s: \"k\" }, P { x: 1, s: \"j\" }))\n"
        "    print(lit(Light.Green))\n"
        "    print(lit(Light.Dim(2)))\n"
        "    print(Light.Dim(3).eq(Light.Dim(3)))\n"
        "    print(near(P { x: 1, s: \"k\" }, 1))\n"
        "    print(near(P { x: 1, s: \"k\" }, 2))\n"
        "}\n"
    ),
    "strings_and_keys_around_eight_bytes": (
        # MYLA-133: string equality and map keys compared and hashed eight
        # bytes at a time: lengths around the word size, a difference at each
        # position, value keys of every size
        "#derive(Eq)\nenum Light { Red, Green, Blue }\n"
        "fun word(n: int, c: str) -> str {\n"
        "    var s = \"\"\n"
        "    for i in 0..n { s = s + c }\n"
        "    return s\n}\n"
        "#main\nfun main() {\n"
        "    var equal = 0\n"
        "    var differ = 0\n"
        "    for n in 0..18 {\n"
        "        if word(n, \"a\") == word(n, \"a\") { equal = equal + 1 }\n"
        "        for k in 0..n {\n"
        "            let t = word(k, \"a\") + \"b\" + word(n - k - 1, \"a\")\n"
        "            if t != word(n, \"a\") { differ = differ + 1 }\n"
        "        }\n"
        "        if word(n, \"a\") == word(n + 1, \"a\") { equal = equal + 100 }\n"
        "    }\n"
        "    print(equal)\n"
        "    print(differ)\n"
        "    var m: [str: int] = [:]\n"
        "    for n in 0..40 { m[word(n, \"x\")] = n }\n"
        "    var total = 0\n"
        "    for n in 0..40 { total = total + m[word(n, \"x\")] }\n"
        "    print(m.len())\n"
        "    print(total)\n"
        "    var ids: [int64: int] = [:]\n"
        "    var big: int64 = 1\n"
        "    for i in 0..60 {\n"
        "        ids[big] = i\n"
        "        ids[0 - big] = i\n"
        "        big = big * 2\n"
        "    }\n"
        "    print(ids.len())\n"
        "    print(ids[1i64 << 40] + ids[0 - (1i64 << 59)])\n"
        "    let l = Light.Green\n"
        "    print(l == Light.Green)\n"
        "    print(l != Light.Blue)\n"
        "    print(Light.Red == Light.Blue)\n}\n"
    ),
    "var_self_method_on_a_shared_element_copies_it": (
        # MYLA-143: a method writing its receiver, called on an element or a
        # field of one, writes the place it names: each list on the way is
        # made unshared first, so a copy of the list doesn't see the write
        "struct C { n: int, tags: [str] }\n"
        "impl C {\n"
        "    fun bump(var self, by: int) -> int {\n"
        "        self.n = self.n + by\n"
        "        self.tags.push(\"t\")\n"
        "        return self.n\n"
        "    }\n"
        "}\n"
        "struct Board { rows: [C], name: str }\n"
        "fun main() {\n"
        "    var cs = [C { n: 0, tags: [] }, C { n: 1, tags: [] }]\n"
        "    let copy = cs\n"
        "    print(cs[1].bump(10))\n"
        "    print(copy[1].n)\n"
        "    print(copy[1].tags.len())\n"
        "    var b = Board { rows: [C { n: 5, tags: [] }], name: \"b\" }\n"
        "    let b2 = b\n"
        "    print(b.rows[0].bump(1))\n"
        "    print(b2.rows[0].n)\n"
        "    var grid = [[C { n: 7, tags: [] }]]\n"
        "    let g2 = grid\n"
        "    print(grid[0][0].bump(2))\n"
        "    print(g2[0][0].n)\n"
        "    print(cs[1].n + b.rows[0].n + grid[0][0].n)\n"
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
        "        print(other.xs.len())\n"
        "    }\n"
        "    fun keep(var self, xs: [int]) {\n"
        "        self.xs.push(5)\n"
        "        print(xs.len())\n"
        "    }\n"
        "}\n"
        "fun churn() {\n"                       # reuses freed cells, if any
        "    var big: [str] = []\n"
        "    for i in 0..50 { big.push(f\"cell {i}\") }\n}\n"
        "#main\nfun main() {\n"
        "    var b = B { name: \"a\" + \"b\", xs: [1, 2] }\n"
        "    b.rename(b.name)\n"
        "    b.swap(b)\n"
        "    b.keep(b.xs)\n"
        "    print(b.name)\n"
        "    print(b.xs.len())\n"
        "    var bs = [B { name: \"c\" + \"d\", xs: [] }]\n"
        "    bs[0].rename(bs[0].name)\n}\n"
    ),
    "heap_free_arguments_survive_the_receivers_writes": (
        # MYLA-129: the same for an argument without heap memory (a struct,
        # a tuple, an enum, the receiver itself, an element's part), which was
        # passed as the place it was read from
        "struct P { x: int, y: int }\n"
        "enum Mode { Slow, Fast(int) }\n"
        "struct W { p: P, t: (int, int), mode: Mode }\n"
        "impl W {\n"
        "    fun moved(var self, q: P) -> int {\n"
        "        self.p.x = 5\n"
        "        return q.x * 10 + self.p.x\n"
        "    }\n"
        "    fun shifted(var self, u: (int, int)) -> int {\n"
        "        self.t = (7, 8)\n"
        "        return u.0 + u.1\n"
        "    }\n"
        "    fun switched(var self, m: Mode) -> int {\n"
        "        self.mode = Mode.Fast(9)\n"
        "        return match m { Mode.Slow => 0, Mode.Fast(n) => n }\n"
        "    }\n"
        "    fun cloned(var self, other: W) -> int {\n"
        "        self.p.y = 6\n"
        "        return other.p.y\n"
        "    }\n"
        "}\n"
        "#main\nfun main() {\n"
        "    var w = W { p: P { x: 1, y: 2 }, t: (3, 4), mode: Mode.Slow }\n"
        "    print(w.moved(w.p))\n"
        "    print(w.shifted(w.t))\n"
        "    print(w.switched(w.mode))\n"
        "    print(w.cloned(w))\n"
        "    var ws = [W { p: P { x: 2, y: 3 }, t: (0, 0), mode: Mode.Fast(4) }]\n"
        "    print(ws[0].moved(ws[0].p))\n"
        "    print(ws[0].switched(ws[0].mode))\n"
        "    print(w.p.x + w.p.y + w.t.0 + ws[0].p.x)\n}\n"
    ),
    "assign_heap_owning_struct_to_itself": (
        "struct Inner { xs: [int] }\n"
        "struct Outer { inner: Inner }\n"
        "fun churn() {\n"                       # reuses freed cells, if any
        "    var big: [[int]] = []\n"
        "    for i in 0..50 { big.push([i, i, i, i]) }\n}\n"
        "#main\nfun main() {\n"
        "    var p = Inner { xs: [9, 9, 9] }\n"
        "    p = p\n"
        "    churn()\n"
        "    print(p.xs.len())\n"
        "    var o = Outer { inner: Inner { xs: [1, 2] } }\n"
        "    o.inner = o.inner\n"
        "    churn()\n"
        "    print(o.inner.xs.len())\n}\n"
    ),
    "assign_replaces_map_and_builder_elements": (
        # replacing an element releases the old one with its own type's drop
        # routine (the native compiler used to assume every element was a list)
        "struct P { tags: [int] }\n"
        "#main\nfun main() {\n"
        "    var ms: [[int: int]] = [[1: 2]]\n"
        "    ms[0] = [3: 4, 5: 6]\n"
        "    print(ms[0].len())\n"
        "    var bs = [StringBuilder()]\n"
        "    bs[0] = StringBuilder()\n"
        "    bs[0].append(\"hi\")\n"
        "    print(bs[0].build())\n"
        # the new value is taken before the old one is released, so a struct
        # assigned to its own slot keeps its list alive
        "    var ps = [P { tags: [7, 8] }]\n"
        "    ps[0] = ps[0]\n"
        "    var big: [int] = []\n"
        "    for i in 0..64 { big.push(i) }\n"   # reuses a freed cell, if any
        "    print(ps[0].tags.len())\n"
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
        'const H: uint8 = G - 100 + 50\n'
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
        "    xs.push(f(62))\n"
        "    let z = ms.contains(s(\"s9\"))\n"
        "    var sb = StringBuilder()\n"
        "    sb.append(s(\"s10\"))\n"
        "    for ii in f(63)..f(65) {\n"
        "        print(ii)\n"
        "    }\n"
        "    print(\"-- done\")\n"
        "    print(a + b + l + o + o2 + n + w + w2 + y + y2 + y3 + y4 + k + k2)\n"
        "    print(m.x + n2.x + j.x + q.x + q2.y + r[0] + t.0 + u[\"k1\"] + pp.x)\n"
        "    print(c && d && e2 && h2 && i && z)\n"
        "    print(e + x + x2 + sb.build())\n"
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
        "    let size = ident((s: str) => s.len())\n"
        "    print(inc(41))\n"
        "    print(size(\"four\"))\n"
        "    print(call((a: int) => a, \"int to int\"))\n"
        "    print(call((s: str) => s, \"str to str\"))\n"
        "    let t1 = ident((1, A_B { v: 5 }))\n"
        "    let t2 = ident((A { s: \"six\", v: 6 }, 2))\n"
        "    print(t1.1.v + t2.0.v)\n"
        "}\n"
    ),
    # a map literal whose values involve generics: the monomorphizer walks
    # its (key, value) entries (MYLA-174)
    "map_literal_with_generic_values": (
        "struct Box<T> { v: T }\n"
        "\n"
        "fun main() {\n"
        "    let m = [1: Some(2), 3: None]\n"
        "    print(m.len())\n"
        "    match m[1] {\n"
        "        Some(n) => print(n),\n"
        "        None => print(0),\n"
        "    }\n"
        "    let b: [int: Box<str>] = [1: Box { v: \"one\" }]\n"
        "    print(b[1].v)\n"
        "    let nested = [\"k\": [Box { v: 4 }]]\n"
        "    print(nested[\"k\"][0].v)\n"
        "}\n"
    ),
    # float32 overflow gives infinity everywhere (MYLA-176); float32 named,
    # since `float` is float64 (D102)
    "float32_overflow_gives_infinity": (
        "fun main() {\n"
        "    let a = 1e38f32 * 10.0f32\n"
        "    print(a)\n"
        "    print(-1e38f32 * 10.0f32)\n"
        "    let c: float32 = 3.5e38\n"
        "    print(c)\n"
        "    print(a - a)\n"
        "    print(3.4028235e38f32)\n"
        "}\n"
    ),
    # ... and float64's, the default (D102)
    "float64_overflow_gives_infinity": (
        "fun main() {\n"
        "    let a = 1e308 * 10.0\n"
        "    print(a)\n"
        "    print(-1e308 * 10.0)\n"
        "    let c: float = 3.5e38\n"
        "    print(c)\n"
        "    print(a - a)\n"
        "    print(1.7976931348623157e308)\n"
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
    # D175: the quotient `MIN / -1` overflows where it is checked, so the
    # interpreter's part is the remainders (0) and the quotients that fit;
    # a plain build's `MIN / -1` (MYLA-5: no `idiv` fault) is test_ir_contract's
    "int64_min_divided_by_minus_one": (
        'const MIN: int64 = -9223372036854775807 - 1\n'
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
        '    print(a % b)\n'
        '    print(rem(a, -1))\n'
        '    print(div(a, 1))\n'
        '    print(div(-7, -1))\n'
        '    print(rem(-7, -1))\n'
        '    print(div(7, -2))\n'
        '    print(rem(7, -2))\n'
        '    let c: int32 = -2147483647 - 1\n'
        '    var d: int32 = -1\n'
        '    print(c % d)\n'
        '    print(c / 1)\n'
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
        '    b.remove("x")\n'
        '    print(a.len())\n'
        '    print(a.contains("x"))\n'
        '    print(b.len())\n'
        '    print(a["x"].len())\n'
        '    var c = a\n'
        '    c.remove("y")\n'
        '    c.remove("nope")\n'
        '    print(c.len())\n'
        '    print(a.len())\n'
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
        "        if m.len() > 5 {\n            for k in m.keys() {\n                m.remove(k)\n            }\n        }\n"
        "        r = r + 1\n    }\n"
        "    print(m.len())\n    print(m.contains(3))\n    print(m[999])\n}\n"
    ),
    "pop_a_boxed_enum": (
        # a list of a recursive enum holds boxes; `pop` copies the value out of
        # the box and releases it (both compilers used to hand out the box
        # pointer itself, MYLA-74)
        "enum T {\n    Leaf(int),\n    Node(T, [T]),\n}\n"
        "fun show(t: T) -> str {\n"
        "    return match t {\n        T.Leaf(n) => f\"leaf {n}\",\n"
        "        T.Node(l, kids) => f\"node({show(l)}, {kids.len()} kids)\",\n    }\n}\n"
        "struct Stack { items: [T] }\n"
        "impl Stack {\n    fun take(var self) -> T {\n        return self.items.pop()\n    }\n}\n"
        "#main\nfun main() {\n"
        "    var xs: [T] = [T.Leaf(1), T.Node(T.Leaf(2), [T.Leaf(3)]), T.Leaf(4)]\n"
        "    let a = xs.pop()\n    print(show(a))\n"
        "    print(show(xs.pop()))\n"
        "    var s = Stack { items: xs }\n    print(show(s.take()))\n"
        "    print(s.items.len())\n    print(xs.len())\n}\n"
    ),
    # MYLA-386: generic actors. A `Cell<T>` with `int`, `str`, `[int]` and
    # `float64` from several tasks, a bound on a second impl
    "generic_actor_cell": """// MYLA-386: a generic actor, `Cell<T>`, made with `int`, `str` and `[int]`
// and called from several tasks: its fields typed by `T`, its arguments and
// results deep copies, one call at a time
actor Cell<T> {
    value: T,
    writes: int,
}

impl<T> Cell<T> {
    fun get(self) -> T {
        return self.value
    }

    fun put(var self, v: T) -> T {
        let old = self.value
        self.value = v
        self.writes += 1
        return old
    }

    fun update(var self, f: (T) -> T) -> T {
        self.value = f(self.value)
        self.writes += 1
        return self.value
    }

    fun count(self) -> int {
        return self.writes
    }
}

// a bound on the impl gives `T` its operators
impl<T: Add> Cell<T> {
    fun add(var self, x: T) -> T {
        self.value = self.value + x
        self.writes += 1
        return self.value
    }
}

async fun add_up(c: Cell<int>, n: int) -> int {
    var last = 0
    for i in 0..n {
        last = await c.update((x) => x + 1)
    }
    return last
}

async fun grow(c: Cell<str>, n: int) -> int {
    for i in 0..n {
        let s = await c.add("ab")
    }
    return n
}

#main
async fun main() {
    let n = Cell { value: 0, writes: 0 }
    let s = Cell { value: "", writes: 0 }
    async let a = add_up(n, 500)
    async let b = add_up(n, 500)
    async let c = grow(s, 100)
    async let d = grow(s, 50)
    let x = await a
    let y = await b
    print(await c + await d)
    print(await n.get())
    print(await n.count())
    let text = await s.get()
    print(text.len())
    print(await s.count())
    let old = await s.put("reset")
    print(old.len())
    print(await s.get())
    // a list: a copy goes in, a copy comes out
    let l: Cell<[int]> = Cell { value: [1, 2], writes: 0 }
    var mine = await l.get()
    mine.push(3)
    print(mine.len())
    print((await l.get()).len())
    let m = await l.update((xs) => {
        var ys = xs
        ys.push(7)
        return ys
    })
    print(m.len())
    let h = l
    print((await h.get())[2])
    let f = Cell { value: 1.5, writes: 0 }
    print(await f.add(2.25))
}
""",
    # ... a queue whose async methods await inside (another actor, a turn,
    # another instance of the same type)
    "generic_actor_queue": """// MYLA-386: a generic queue actor whose async methods await inside: `push`
// notes each item in a log (another actor), `pop` gives the other tasks a
// turn until an item is there, `move_to` hands its items to another queue of
// the same type, one awaited call at a time
import std.task as task

actor Log {
    lines: int,
}

impl Log {
    fun note(var self) -> int {
        self.lines += 1
        return self.lines
    }

    fun count(self) -> int {
        return self.lines
    }
}

actor Queue<T> {
    items: [T],
    head: int,
    log: Log,
}

impl<T> Queue<T> {
    async fun push(var self, x: T) -> int {
        self.items.push(x)
        let n = await self.log.note()
        return n
    }

    fun take(var self) -> Option<T> {
        if self.head >= self.items.len() { return None }
        self.head += 1
        return Some(self.items[self.head - 1])
    }

    async fun pop(var self) -> T {
        while true {
            if let Some(x) = self.take() { return x }
            await task.yield()
        }
        unreachable()
    }

    fun size(self) -> int {
        return self.items.len() - self.head
    }

    // `take` checks and changes `head` in one step: the warning's walk
    // sees a check before the `await` and a change after it (D95)
    #allow(reentrancy)
    async fun move_to(var self, other: Queue<T>) -> int {
        var moved = 0
        while let Some(x) = self.take() {
            let n = await other.push(x)
            moved += 1
        }
        return moved
    }
}

async fun produce(q: Queue<int>, start: int, n: int) -> int {
    for i in start..start + n {
        let k = await q.push(i)
    }
    return n
}

async fun consume(q: Queue<int>, n: int) -> int {
    var sum = 0
    for i in 0..n {
        sum += await q.pop()
    }
    return sum
}

async fun words(q: Queue<str>, w: str, n: int) -> int {
    for i in 0..n {
        let k = await q.push(f"{w}{i}")
    }
    return n
}

#main
async fun main() {
    let log = Log { lines: 0 }
    let q: Queue<int> = Queue { items: [], head: 0, log: log }
    async let total = consume(q, 300)
    async let a = produce(q, 0, 100)
    async let b = produce(q, 100, 100)
    async let c = produce(q, 200, 100)
    print(await a + await b + await c)
    print(await total)
    print(await q.size())
    let empty: [str] = []
    let w = Queue { items: empty, head: 0, log: log }
    async let x = words(w, "ab", 20)
    async let y = words(w, "c", 30)
    print(await x + await y)
    var chars = 0
    for i in 0..50 {
        chars += (await w.pop()).len()
    }
    print(chars)
    let w2: Queue<str> = Queue { items: ["p", "qq"], head: 0, log: log }
    let w3: Queue<str> = Queue { items: [], head: 0, log: log }
    print(await w2.move_to(w3))
    print(await w3.size())
    print(await w3.pop())
    print(await log.count())
}
""",
    # ... a list of structs, a map and a generic struct inside, deep copies
    # in and out
    "generic_actor_of_structs": """// MYLA-386: a generic actor holding a list of structs (and one holding a map
// and a generic struct): the rows go in and come out as deep copies, so a
// caller's change to what it got doesn't reach the actor

struct Order {
    id: int,
    item: str,
    tags: [str],
}

struct Box<T> {
    v: T,
}

actor Store<T> {
    rows: [T],
    last: Option<T>,
}

impl<T> Store<T> {
    fun add(var self, x: T) -> int {
        self.rows.push(x)
        self.last = Some(x)
        return self.rows.len()
    }

    fun all(self) -> [T] {
        return self.rows
    }

    fun at(self, i: int) -> T {
        return self.rows[i]
    }

    fun keep(var self, f: (T) -> bool) -> int {
        var out: [T] = []
        for r in self.rows {
            if f(r) { out.push(r) }
        }
        self.rows = out
        return out.len()
    }

    fun newest(self) -> Option<T> {
        return self.last
    }
}

actor Index<K, V> {
    m: [K: V],
    boxes: [Box<V>],
}

impl<K: Eq + Hash, V> Index<K, V> {
    fun put(var self, k: K, v: V) -> int {
        self.m[k] = v
        self.boxes.push(Box { v: v })
        return self.m.len()
    }

    fun get(self, k: K) -> Option<V> {
        if self.m.contains(k) { return Some(self.m[k]) }
        return None
    }

    fun boxed(self) -> [Box<V>] {
        return self.boxes
    }
}

async fun fill(s: Store<Order>, start: int, n: int) -> int {
    for i in start..start + n {
        let k = await s.add(Order { id: i, item: f"item{i}", tags: ["new"] })
    }
    return n
}

#main
async fun main() {
    let empty: [Order] = []
    let s = Store { rows: empty, last: None }
    async let a = fill(s, 0, 40)
    async let b = fill(s, 40, 40)
    print(await a + await b)
    var rows = await s.all()
    var ids = 0
    for r in rows { ids += r.id }
    print(ids)
    rows[0].tags.push("changed")
    rows[0].item = "mine"
    let first = await s.at(0)
    print(first.tags.len())
    print(first.item == "mine")
    print(await s.keep((o) => o.id % 10 == 0))
    let again = await s.all()
    print(again.len())
    var kept = 0
    for o in again { kept += o.id }
    print(kept)
    match await s.newest() {
        Some(o) => print(o.tags[0]),
        None => print("none"),
    }
    // two type arguments, a map and a list of a generic struct
    let ix = Index { m: [1: "one"], boxes: [] }
    async let p = ix.put(2, "two")
    async let q = ix.put(3, "three")
    print(await p + await q)
    print((await ix.get(3)).unwrap_or("-"))
    print((await ix.get(9)).unwrap_or("-"))
    print((await ix.boxed()).len())
    let named: Index<str, Order> = Index { m: [:], boxes: [] }
    let n = await named.put("x", Order { id: 5, item: "pen", tags: [] })
    match await named.get("x") {
        Some(o) => print(o.item),
        None => print("none"),
    }
}
""",
    # ... passed to and returned from generic functions, in a generic
    # struct's field and a list, an actor of an actor
    "generic_actor_in_generic_code": """// MYLA-386: generic actors passed to and returned from generic functions,
// held in a generic struct's field and in a list, one instance per type
// argument natively; a copy of a handle reaches the same actor

actor Slot<T> {
    v: T,
    changes: int,
}

impl<T> Slot<T> {
    fun get(self) -> T {
        return self.v
    }

    fun set(var self, v: T) -> T {
        let old = self.v
        self.v = v
        self.changes += 1
        return old
    }

    fun sets(self) -> int {
        return self.changes
    }

    async fun copy_to(self, other: Slot<T>) -> T {
        let old = await other.set(self.v)
        return old
    }
}

struct Named<T> {
    name: str,
    slot: Slot<T>,
}

fun make<T>(v: T) -> Slot<T> {
    return Slot { v: v, changes: 0 }
}

fun named<T>(name: str, v: T) -> Named<T> {
    return Named { name: name, slot: make(v) }
}

async fun swap<T>(a: Slot<T>, b: Slot<T>) {
    let x = await a.get()
    let y = await b.set(x)
    let z = await a.set(y)
}

async fun read_all<T>(ns: [Named<T>]) -> [T] {
    var out: [T] = []
    for n in ns {
        out.push(await n.slot.get())
    }
    return out
}

async fun bump_all(ns: [Named<int>], k: int) -> int {
    var done = 0
    for n in ns {
        let old = await n.slot.set(await n.slot.get() + k)
        done += 1
    }
    return done
}

fun pick<T>(xs: [Slot<T>], i: int) -> Slot<T> {
    return xs[i]
}

#main
async fun main() {
    let a = make(1)
    let b: Slot<int> = make(2)
    await swap(a, b)
    print(await a.get())
    print(await b.get())
    let s = make<str>("left")
    let t = make("right")
    await swap(s, t)
    print(await s.get() + " " + await t.get())
    let ns = [named("x", 10), named("y", 20)]
    async let p = bump_all(ns, 1)
    let q = await p
    print(q)
    let vs = await read_all(ns)
    print(vs[0] + vs[1])
    let words = [named("w", "hello")]
    print((await read_all(words))[0])
    // the same actor through a copy of its handle, and through a list
    let slots = [a, b, make(9)]
    let same = pick(slots, 0)
    let old = await same.set(100)
    print(await a.get())
    print(await a.sets())
    print(await pick(slots, 2).get())
    // an async method of a generic actor calling another instance
    let u = make([1, 2, 3])
    let w = make([0])
    let before = await u.copy_to(w)
    print(before.len())
    print((await w.get()).len())
    let pairs = make((1, "one"))
    print((await pairs.get()).1)
    let nested = make(make(5))
    print(await (await nested.get()).get())
}
""",
    # ... a bounded impl calling `T.zero()`, a method with a type parameter of
    # its own, children of an async method, `task.all` over its calls
    "generic_actor_bounds_and_children": """// MYLA-386: a generic actor's bounded impl calling `T.zero()`, a method
// with a type parameter of its own (`mapped<U>`), an async method whose
// children work on what it read, and `task.all` over its calls
import std.task as task

trait Zero {
    fun zero() -> Self
}

impl Zero for int {
    fun zero() -> int { return 0 }
}

impl Zero for str {
    fun zero() -> str { return "" }
}

actor Acc<T> {
    items: [T],
}

impl<T> Acc<T> {
    fun mapped<U>(self, f: (T) -> U) -> [U] {
        var out: [U] = []
        for x in self.items { out.push(f(x)) }
        return out
    }

    fun push(var self, x: T) -> int {
        self.items.push(x)
        return self.items.len()
    }

    async fun split_count(self, f: async (T) -> int) -> int {
        let xs = self.items
        async let a = count_all(xs, f)
        async let b = count_all(xs, f)
        return await a + await b
    }
}

impl<T: Zero + Add> Acc<T> {
    fun total(self) -> T {
        var s = T.zero()
        for x in self.items { s = s + x }
        return s
    }
}

async fun count_all<T>(xs: [T], f: async (T) -> int) -> int {
    var n = 0
    for x in xs { n += await f(x) }
    return n
}

async fun weigh(s: str) -> int {
    return s.len()
}

async fun one(x: int) -> int {
    return x
}

#main
async fun main() {
    let a = Acc { items: [1, 2, 3] }
    let b = Acc { items: ["x", "yy"] }
    var fs: [async () -> int] = []
    for i in 0..10 {
        fs.push(async () => await a.push(i))
    }
    let rs = await task.all(fs)
    print(rs.len())
    print(await a.total())
    print(await b.total())
    let strs = await a.mapped<str>((x) => f"<{x}>")
    print(strs.len())
    print(strs[0])
    print(await b.split_count(weigh))
    print(await a.split_count(one))
}
""",
    # ... an actor holding another of its type argument, and one that links
    # to others of its own type
    "generic_actors_nested": """// MYLA-386: a generic actor whose field is another generic actor of its
// type argument, awaited from its async method, and one that links to
// others of its own type (a handle is a reference, so it may)
actor Cell<T> {
    value: T,
}

impl<T> Cell<T> {
    fun get(self) -> T {
        return self.value
    }

    fun set(var self, v: T) {
        self.value = v
    }
}

actor Pipe<T> {
    out: Cell<T>,
    seen: int,
}

impl<T> Pipe<T> {
    async fun send(var self, v: T) -> int {
        await self.out.set(v)
        self.seen += 1
        return self.seen
    }
}

actor Node<T> {
    v: T,
    next: Option<Node<T>>,
}

impl<T> Node<T> {
    fun value(self) -> T {
        return self.v
    }

    fun link(self) -> Option<Node<T>> {
        return self.next
    }
}

async fun walk<T>(n: Node<T>) -> [T] {
    var out: [T] = []
    var cur: Option<Node<T>> = Some(n)
    while let Some(c) = cur {
        out.push(await c.value())
        cur = await c.link()
    }
    return out
}

#main
async fun main() {
    let c: Cell<str> = Cell { value: "a" }
    let p = Pipe { out: c, seen: 0 }
    let k = await p.send("b")
    let k2 = await p.send("c")
    print(await c.get())
    print(k2)
    let last = Node { v: 3, next: None }
    let mid = Node { v: 2, next: Some(last) }
    let first = Node { v: 1, next: Some(mid) }
    let vs = await walk(first)
    print(vs.len())
    print(vs[0] + vs[1] + vs[2])
}
""",
    # MYLA-392: an `await` in a `match` that ends an arm of a `match`
    # statement. The async split took the inner `match` for the arm's value
    # and bound the void `await` to a temporary, which native code couldn't
    # lower ("a function used as a value")
    "await_in_a_nested_match": """import std.task as task

enum Cause { Stop, Code(int) }

async fun worker(r: Result<int, Cause>) -> int {
    match r {
        Ok(n) => { return n }
        Err(e) => {
            match e {
                Stop => {}
                Code(code) => {
                    print(code)
                    await task.sleep(1)
                }
            }
        }
    }
    return 0
}

async fun twice(n: int) -> int {
    await task.yield()
    return 2 * n
}

// three deep, the innermost arm's value an awaited call, and a match as a
// value whose arm ends in a nested match statement
async fun deeper(r: Result<Option<int>, str>) -> int {
    var got = 0
    match r {
        Ok(o) => match o {
            Some(n) => {
                match n > 10 {
                    true => { got = await twice(n) }
                    false => await task.sleep(0)
                }
            }
            None => { got = -1 }
        }
        Err(s) => {
            let k = match s.len() {
                0 => 0
                n => {
                    match n {
                        1 => await task.yield()
                        _ => { print(s) }
                    }
                    await twice(n)
                }
            }
            got = k
        }
    }
    return got
}

#main
async fun main() {
    print(await worker(Err(Cause.Code(24))))
    print(await worker(Err(Cause.Stop)))
    print(await worker(Ok(7)))
    print(await deeper(Ok(Some(21))))
    print(await deeper(Ok(Some(3))))
    print(await deeper(Ok(None)))
    print(await deeper(Err("abc")))
    print(await deeper(Err("z")))
    print(await deeper(Err("")))
}
""",
    # MYLA-390: a tuple of names in a `for` head, over a list, a map's items,
    # an iterator, nested tuples, `_`, nested loops and an async loop
    "for_tuple_patterns": """// MYLA-390: a tuple of names in a `for` head, over lists, maps' items,
// iterators, nested tuples and `_`
import std.task as task
import std.iter as iter

struct Pairs {
    i: int,
    n: int,
}

impl Iterator<(int, str)> for Pairs {
    fun next(var self) -> Option<(int, str)> {
        if self.i >= self.n { return None }
        self.i += 1
        return Some((self.i, "#".repeat(self.i)))
    }
}

async fun total(ps: [(str, int)]) -> int {
    var t = 0
    for (name, n) in ps {
        await task.yield()
        t += n * name.len()
    }
    return t
}

#main
async fun main() {
    let pairs = [("a", 1), ("bb", 2), ("ccc", 3)]
    for (k, v) in pairs {
        print(f"{k}={v}")
    }
    var m: [str: int] = [:]
    m["x"] = 10
    m["y"] = 20
    var sum = 0
    for (k, v) in m.items() {
        print(k)
        sum += v
    }
    print(sum)
    for (i, s) in (Pairs { i: 0, n: 3 }) {
        print(f"{i}:{s}")
    }
    for ((a, b), c) in [((1, 2), 3), ((4, 5), 6)] {
        print(a + b + c)
    }
    for (_, v) in pairs {
        print(v)
    }
    for (i, x) in ["p", "q"].iter() |> iter.enumerate() {
        print(f"{i} {x}")
    }
    // a nested loop's names, and break and continue
    for (k, v) in pairs {
        if v == 2 { continue }
        for (k2, v2) in pairs {
            if v2 > v { break }
            print(k + k2)
        }
    }
    print(await total(pairs))
}
""",
    # MYLA-390: `sb.append_char(c)` natively, as the interpreter does it
    "wrapping_methods": """// D175 (MYLA-395): the builtin wrapping methods of every integer width, the
// same interpreted, natively and checked, past both ends; a hash, a random
// step and a checksum that wrap on purpose
fun fnv1a(s: str) -> uint64 {
    var h: uint64 = 0xcbf29ce484222325
    for i in 0..s.len() {
        h = (h ^ (s[i] as uint64)).wrapping_mul(0x100000001b3)
    }
    return h
}

fun lcg(x: uint32) -> uint32 {
    return x.wrapping_mul(1664525).wrapping_add(1013904223)
}

fun adler(s: str) -> uint32 {
    var a: uint16 = 1
    var b: uint16 = 0
    for i in 0..s.len() {
        a = a.wrapping_add(s[i] as uint16)
        b = b.wrapping_add(a)
    }
    return ((b as uint32) << 16) | (a as uint32)
}

fun main() {
    let i8max: int8 = 127
    let i8min: int8 = -128
    print(i8max.wrapping_add(1))
    print(i8min.wrapping_sub(1))
    print(i8max.wrapping_mul(i8max))
    print(i8min.wrapping_neg())
    let u8max: uint8 = 255
    let u8zero: uint8 = 0
    print(u8max.wrapping_add(u8max))
    print(u8zero.wrapping_sub(1))
    print(u8max.wrapping_mul(u8max))
    print(u8zero.wrapping_neg())
    let one: uint8 = 1
    print(one.wrapping_neg())
    let i16: int16 = 32767
    print(i16.wrapping_add(i16))
    let u16: uint16 = 65535
    print(u16.wrapping_mul(3))
    let i32max: int32 = 2147483647
    print(i32max.wrapping_add(1))
    print(i32max.wrapping_mul(-2))
    let u32max: uint32 = 4294967295
    print(u32max.wrapping_mul(u32max))
    print(u32max.wrapping_add(2))
    let i64min: int64 = -9223372036854775807 - 1
    print(i64min.wrapping_sub(1))
    print(i64min.wrapping_neg())
    print(i64min.wrapping_mul(-1))
    let u64max: uint64 = 18446744073709551615
    print(u64max.wrapping_add(1))
    print(u64max.wrapping_mul(u64max))
    var x: uint32 = 1
    for k in 0..5 {
        x = lcg(x)
    }
    print(x)
    print(fnv1a("myla"))
    print(adler(\"Wikipedia, the free encyclopedia, at some length\"))
    var acc: int64 = 1
    acc = acc.wrapping_mul(3).wrapping_add(4).wrapping_sub(10)
    print(acc)
}
""",
    "append_char": """// MYLA-390: `sb.append_char(c)`, a character's UTF-8 bytes, of each length
struct Doc {
    out: StringBuilder,
}

impl Doc {
    fun put(var self, c: char) {
        self.out.append_char(c)
    }
}

fun main() {
    var sb = StringBuilder()
    for c in ['a', 'é', '€', '😀', '\\n', '\\u{10FFFF}', '\\0'] {
        sb.append_char(c)
    }
    let s = sb.build()
    print(s.len())
    for c in s { print(c as int) }
    // in a struct's field and a list's element
    var d = Doc { out: StringBuilder() }
    d.put('ö')
    d.put('k')
    print(d.out.build())
    var bs = [StringBuilder(), StringBuilder()]
    bs[1].append_char('ß')
    bs[1].append_char('!')
    print(bs[1].build())
    print(bs[0].len())
    // a copy keeps its own bytes
    var a = StringBuilder()
    a.append_char('x')
    var b = a
    b.append_char('y')
    print(a.build())
    print(b.build())
    var many = StringBuilder()
    for i in 0..1000 { many.append_char('λ') }
    print(many.len())
}
""",
    "literal_element_types_from_later_elements": """// MYLA-401: a list or map literal's element type from all its elements:
// a variant's open type parameters come from a later element
enum Either<L, R> {
    Left(L),
    Right(R),
}

enum Tagged<T, U> {
    One(T),
    Two(T, U),
    Nothing,
}

#derive(Eq, Hash)
enum Key<T> {
    Any,
    One(T),
}

struct Page<T> {
    items: [T],
    next: Option<int>,
}

fun show(e: Either<int, str>) -> str {
    return match e {
        Left(n) => f"L{n}"
        Right(s) => f"R{s}"
    }
}

fun main() {
    let es = [Either.Left(1), Either.Right("a"), Either.Left(3)]
    var line = ""
    for e in es { line = line + show(e) }
    print(line)
    // None, Ok and Err take theirs from a later element
    let os = [None, Some(2u8), None]
    print(os.len())
    match os[1] { Some(v) => print(v + 250), None => print(0) }
    let rs = [Ok(1), Err("bad"), Ok(2)]
    for r in rs {
        match r {
            Ok(n) => print(n)
            Err(s) => print(s)
        }
    }
    // a variant without payload, and nested lists
    let ts = [Tagged.Nothing, Tagged.One(1.5), Tagged.Two(2.5, 'x')]
    print(ts.len())
    match ts[2] { Tagged.Two(a, b) => print(b), _ => print('-') }
    let nested = [[], [Either.Left(4)], [Either.Right(true)]]
    print(nested[1].len() + nested[2].len())
    let empties = [[], [], [7i64]]
    print(empties[2][0] + 5000000000)
    // a map's keys and values
    let m = ["a": None, "b": Some(2), "c": None]
    print(m["b"].unwrap_or(0) + 40)
    let k = [Key.Any: 1, Key.One('z'): 2]
    print(k[Key.One('z')])
    // in tuples
    let ps = [(None, 'a'), (Some("b"), 'c')]
    match ps[1] { (Some(s), c) => print(s), _ => print("-") }
    // in a struct literal's field
    let p = Page { items: [Tagged.One(1), Tagged.Two(1, false)], next: None }
    print(p.items.len())
    let q: Page<Tagged<int, bool>> = Page { items: [Tagged.One(1)], next: None }
    print(q.items.len() + first_page().items.len())
    // what an earlier element fixed guides a later one's literal
    let ws = [Either.Left(1u8), Either.Left(2), Either.Right("x")]
    match ws[1] { Left(n) => print(n + 250), Right(s) => print(s) }
}

fun first_page() -> Page<Tagged<str, bool>> {
    return Page { items: [Tagged.One("p"), Tagged.Nothing], next: Some(2) }
}
""",
    "a_field_and_a_method_of_one_name": """// MYLA-406: a field and a method of the same name: `x.name` is the field,
// `x.name(…)` the method
struct Lru<K> {
    keys: [K],
    len: int,
}

impl<K> Lru<K> {
    fun keys(self) -> [K] {
        return self.keys[::-1]
    }

    fun len(self) -> int {
        return self.keys.len()
    }

    fun push(var self, k: K) {
        self.keys.push(k)
        self.len += 10
    }
}

// a field of a type parameter is no function where the struct is declared
struct Cell<T> {
    get: T,
}

impl<T> Cell<T> {
    fun get(self) -> [T] {
        return [self.get, self.get]
    }
}

// a getter named like the field, the way an actor's state is read
actor Counter {
    count: int,
}

impl Counter {
    fun count(self) -> int {
        return self.count
    }

    fun bump(var self) {
        self.count += 1
    }
}

trait Named {
    fun name(self) -> str
}

struct Pet {
    name: str,
}

impl Named for Pet {
    fun name(self) -> str {
        return "pet " + self.name
    }
}

fun describe<T: Named>(x: T) -> str {
    return x.name()
}

// a field that holds a function is still called as `h.on(…)`
struct Handler {
    on: (int) -> int,
}

#main
async fun main() {
    var c = Lru { keys: [1, 2], len: 0 }
    c.push(3)
    print(c.keys.len())
    print(c.keys()[0])
    print(c.keys[0])
    print(c.len)
    print(c.len())
    let cell = Cell { get: 'q' }
    print(cell.get)
    print(cell.get().len())
    let k = Counter { count: 4 }
    await k.bump()
    print(await k.count())
    let p = Pet { name: "rex" }
    print(p.name)
    print(p.name())
    print(describe(p))
    let h = Handler { on: (n: int) => n + 1 }
    print(h.on(2))
    print((h.on)(3))
}
""",
    "comparisons_in_literals_and_holes": """// D186 (MYLA-416): `a < b, c > (d)` is one generic call only in a call's
// argument list; in a list, map or tuple literal it is two comparisons, and
// each f-string hole is parsed on its own. A literal's element keeps a
// call's own arguments, a struct literal's fields and one type argument.
struct Box<T> {
    v: T,
}

fun pair<A, C>(a: A, c: C) -> (A, C) {
    return (a, c)
}

fun mk<T>() -> [T] {
    return []
}

fun count(p: (int64, str)) -> int {
    return p.1.len()
}

fun both(p: bool, q: bool) -> int {
    if p && q {
        return 2
    }
    return 0
}

fun main() {
    let a = 1
    let b = 3
    let c = 5
    let d = 2
    let t = [a < b, c > (d + 1), b < a, a > (c)]
    print(t.len())
    print(t[3])
    let u = (a < b, c > (d))
    print(u.1)
    let w = (b < a, d > (a), c > (d))
    print(w.2)
    let m = [a < b: 1, c > (d): 2]
    print(m.len())
    print(m[true])
    // f-string holes
    print(f"{a < b} {c > (a)}")
    let lo = 1
    let hi = 9
    let x = 5
    print(f"below: {x < lo}, above: {x > (hi - 1)}")
    print(f"{x < lo}{x} > ({hi})")
    print(f"{x < lo:>6} and {hi > (x)}")
    print(f"{[a < b, c > (d)].len()}")
    // what stays a generic call inside an element
    let n = [count(pair<int64, str>(1, "one")), count(pair<int64, str>(2, "three"))]
    print(n[1])
    let bx = [Box { v: pair<int, str>(7, "seven") }]
    print(bx[0].v.1)
    let one = [mk<int>().len(), mk<str>().len()]
    print(one.len())
}
""",
    # M24 (MYLA-417): `()` as a type argument
    "unit_as_a_type_argument": r"""// M24 (MYLA-417): `()` as a type argument, written or inferred from a
// function without a result: `() -> T` with `T` the unit type is `() -> ()`
import std.bench as bench

fun work() {
}

fun twice<T>(f: () -> T) -> [T] {
    return [f(), f()]
}

fun main() {
    let r = bench.run_n<()>("u", 3, () => work())
    print(r.runs)
    let r2 = bench.run_n("v", 2, () => work())
    print(r2.runs)
    let xs = twice(() => work())
    print(xs.len())
    let ys: [()] = twice(work)
    print(ys.len())
    let g: () -> () = () => work()
    print(twice(g).len())
    print(twice(() => 7)[1])
}
""",
    # L2 (MYLA-417): earlier literals take the type a later element fixes
    "literals_take_the_type_a_later_element_fixes": r"""// L2 (MYLA-417): the literals before the element that fixes a literal's
// type take that type, each checked again against it, in lists, map keys
// and map values
fun main() {
    let big: int64 = 5000000000
    let a = [1, -2, 3, big]
    print(a[1] * big)
    let b = [200, 100, 255u8]
    print(b[2] - b[0] + b[1])
    let f = [1.5, -2.25, 0.5f32]
    print(f[1])
    let m = [1: 40000, 2: 7, 3: big]
    print(m[1] * big)
    let k = [7: "a", 300: "b", 3u16: "c"]
    for x in k.keys().sorted() { print(x * 200) }
    let c = ['a', 'b', 99u8]
    print(c[1] + c[2])
    let n = [-1, -128, 5i8]
    print(n[1])
}
""",
    # MYLA-449: a literal too wide for int32 waits for the element that fixes a wider type
    "literals_wait_for_the_element_that_fixes_a_wider_type": r"""// MYLA-449: a literal too wide for the type the literals before it have
// waits for the element that fixes a wider one, in lists, map keys and map
// values
fun main() {
    let big: int64 = 5000000000
    let a = [4000000000, big]
    print(a[0] + a[1])
    let b = [1, -3000000000, 4000000000, big]
    print(b[1] * 2)
    let m = [1: 4000000000, 2: big]
    print(m[1] - m[2])
    let k = [4000000000: "a", big: "b", 7: "c"]
    print(k[4000000000] + k[7])
    let u: uint64 = 1
    let c = [18000000000000000000, 2, u]
    print(c[0] + c[1])
    let n = [[4000000000, big], [1]]
    print(n[1][0] + n[0][0])
}
""",
    # MYLA-448: a compound assignment's hidden index and right side take the plain assignment's types
    "compound_assignments_type_as_their_plain_form": r"""// MYLA-448: a compound assignment's hidden `let` of its index expects the
// key type of the place it indexes, and its right side what the plain
// `place = place op value` gives it
trait Blank {
    fun blank() -> Self
}

impl Blank for str {
    fun blank() -> str { return "-" }
}

impl Blank for int {
    fun blank() -> int { return 7 }
}

fun blank<T: Blank>() -> T { return T.blank() }

struct Acc {
    counts: [Option<int>: int],
    grid: [[int64]],
}

fun main() {
    var r: [Result<str, int>: int] = [:]
    r[Ok("a")] = 1
    r[Ok("a")] += 10
    r[Err(2)] = 5
    r[Err(2)] *= 3
    print(r[Ok("a")] + r[Err(2)])
    var m: [Option<int>: int] = [:]
    m[None] = 1
    m[None] += 1
    m[Some(4)] = 2
    m[Some(2 + 2)] <<= 3
    print(m[None] + m[Some(4)])
    var w: [int64: int] = [:]
    w[5000000000] = 1
    w[2500000000 * 2] += 41
    print(w[5000000000])
    var b: [uint8: str] = [:]
    b[200] = "x"
    b[100 + 100] += "y"
    b[100 + 100] += blank()
    print(b[200])
    var acc = Acc { counts: [None: 1], grid: [[1, 2], [3]] }
    acc.counts[None] -= 1
    acc.counts[Some(1 + 1)] = 4
    acc.counts[Some(1 + 1)] %= 3
    var i = 0
    acc.grid[i + 1][^(i + 1)] += 5000000000
    var n = 1
    n += blank()
    print(f"{acc.counts[None]} {acc.counts[Some(2)]} {acc.grid[1][0]} {n}")
}
""",
    # D182 (MYLA-417): `Option` and `Result` are `Hash`
    "option_and_result_as_map_keys": r"""// D182 (MYLA-417): `Option` and `Result` derive `Hash` in the prelude, so
// an `Option` or `Result` of hashable types is a map key, and a derived key
// struct may have such a field
#derive(Eq, Hash)
struct Key {
    name: str,
    port: Option<int>,
}

fun count_distinct<K: Eq + Hash>(xs: [K]) -> int {
    var seen: [K: bool] = [:]
    for x in xs { seen[x] = true }
    return seen.len()
}

fun main() {
    var m: [Option<int>: str] = [:]
    m[Some(1)] = "one"
    m[None] = "none"
    m[Some(2)] = "two"
    m[Some(1)] = "uno"
    print(m.len())
    print(m[Some(1)])
    print(m.get(None).unwrap_or("?"))
    print(m.contains(Some(3)))
    var r: [Result<str, int>: int] = [:]
    r[Ok("a")] = 1
    r[Err(1)] = 2
    r[Ok("a")] = r[Ok("a")] + 10
    print(r[Ok("a")] + r[Err(1)])
    let keys = [Key { name: "a", port: None }, Key { name: "a", port: Some(80) }, Key { name: "a", port: None }]
    print(count_distinct(keys))
    print(count_distinct([Some(Some(1)), Some(None), None, Some(Some(1))]))
    let h1 = Hasher { state: 7 }.add(Some("x")).finish()
    let h2 = Hasher { state: 7 }.add(Some("x")).finish()
    let h3 = Hasher { state: 7 }.add(Some("y")).finish()
    print(h1 == h2)
    print(h1 == h3)
    var t: [(Option<str>, int): int] = [:]
    t[(None, 1)] = 5
    print(t[(None, 1)])
}
""",
    # MYLA-417: a lambda result, `?` and a variant on the left of `==` take the types the call knows
    "inference_through_lambdas_try_and_variants": r"""// MYLA-417: inference follow-ups. A lambda's result takes what the call
// knows of it (`and_then`'s `E` from the receiver, MYLA-356); the type
// expected of `e?` is expected of `e`, with the function's error type
// (MYLA-315); `Tree.Leaf == t` types the variant by `t` (MYLA-379)
struct B<T> {
    items: [T],
}

#derive(Eq)
enum Tree<T> {
    Leaf,
    Node(T),
}

fun mk<T>() -> B<T> {
    return B { items: [] }
}

fun try_mk<T>(ok: bool) -> Result<B<T>, str> {
    if ok { return Ok(mk()) }
    return Err("no")
}

fun opt_mk<T>(ok: bool) -> Option<B<T>> {
    if ok { return Some(mk()) }
    return None
}

fun use_q(ok: bool) -> Result<int, str> {
    let a: B<int> = try_mk(ok)?
    var b: B<str> = try_mk(ok)?
    b.items.push("x")
    return Ok(a.items.len() + b.items.len())
}

fun use_o(ok: bool) -> Option<int> {
    let a: B<int64> = opt_mk(ok)?
    return Some(a.items.len())
}

fun main() {
    let r: Result<int, str> = Ok(2)
    print(r.and_then((x) => Ok(x + 1)) == Ok(3))
    let bad: Result<int, str> = Err("e")
    print(bad.and_then((x) => Ok(x * 2)) == Err("e"))
    let o: Option<int> = Some(4)
    print(o.and_then((x) => Some(x + 1)) == Some(5))
    print(use_q(true) == Ok(1))
    print(use_q(false) == Err("no"))
    print(use_o(true) == Some(0))
    print(use_o(false) == None)
    let t: Tree<int> = Tree.Node(3)
    print(Tree.Leaf == t)
    print(Tree.Node(3) == t)
    print(Tree.Node(4) != t)
}
""",
    # MYLA-380 follow-up (MYLA-417): an enum as a stateful iterator
    "enum_var_self_assigns_self": r"""// MYLA-380's follow-up (MYLA-417): an enum's `var self` method assigns
// `self`, which writes the caller's place, so an enum can be a stateful
// iterator; payloads that own memory, a place in a struct and in a list
enum Count {
    Left(int),
    Done,
}

impl Iterator<int> for Count {
    fun next(var self) -> Option<int> {
        match self {
            Left(n) => {
                if n == 0 { self = Count.Done } else { self = Count.Left(n - 1) }
                return Some(n)
            }
            Done => { return None }
        }
    }
}

enum Words {
    Rest([str]),
    Empty,
}

impl Words {
    fun take(var self) -> str {
        return match self {
            Rest(ws) => {
                if ws.len() <= 1 { self = Words.Empty } else { self = Words.Rest(ws[1:]) }
                ws[0]
            }
            Empty => "",
        }
    }
}

enum Light {
    Red,
    Green,
    Amber,
}

impl Light {
    fun step(var self) {
        self = match self {
            Red => Light.Green,
            Green => Light.Amber,
            Amber => Light.Red,
        }
    }

    fun name(self) -> str {
        return match self {
            Red => "red",
            Green => "green",
            Amber => "amber",
        }
    }
}

struct Crossing {
    light: Light,
}

fun main() {
    for x in Count.Left(3) { print(x) }
    var w = Words.Rest(["a", "bb", "ccc"])
    let first = w.take()
    print(first + w.take() + w.take() + w.take() + "|")
    var c = Crossing { light: Light.Red }
    c.light.step()
    c.light.step()
    print(c.light.name())
    var ls = [Light.Amber, Light.Red]
    ls[1].step()
    print(ls[0].name() + " " + ls[1].name())
    var total = 0
    var it = Count.Left(4)
    while let Some(n) = it.next() { total += n }
    print(total)
}
""",
    # MYLA-538: a generic impl's bounds of generic traits, met, at each use
    "impl_bounds_of_generic_traits_met": r"""// MYLA-538: an impl's bound naming a generic trait is checked where the
// impl is used, its arguments included; these meet theirs, directly, in
// generic code, through another bound and a derive-free nesting
import std.iter as iter

trait Conv<T> {
    fun conv(self) -> T
}

struct S {
    n: int,
}

impl Conv<int> for S {
    fun conv(self) -> int { return self.n }
}

struct V<I> {
    v: I,
}

impl<I: Iterator<str>> Eq for V<I> {
    fun eq(self, other: V<I>) -> bool {
        var a = self.v
        return a.next() == Some("x")
    }
}

struct W<I, T> {
    v: I,
    d: [T],
}

impl<I: Iterator<T>, T: Eq> Eq for W<I, T> {
    fun eq(self, other: W<I, T>) -> bool {
        var a = self.v
        var b = other.v
        return a.next() == b.next()
    }
}

struct C<I> {
    v: I,
}

impl<I: Iterator<int>> Iterator<int> for C<I> {
    fun next(var self) -> Option<int> {
        return match self.v.next() {
            Some(x) => Some(x * 2),
            None => None,
        }
    }
}

struct K<X> {
    c: X,
}

impl<X: Conv<int>> Eq for K<X> {
    fun eq(self, other: K<X>) -> bool { return self.c.conv() == other.c.conv() }
}

struct P<I> {
    w: V<I>,
}

impl<I: Iterator<str>> Eq for P<I> {
    fun eq(self, other: P<I>) -> bool { return self.w == other.w }
}

fun g<J: Iterator<str>>(j: J) -> bool { return V { v: j } == V { v: j } }

fun same<T: Eq>(a: T, b: T) -> bool { return a == b }

fun h<J: Iterator<T>, T: Eq>(j: J, k: J) -> bool {
    let e: [T] = []
    return W { v: j, d: e } == W { v: k, d: e }
}

fun main() {
    print(V { v: ["x"].iter() } == V { v: ["y"].iter() })
    print(V { v: ["y"].iter() } == V { v: ["x"].iter() })
    print(g(["x"].iter()))
    print(same(V { v: ["x"].iter() }, V { v: ["y"].iter() }))
    let e: [int] = []
    print(W { v: [1].iter(), d: e } == W { v: [1].iter(), d: e })
    print(h([1].iter(), [2].iter()))
    print([V { v: ["x"].iter() }] == [V { v: ["x"].iter() }])
    print(C { v: [1, 2, 3].iter() } |> iter.sum(0))
    for x in (C { v: [4].iter() }) { print(x) }
    print(C { v: C { v: [5].iter() } } |> iter.sum(0))
    print(K { c: S { n: 1 } } == K { c: S { n: 1 } })
    print(K { c: S { n: 1 } } != K { c: S { n: 2 } })
    print(P { w: V { v: ["x"].iter() } } == P { w: V { v: ["z"].iter() } })
}
""",
    # MYLA-544 (C8): x.format(spec) on a builtin T: Format
    "format_method_on_a_builtin_type_parameter": r"""// MYLA-544 (C8): `x.format(spec)` on `x: T` with `T: Format` at a builtin
// `T`: its print form by the spec, as a format hole gives it, on each runner
struct P {
    n: int,
}

impl Format for P {
    fun format(self, spec: str) -> str { return "P" + spec }
}

struct V<T> {
    v: T,
}

impl<T: Format> Format for V<T> {
    fun format(self, spec: str) -> str { return "V(" + self.v.format(spec) + ")" }
}

fun show<T: Format>(x: T, spec: str) -> str {
    return "[" + x.format(spec) + "]"
}

fun widths<T: Format>(xs: [T]) -> str {
    var sb = StringBuilder()
    var w = 1
    for x in xs {
        sb.append(x.format(f">{w}"))
        w += 1
    }
    return sb.build()
}

fun main() {
    print(show(5, ""))
    print(show(-5i8, "04"))
    print(show(255u8, "#06x"))
    print(show(18446744073709551615u64, "x"))
    print(show(-1i64, "b"))
    print(show(3.14159f32, ".2"))
    print(show(2.5, ">8.3"))
    print(show('λ', "^3"))
    print(show(true, ">6"))
    print(show("ab", "*<5"))
    print(show(P { n: 1 }, "!"))
    print(f"{V { v: 7 }:+}")
    print(show(V { v: V { v: 'c' } }, ">2"))
    print(widths([1, 2, 3]))
    print(widths(["a", "b"]))
    let s = show(42, "08")
    print(s.len())
}
""",
    # MYLA-544: literals left of typed operands, the expected type through an operator
    "literals_left_of_typed_operands": r"""// MYLA-544: a literal left of a typed operand is typed by it, as one on its
// right is (a negated one, one past int32, a range's start and an arm's
// too), and the type expected of an operator trait's result reaches its
// operands, a struct of literals taking the other operand's type
struct V<T> {
    v: T,
}

impl<T: Add> Add for V<T> {
    fun add(self, other: V<T>) -> V<T> { return V { v: self.v + other.v } }
}

impl<T: Eq> Eq for V<T> {
    fun eq(self, other: V<T>) -> bool { return self.v == other.v }
}

fun main() {
    let big: int64 = 5
    let u: uint32 = 5
    let f: float32 = 1.5f32
    print(5000000000 + big)
    print(-1 + big)
    print(-1 == big)
    print(3000000000 > u)
    print(-2.5 * f)
    var n = 0
    for i in u..4294967295 {
        n += 1
        if n == 3 { break }
    }
    print(n)
    for j in -2..big { n += 1 }
    print(n)
    let a = if big > 0 { -1 } else { big }
    let b = match big { 0 => -1.5, _ => f }
    print(a)
    print(b)
    let c: V<int64> = V { v: 2 } + V { v: 5000000000 }
    print(c.v)
    let d = V { v: 2 } + V { v: 1u8 }
    print(d.v)
    let x: V<uint8> = V { v: 250 }
    print(V { v: 250 } == x)
    let w: int8 = -'a'
    print(w)
}
""",
    # MYLA-417 (C1): a generic actor's getter called from outside
    "actor_getter_of_a_field_s_name": r"""// MYLA-417 (C1): a generic actor's getter of a field's name, called from
// outside, is the method: the actor's fields are its own methods' only, so
// D178's call error has nothing to tell apart there
actor Cell<T> {
    value: T,
}

impl<T> Cell<T> {
    fun value(self) -> T { return self.value }
}

struct Holder {
    c: Cell<(int) -> int>,
}

async fun via(h: Holder) -> int {
    let g = await h.c.value()
    return g(10)
}

#main
async fun main() {
    let c = Cell { value: (x: int) => x + 1 }
    let f = await c.value()
    print(f(5))
    print(await via(Holder { c: c }))
}
""",
    "values_nested_through_closures":r"""// M15 (MYLA-415): values nested through closures, as deep as they like, are
// released in a bounded stack on every target (wasm32 overflowed at about
// 3,000 levels, aarch64 under qemu at 30,000), and copied to a child task
// without recursion
import std.process as process
import std.num as num

struct Holder { f: () -> int, rest: [Holder] }
struct Box { kids: [Box], tag: str }
enum Chain { End, Step((int) -> int, Chain) }

fun closures(n: int) -> int {
    var f = () => 0
    for i in 0..n {
        let g = f
        f = () => g() + 1
    }
    return 7
}

fun lists_of_closures(n: int) -> int {
    var fs: [() -> int] = []
    for i in 0..n {
        let prev = fs
        fs = [() => prev.len()]
    }
    return fs[0]()
}

fun holders(n: int) -> int {
    var h = Holder { f: () => 0, rest: [] }
    for i in 0..n {
        let prev = h
        h = Holder { f: () => prev.rest.len() + 1, rest: [] }
    }
    return h.f()
}

fun chains(n: int) -> int {
    var c = Chain.End
    for i in 0..n {
        let prev = c
        c = Chain.Step((x: int) => match prev { End => x, Step(g, _) => x + 1 }, Chain.End)
    }
    return match c { End => 0, Step(g, _) => g(1) }
}

fun partials(n: int) -> int {
    var f = (x: int, k: () -> int) => x
    var k = () => 0
    for i in 0..n {
        let kk = k
        k = () => kk() + 0
    }
    let p = f(_, k)
    return p(5)
}

fun nest(n: int) -> Box {
    var b = Box { kids: [], tag: "leaf" }
    for k in 0..n { b = Box { kids: [b], tag: f"t{k % 7}" } }
    return b
}

// the depth of a nested box and the length of its tags, by a loop
fun depth(b0: Box) -> (int, int) {
    var b = b0
    var d = 0
    var sum = 0
    while b.kids.len() > 0 {
        sum += b.tag.len()
        b = b.kids[0]
        d += 1
    }
    return (d, sum)
}

async fun crossing(f: () -> int, fs: [() -> int], b: Box) -> (int, int) {
    let (d, s) = depth(b)
    return (fs.len() + d, s)
}

#main
async fun main() {
    let a = process.args()
    var n = 50000
    if a.len() > 1 { n = num.parse_int(a[1]).unwrap_or(50000) as int }
    print(closures(n))
    print(lists_of_closures(n))
    print(holders(n))
    print(chains(n))
    print(partials(n))
    // to a child task and back, deeply copied
    var f = () => 0
    var fs: [() -> int] = []
    for i in 0..n {
        let g = f
        f = () => g() + 1
        let prev = fs
        fs = [() => prev.len()]
    }
    let b = nest(n)
    async let c = crossing(f, fs, b)
    let (k, t) = await c
    let (d, u) = depth(b)
    print(f"{k} {t} {d} {u}")
    print("released")
}
""",
    "arithmetic_operators_of_generic_impls": r"""// M2 (MYLA-415, MYLA-367): the arithmetic operators of a generic impl call
// its instance for the operands' type arguments (natively they didn't link)
struct Box<T> { v: T }
impl<T: Add> Add for Box<T> {
    fun add(self, other: Box<T>) -> Box<T> { return Box { v: self.v + other.v } }
}
impl<T: Sub> Sub for Box<T> {
    fun sub(self, other: Box<T>) -> Box<T> { return Box { v: self.v - other.v } }
}
impl<T: Mul> Mul for Box<T> {
    fun mul(self, other: Box<T>) -> Box<T> { return Box { v: self.v * other.v } }
}
impl<T: Div> Div for Box<T> {
    fun div(self, other: Box<T>) -> Box<T> { return Box { v: self.v / other.v } }
}
impl<T: Rem> Rem for Box<T> {
    fun rem(self, other: Box<T>) -> Box<T> { return Box { v: self.v % other.v } }
}

struct Pair<A, B> { a: A, b: B }
impl<A: Add, B: Add> Add for Pair<A, B> {
    fun add(self, other: Pair<A, B>) -> Pair<A, B> { return Pair { a: self.a + other.a, b: self.b + other.b } }
}

// in generic code, where the checker types the result (its half of M2 is
// MYLA-417's), each operator through a function of its own
fun plus<T: Add>(a: Box<T>, b: Box<T>) -> Box<T> { return a + b }
fun minus<T: Sub>(a: Box<T>, b: Box<T>) -> Box<T> { return a - b }
fun times<T: Mul>(a: Box<T>, b: Box<T>) -> Box<T> { return a * b }
fun over<T: Div>(a: Box<T>, b: Box<T>) -> Box<T> { return a / b }
fun modulo<T: Rem>(a: Box<T>, b: Box<T>) -> Box<T> { return a % b }
fun chain<T: Add>(a: Box<T>) -> Box<T> { return a + a + a }
fun pair_sum<A: Add, B: Add>(x: Pair<A, B>, y: Pair<A, B>) -> Pair<A, B> { return x + y }

fun int_of(b: Box<int>) -> int { return b.v }
fun float_of(b: Box<float>) -> float { return b.v }
fun str_of(b: Box<str>) -> str { return b.v }

fun main() {
    print(int_of(plus(Box { v: 1 }, Box { v: 2 })))
    print(int_of(minus(Box { v: 7 }, Box { v: 2 })))
    print(int_of(times(Box { v: 6 }, Box { v: 7 })))
    print(int_of(over(Box { v: 9 }, Box { v: 2 })))
    print(int_of(modulo(Box { v: 9 }, Box { v: 4 })))
    print(float_of(plus(Box { v: 1.5 }, Box { v: 2.25 })))
    print(str_of(plus(Box { v: "ab" }, Box { v: "cd" })))
    print(str_of(chain(Box { v: "ab" })))
    let big: Box<int64> = Box { v: 5000000000 }
    print(chain(big).v)
    print(int_of(Box { v: 1 }.add(Box { v: 2 })))
    let p = pair_sum(Pair { a: 1, b: "x" }, Pair { a: 2, b: "y" })
    print(f"{p.a} {p.b}")
    // the operator outside generic code links too
    let unused = Box { v: 1 } + Box { v: 2 }
    print("linked")
}
""",
    "list_equal_to_itself": r"""// M3 (MYLA-415, MYLA-313): a list compared with itself, or with a copy that
// shares its cell, is equal without a look at its elements only where the
// elements' `==` is built in and reflexive: a NaN isn't equal to itself, and
// a struct's `eq` runs (and may say no)
from std.io import println

struct Never { v: int }
impl Eq for Never { fun eq(self, other: Never) -> bool { return false } }

struct Loud { v: int }
impl Eq for Loud {
    fun eq(self, other: Loud) -> bool {
        println("eq called")
        return self.v == other.v
    }
}

#derive(Eq)
struct Holder { items: [float] }

#derive(Eq)
struct Point { x: int, y: int }

fun main() {
    let nan = 0.0 / 0.0
    let xs = [nan]
    let ys = xs
    println(f"{xs == xs} {xs == ys} {xs != ys} {xs == [nan]}")
    let nested = [[1.0, nan]]
    let n2 = nested
    println(f"{nested == n2} {nested != n2}")
    let pairs = [(1, nan)]
    println(f"{pairs == pairs}")
    let a = [Never { v: 1 }]
    let b = a
    println(f"{a == b} {a != b}")
    let l = [Loud { v: 1 }, Loud { v: 2 }]
    let l2 = l
    println(f"{l == l2}")
    let h = Holder { items: [nan] }
    println(f"{h == h}")
    let hs = [h]
    println(f"{hs == hs}")
    // reflexive elements: equal, as before
    let ints = [1, 2, 3]
    let strs = ["a", "b"]
    let deep = [[1, 2], [3]]
    let tups = [(1, "x", 'c', true)]
    let pts = [Point { x: 1, y: 2 }]
    let pts2 = pts
    println(f"{ints == ints} {strs == strs} {deep == deep} {tups == tups} {pts == pts2}")
    let f2 = [1.5, 2.5]
    println(f"{f2 == f2} {f2 != f2}")
}
""",
    "keys_that_change_their_container": r"""// H4 (MYLA-415): a key, index or argument whose computation copies or grows
// the container it is used on: computed before the container is made
// unique, as the interpreter does, so a copy keeps the old contents and a
// write never lands in a cell the growth freed
struct Counter { n: int }
impl Counter {
    fun inc(var self, k: int) { self.n += k }
}

struct H {
    m: [int: int],
    saved: [int: int],
    xs: [int],
    xs_saved: [int],
    grid: [[int]],
    i: int,
    sb: StringBuilder,
    sb_saved: StringBuilder,
    cs: [Counter],

    names: [str: str],
}

impl H {
    fun snap(var self, k: int) -> int {
        self.saved = self.m
        self.xs_saved = self.xs
        return k
    }
    fun grow(var self, k: int) -> int {
        var i = 100
        while i < 400 {
            self.m[i] = i
            self.xs.push(i)
            self.cs.push(Counter { n: i })
            i += 1
        }
        return k
    }
    fun bump(var self) -> int {
        self.i += 1
        return self.i
    }
    fun snap_sb(var self, s: str) -> str {
        self.sb_saved = self.sb
        return s
    }
    fun key(var self, k: str) -> str {
        self.names[k + "!"] = "added"
        return k
    }
}

impl [int] {
    fun put_at(var self, i: int, v: int) { self[i] = v }
}

fun fresh() -> H {
    return H { m: [1: 10, 2: 20, 3: 30], saved: [:], xs: [1, 2, 3], xs_saved: [], grid: [[0, 0, 0], [0, 0, 0], [0, 0, 0]], i: 0, sb: StringBuilder(), sb_saved: StringBuilder(), cs: [Counter { n: 0 }], names: ["a": "x"] }
}

fun main() {
    // map remove, set and read-modify-write with a key that copies or grows
    var h = fresh()
    h.m.remove(h.snap(2))
    print(f"{h.m.len()} {h.saved.len()} {h.saved.contains(2)}")
    h = fresh()
    h.m.remove(h.grow(2))
    print(f"{h.m.len()} {h.m.contains(2)} {h.m[399]}")
    h = fresh()
    h.m[h.snap(7)] = 70
    print(f"{h.m.len()} {h.saved.len()} {h.saved.contains(7)}")
    h = fresh()
    h.m[h.grow(2)] = 99
    print(f"{h.m.len()} {h.m[2]} {h.m[150]}")
    h = fresh()
    h.names[h.key("b")] = "y"
    print(f"{h.names.len()} {h.names["b"]} {h.names["b!"]}")
    // list elements
    h = fresh()
    h.xs[h.snap(1)] = 99
    print(f"{h.xs[1]} {h.xs_saved[1]}")
    h = fresh()
    h.xs[h.grow(1)] = 77
    print(f"{h.xs[1]} {h.xs.len()}")
    h = fresh()
    h.grid[h.bump()][h.bump()] = 5
    print(f"{h.grid[1][2]} {h.grid[2][1]} {h.i}")
    h = fresh()
    h.xs[h.xs.len() - 1] = 9
    print(h.xs[2])
    // pushes
    h = fresh()
    h.xs.push(h.snap(4))
    print(f"{h.xs.len()} {h.xs_saved.len()}")
    h = fresh()
    h.xs.push(h.grow(5))
    print(f"{h.xs[^1]} {h.xs.len()}")
    // a builder
    h = fresh()
    h.sb.append("a")
    h.sb.append(h.snap_sb("b"))
    print(f"{h.sb.build()} {h.sb_saved.build()}")
    h = fresh()
    h.sb.append("abcdef", h.bump(), h.bump() + 2)
    print(h.sb.build())
    // methods writing their receiver, with an argument that grows it
    h = fresh()
    h.xs.put_at(h.grow(1), 55)
    print(f"{h.xs[1]} {h.xs.len()}")
    h = fresh()
    h.cs[0].inc(h.grow(3))
    print(f"{h.cs[0].n} {h.cs.len()}")
    // locals, with an `if` that copies
    var ys = [1, 2, 3]
    var zs: [int] = []
    ys[if true { zs = ys; 0 } else { 1 }] = 50
    print(f"{ys[0]} {zs[0]}")
    ys.push(if true { zs = ys; 0 } else { 1 })
    print(f"{ys.len()} {zs.len()}")
    var m2 = [1: 10, 2: 20, 3: 30]
    m2.remove(if m2.len() > 0 { var i = 100; while i < 300 { m2[i] = i; i += 1 }; 2 } else { 0 })
    print(f"{m2.len()} {m2.contains(2)}")
    // in a match arm's expression, which is no scope of its own
    for k in 0..3 {
        h = fresh()
        match k {
            0 => h.sb.append(if k == 0 { "zero" } else { "other" }),
            1 => h.xs.put_at(h.snap(1), 5),
            _ => h.m.remove(if k > 1 { h.grow(2) } else { 3 }),
        }
        print(f"{k}: {h.sb.build()} {h.xs[1]} {h.xs_saved.len()} {h.m.len()}")
    }
    var saved2: [int: int] = [:]
    m2[if true { saved2 = m2; 5 } else { 6 }] = 1
    print(f"{m2.len()} {saved2.len()}")
}
""",
    "recursive_enums_across_tasks": r"""// H3 (MYLA-415): recursive enums crossing between tasks and actors: handed
// to a child while the parent keeps them, returned by a child, awaited by
// a sibling, kept by an actor, inside structs, lists and options
import std.task as task

enum L { Nil, Cons(int, L) }
enum T { Leaf, Bin(T, int, T) }

struct Held { name: str, tree: T, lists: [L] }

fun head(l: L) -> int { return match l { Cons(k, _) => k, Nil => -1 } }
fun count(l: L) -> int { return match l { Cons(_, r) => 1 + count(r), Nil => 0 } }
fun size(t: T) -> int { return match t { Leaf => 0, Bin(l, _, r) => size(l) + 1 + size(r) } }
fun sum(t: T) -> int { return match t { Leaf => 0, Bin(l, v, r) => sum(l) + v + sum(r) } }

fun tree(n: int) -> T {
    var t = T.Leaf
    for i in 0..n { t = T.Bin(t, i, T.Bin(T.Leaf, i * 10, T.Leaf)) }
    return t
}

fun upto(n: int) -> L {
    var l = L.Nil
    for i in 0..n { l = L.Cons(i, l) }
    return l
}

async fun crossing(l: L) -> int { return head(l) + count(l) }
async fun make(n: int) -> T { return tree(n) }
async fun make_list(n: int) -> L { return upto(n) }
async fun keep(h: Held) -> Held {
    var out = h
    out.lists.push(L.Cons(99, h.lists[0]))
    return out
}
async fun maybe(n: int) -> Option<T> {
    if n == 0 { return None }
    return Some(tree(n))
}

actor Shelf { trees: [T], last: L }
impl Shelf {
    fun put(var self, t: T) -> int {
        self.trees.push(t)
        return self.trees.len()
    }
    fun set_last(var self, l: L) { self.last = l }
    fun total(self) -> int {
        var s = 0
        for t in self.trees { s += sum(t) }
        return s + count(self.last)
    }
    fun first(self) -> T { return self.trees[0] }
}

#main
async fun main() {
    // shared with the parent, which reads it again afterwards
    let l = L.Cons(1, L.Cons(2, L.Nil))
    async let c = crossing(l)
    print(await c)
    print(count(l))
    // a child's result
    async let a = make(4)
    let t = await a
    print(size(t))
    print(sum(t))
    async let b = make_list(5)
    print(count(await b))
    // a struct holding them, both ways
    let h = Held { name: "h", tree: t, lists: [l, upto(3)] }
    async let k = keep(h)
    let h2 = await k
    print(f"{h2.name} {size(h2.tree)} {h2.lists.len()} {head(h2.lists[2])} {count(h2.lists[2])} {h.lists.len()}")
    async let m = maybe(3)
    match await m {
        Some(x) => print(size(x)),
        None => print("none"),
    }
    // a list of them through task.all
    let jobs: [async () -> T] = [async () => tree(1), async () => tree(2), async () => tree(3)]
    let ts = await task.all(jobs)
    var s = 0
    for x in ts { s += size(x) }
    print(s)
    // an actor keeps them
    let shelf = Shelf { trees: [], last: L.Nil }
    print(await shelf.put(t))
    print(await shelf.put(tree(2)))
    await shelf.set_last(l)
    print(await shelf.total())
    let f = await shelf.first()
    print(size(f) == size(t))
    // the parent's copies are still whole
    print(sum(t))
    print(count(l))
}
""",
    "closures_capturing_recursive_enums_across_tasks": r"""// B1 (MYLA-415): a closure held in a variable that captures a recursive
// enum crosses to a child task, an actor or a channel as a deep copy: its
// environment holds the enum inline (its cell's contents), not as a box.
// Also a partial, a struct holding the closure, nested closures, a list of
// them to `task.all`, and a channel.
import std.task as task

enum Lst { Nil, Cons(int, Lst) }
enum T { Leaf, Bin(T, int, T) }

fun total(l: Lst) -> int {
    return match l {
        Cons(n, rest) => n + total(rest)
        Nil => 0
    }
}

fun size(t: T) -> int { return match t { Leaf => 0, Bin(l, _, r) => size(l) + 1 + size(r) } }

fun add(l: Lst, k: int) -> int { return total(l) + k }

struct Holder { name: str, f: () -> int }

async fun run(f: () -> int) -> int { return f() }
async fun run_held(h: Holder) -> int { return h.f() + h.name.len() }
async fun run_partial(g: (int) -> int) -> int { return g(10) }
async fun maker(n: int) -> () -> int {
    var l = Lst.Nil
    for i in 0..n { l = Lst.Cons(i, l) }
    return () => total(l)
}

actor Keep { f: () -> int }
impl Keep {
    fun put(var self, f: () -> int) { self.f = f }
    fun call(self) -> int { return self.f() }
}

#main
async fun main() {
    let cap = Lst.Cons(1, Lst.Cons(2, Lst.Nil))
    let tr = T.Bin(T.Bin(T.Leaf, 1, T.Leaf), 2, T.Leaf)
    let f = () => total(cap)
    async let a = run(f)
    print(await a)
    // two recursive enums and a string beside them
    let label = "tree"
    let g = () => total(cap) * 100 + size(tr) * 10 + label.len()
    async let b = run(g)
    print(await b)
    // a partial
    let p = add(cap, _)
    async let c = run_partial(p)
    print(await c)
    // a struct holding the closure
    let h = Holder { name: "held", f: f }
    async let d = run_held(h)
    print(await d)
    // nested closures
    let outer = () => f() + g()
    async let e = run(outer)
    print(await e)
    // a list of them to task.all
    let jobs: [async () -> int] = [async () => f(), async () => g()]
    let rs = await task.all(jobs)
    print(rs[0] + rs[1])
    // an actor keeps it
    let k = Keep { f: () => 0 }
    await k.put(f)
    print(await k.call())
    // through a channel
    let ch: task.Channel<() -> int> = task.channel(2)
    let s1 = await ch.send(f)
    let s2 = await ch.send(g)
    match await ch.recv() {
        Some(x) => print(x())
        None => print("none")
    }
    match await ch.recv() {
        Some(x) => print(x())
        None => print("none")
    }
    // a child's closure, which its siblings and the parent share (a clone)
    async let m = maker(5)
    async let s3 = run(await m)
    async let s4 = run(await m)
    let mine = await m
    print(await s3 + await s4 + mine())
    // the parent's copies are still whole
    print(f() + g() + p(1) + total(cap) + size(tr))
}
""",
    "operands_kept_when_a_later_operand_writes_their_variable": r"""// B2 (MYLA-543): an operator's left operand, read from a variable's
// container, kept while the right one replaces that container (a `var self`
// method); a compound assignment's old value too. Native code read freed
// cells (`s121!`, `out of memory`)
struct P { x: int, s: str }

#derive(Eq)
struct Q { name: str, n: int }

impl Add for P {
    fun add(self, other: P) -> P { return P { x: self.x + other.x, s: self.s + other.s } }
}

struct H {
    xs: [str], m: [int: str], g: [[str]], ps: [P], qs: [Q], name: str,
    t: [(str, int)], fs: [(int) -> str], n: int,
}

fun mk(n: int) -> str { return f"s{n}" }

fun fresh() -> H {
    return H {
        xs: [mk(10), mk(11), mk(12)], m: [0: mk(20), 1: mk(21)], g: [[mk(30), mk(31)], [mk(32), mk(33)]],
        ps: [P { x: 1, s: mk(40) }], qs: [Q { name: mk(41), n: 1 }], name: mk(50), t: [(mk(60), 6)],
        fs: [(i: int) => mk(70 + i), (i: int) => mk(80 + i)], n: 0,
    }
}

impl H {
    // every container of `self` replaced: what was read from them released
    fun repl(var self) {
        self.xs = [mk(110), mk(111), mk(112)]
        self.m = [0: mk(120), 1: mk(121)]
        self.g = [[mk(130), mk(131)], [mk(132), mk(133)]]
        self.ps = [P { x: 9, s: mk(140) }]
        self.qs = [Q { name: mk(141), n: 9 }]
        self.name = mk(150)
        self.t = [(mk(160), 16)]
        self.fs = [(i: int) => mk(170 + i), (i: int) => mk(180 + i)]
        self.n += 1
    }
    fun s(var self) -> str { self.repl(); return "!" }
    fun k(var self) -> int { self.repl(); return 1 }
    fun l(var self) -> [str] { self.repl(); return [mk(10), mk(11), mk(12)] }
    fun p(var self) -> P { self.repl(); return P { x: 2, s: "p" } }
    fun q(var self) -> Q { self.repl(); return Q { name: mk(41), n: 1 } }
    fun tu(var self) -> (str, int) { self.repl(); return (mk(60), 6) }
    fun shrink(var self) -> str {
        self.m.remove(1)
        self.xs.truncate(1)
        return "v"
    }
}

fun shl(xs: [str]) -> str {
    var sb = StringBuilder()
    for x in xs { sb.append(x + ",") }
    return sb.build()
}

fun main() {
    // operators
    var h = fresh()
    print(h.xs[0] + h.s())
    h = fresh()
    print(h.name + h.s())
    h = fresh()
    print(h.g[0][0] + (h.xs[1] + h.s()))
    h = fresh()
    print(h.m[0] + h.s())
    h = fresh()
    print(f"{h.xs[0] == h.s()} {h.xs[0] < h.s()}")
    h = fresh()
    print(f"{h.xs == h.l()}")
    h = fresh()
    print(f"{h.t[0] == h.tu()}")
    h = fresh()
    print(f"{h.qs[0] == h.q()}")
    h = fresh()
    let sum = h.ps[0] + h.p()
    print(f"{sum.x} {sum.s}")
    h = fresh()
    print(h.xs[0] + (if h.k() > 0 { "T" } else { "F" }))
    // compound assignments
    h = fresh()
    h.xs[0] += h.s()
    print(shl(h.xs))
    h = fresh()
    h.m[1] += h.shrink()
    print(f"{h.m[1]} {h.m.len()} {shl(h.xs)}")
}
""",
    "bases_kept_when_their_index_writes_their_variable": r"""// B2 (MYLA-543): an index's or a slice's base kept while the index replaces
// the container it is read from; and a function value called from a list.
// Native code read freed cells (`list index 1 out of bounds (len 0)`)
struct P { x: int, s: str }

#derive(Eq)
struct Q { name: str, n: int }

impl Add for P {
    fun add(self, other: P) -> P { return P { x: self.x + other.x, s: self.s + other.s } }
}

struct H {
    xs: [str], m: [int: str], g: [[str]], ps: [P], qs: [Q], name: str,
    t: [(str, int)], fs: [(int) -> str], n: int,
}

fun mk(n: int) -> str { return f"s{n}" }

fun fresh() -> H {
    return H {
        xs: [mk(10), mk(11), mk(12)], m: [0: mk(20), 1: mk(21)], g: [[mk(30), mk(31)], [mk(32), mk(33)]],
        ps: [P { x: 1, s: mk(40) }], qs: [Q { name: mk(41), n: 1 }], name: mk(50), t: [(mk(60), 6)],
        fs: [(i: int) => mk(70 + i), (i: int) => mk(80 + i)], n: 0,
    }
}

impl H {
    // every container of `self` replaced: what was read from them released
    fun repl(var self) {
        self.xs = [mk(110), mk(111), mk(112)]
        self.m = [0: mk(120), 1: mk(121)]
        self.g = [[mk(130), mk(131)], [mk(132), mk(133)]]
        self.ps = [P { x: 9, s: mk(140) }]
        self.qs = [Q { name: mk(141), n: 9 }]
        self.name = mk(150)
        self.t = [(mk(160), 16)]
        self.fs = [(i: int) => mk(170 + i), (i: int) => mk(180 + i)]
        self.n += 1
    }
    fun s(var self) -> str { self.repl(); return "!" }
    fun k(var self) -> int { self.repl(); return 1 }
    fun l(var self) -> [str] { self.repl(); return [mk(10), mk(11), mk(12)] }
    fun p(var self) -> P { self.repl(); return P { x: 2, s: "p" } }
    fun q(var self) -> Q { self.repl(); return Q { name: mk(41), n: 1 } }
    fun tu(var self) -> (str, int) { self.repl(); return (mk(60), 6) }
    fun shrink(var self) -> str {
        self.m.remove(1)
        self.xs.truncate(1)
        return "v"
    }
}

fun shl(xs: [str]) -> str {
    var sb = StringBuilder()
    for x in xs { sb.append(x + ",") }
    return sb.build()
}

fun main() {
    // an index's and a slice's base
    var h = fresh()
    print(h.xs[h.k()])
    h = fresh()
    print(h.g[0][h.k()])
    h = fresh()
    print(h.g[h.k()][0])
    h = fresh()
    print(h.m[h.k()])
    h = fresh()
    print(h.ps[h.k() - 1].s)
    h = fresh()
    print(f"{h.xs[0][h.k()]}")
    h = fresh()
    print(shl(h.xs[h.k():]))
    h = fresh()
    print(h.xs[0][h.k():])
    // a function value called from a list
    h = fresh()
    print(h.fs[0](h.k()))
    print(h.n)
}
""",
    "holes_and_keys_kept_when_a_later_one_writes_their_variable": r"""// B2 (MYLA-543): an f-string's or `format`'s hole, a map literal's key and a
// `match` scrutinee's operand kept while a later operand replaces the
// container they are read from. Native code read freed cells
struct P { x: int, s: str }

#derive(Eq)
struct Q { name: str, n: int }

impl Add for P {
    fun add(self, other: P) -> P { return P { x: self.x + other.x, s: self.s + other.s } }
}

struct H {
    xs: [str], m: [int: str], g: [[str]], ps: [P], qs: [Q], name: str,
    t: [(str, int)], fs: [(int) -> str], n: int,
}

fun mk(n: int) -> str { return f"s{n}" }

fun fresh() -> H {
    return H {
        xs: [mk(10), mk(11), mk(12)], m: [0: mk(20), 1: mk(21)], g: [[mk(30), mk(31)], [mk(32), mk(33)]],
        ps: [P { x: 1, s: mk(40) }], qs: [Q { name: mk(41), n: 1 }], name: mk(50), t: [(mk(60), 6)],
        fs: [(i: int) => mk(70 + i), (i: int) => mk(80 + i)], n: 0,
    }
}

impl H {
    // every container of `self` replaced: what was read from them released
    fun repl(var self) {
        self.xs = [mk(110), mk(111), mk(112)]
        self.m = [0: mk(120), 1: mk(121)]
        self.g = [[mk(130), mk(131)], [mk(132), mk(133)]]
        self.ps = [P { x: 9, s: mk(140) }]
        self.qs = [Q { name: mk(141), n: 9 }]
        self.name = mk(150)
        self.t = [(mk(160), 16)]
        self.fs = [(i: int) => mk(170 + i), (i: int) => mk(180 + i)]
        self.n += 1
    }
    fun s(var self) -> str { self.repl(); return "!" }
    fun k(var self) -> int { self.repl(); return 1 }
    fun l(var self) -> [str] { self.repl(); return [mk(10), mk(11), mk(12)] }
    fun p(var self) -> P { self.repl(); return P { x: 2, s: "p" } }
    fun q(var self) -> Q { self.repl(); return Q { name: mk(41), n: 1 } }
    fun tu(var self) -> (str, int) { self.repl(); return (mk(60), 6) }
    fun shrink(var self) -> str {
        self.m.remove(1)
        self.xs.truncate(1)
        return "v"
    }
}

fun shl(xs: [str]) -> str {
    var sb = StringBuilder()
    for x in xs { sb.append(x + ",") }
    return sb.build()
}

fun main() {
    // holes
    var h = fresh()
    print(f"{h.xs[0]}{h.s()}{h.xs[0]}")
    h = fresh()
    print(format("{}-{}", h.g[0][0], h.s()))
    // a map literal's key
    h = fresh()
    let m = [h.xs[0]: h.s()]
    for k in m { print(k + m[k]) }
    // a scrutinee
    h = fresh()
    print(match h.xs[0] + h.s() { "s10!" => "ok", _ => "bad" })
}
""",
    "a_method_call_takes_its_receivers_place_first": r"""// C9, D193 (MYLA-543): `place[i()].push(v())` takes the receiver's place
// (its indices and keys) before the argument, as every method call does and
// as the interpreter did; native code ran the value first (`push: 21`)
struct C { n: int, g: [[int]], m: [int: [int]] }

impl C {
    fun k(var self) -> int {
        self.n = self.n * 10 + 1
        return 0
    }
    fun v(var self) -> int {
        self.n = self.n * 10 + 2
        return 7
    }
}

fun at(n: int) -> int {
    print(f"index {n}")
    return 0
}

fun val(n: int) -> int {
    print(f"value {n}")
    return n
}

fun main() {
    // C9
    var c = C { n: 0, g: [[1]], m: [0: [1]] }
    c.g[c.k()].push(c.v())
    print(f"push: {c.n} {c.g[0].len()}")
    c.n = 0
    c.m[c.k()].push(c.v())
    print(f"map element push: {c.n} {c.m[0].len()}")
    c.n = 0
    c.g[c.n].push(c.v())
    print(f"index read first: {c.n} {c.g[0].len()}")
    var g: [[int]] = [[]]
    g[at(1)].push(val(2))
    var bs = [StringBuilder()]
    bs[at(3)].append(f"{val(4)}")
    print(f"{g[0].len()} {bs[0].build()}")
}
""",
    "recursive_enums_as_map_keys": r"""// C11, D194 (MYLA-543): a recursive enum is a map key natively too, as
// interpreted: written, read, updated, removed, iterated, copied, handed to
// a child task, in a literal; natively `main can't be lowered to the IR`
import std.task as task

#derive(Eq, Hash)
enum Lst { Nil, Cons(int, Lst) }

#derive(Eq, Hash)
enum T { Leaf(str), Bin(T, T) }

fun upto(n: int) -> Lst {
    var l = Lst.Nil
    for i in 0..n { l = Lst.Cons(i, l) }
    return l
}

fun total(l: Lst) -> int {
    return match l {
        Cons(n, rest) => n + total(rest)
        Nil => 0
    }
}

async fun count_in(m: [Lst: int], k: Lst) -> int { return m.get_or(k, -1) + m.len() }

#main
async fun main() {
    var m: [Lst: int] = [:]
    for i in 0..6 { m[upto(i)] = i * 10 }
    print(m.len())
    print(m[upto(3)])
    print(m.contains(upto(5)))
    print(m.contains(Lst.Cons(9, Lst.Nil)))
    m[upto(2)] += 5
    print(m[upto(2)])
    m.remove(upto(4))
    print(f"{m.len()} {m.contains(upto(4))}")
    var s = 0
    for k in m { s += total(k) * 100 + m[k] }
    print(s)
    let ks = m.keys()
    print(f"{ks.len()} {total(ks[ks.len() - 1])}")
    print(m.get(upto(1)) == Some(10))
    print(m.get_or(upto(7), -1))
    // a copy keeps its keys when the original changes
    var c = m
    c[Lst.Cons(42, Lst.Nil)] = 42
    m.remove(upto(0))
    print(f"{m.len()} {c.len()} {c[upto(0)]} {c[Lst.Cons(42, Lst.Nil)]}")
    // to a child task, the parent keeping its own
    async let a = count_in(c, upto(5))
    print(await a)
    print(c.len())
    // a literal, and a key holding strings
    let t: [T: str] = [T.Leaf("a"): "leaf", T.Bin(T.Leaf("a"), T.Leaf("b")): "bin"]
    print(t[T.Bin(T.Leaf("a"), T.Leaf("b"))] + " " + t[T.Leaf("a")])
    var many: [Lst: int] = [:]
    for i in 0..2000 { many[upto(i % 50)] = i }
    print(f"{many.len()} {many[upto(49)]}")
}
""",
    "actors_store_every_heap_type": r"""// H2 (MYLA-415): an actor's method keeps an argument of every heap type in
// its state, in a program with tasks, the arguments temporaries or the
// caller's own values, which the caller then changes
enum Shape { Dot, Line(int, int) }
enum L { Nil, Cons(int, L) }
struct Rec { name: str, tags: [str] }

actor Store {
    s: str,
    xs: [int],
    m: [str: int],
    sb: StringBuilder,
    r: Rec,
    t: (str, [int]),
    o: Option<str>,
    e: Shape,
    l: L,
    f: (int) -> int,
    nested: [[str]],
}

impl Store {
    fun put_s(var self, v: str) -> int { self.s = v; return self.s.len() }
    fun put_xs(var self, v: [int]) -> int { self.xs = v; return self.xs.len() }
    fun put_m(var self, v: [str: int]) -> int { self.m = v; return self.m.len() }
    fun put_sb(var self, v: StringBuilder) { self.sb = v }
    fun put_r(var self, v: Rec) -> int { self.r = v; return self.r.tags.len() }
    fun put_t(var self, v: (str, [int])) { self.t = v }
    fun put_o(var self, v: Option<str>) { self.o = v }
    fun put_e(var self, v: Shape) { self.e = v }
    fun put_l(var self, v: L) { self.l = v }
    fun put_f(var self, v: (int) -> int) { self.f = v }
    fun put_nested(var self, v: [[str]]) { self.nested = v }
    fun put_two(var self, a: str, b: [int]) -> int {
        self.s = a + self.s
        self.xs = b
        return self.s.len() + self.xs.len()
    }
    fun report(var self) -> str {
        let lsum = match self.l { Cons(k, _) => k, Nil => -1 }
        let e = match self.e { Dot => 0, Line(a, b) => a + b }
        let g = self.f
        var sb = self.sb
        sb.append("!")
        return f"{self.s} {self.xs.len()} {self.m.get_or("a", 0)} {sb.build()} {self.r.name}/{self.r.tags.len()} {self.t.0}{self.t.1.len()} {self.o.unwrap_or("-")} {e} {lsum} {g(1)} {self.nested.len()}"
    }
}

async fun helper() -> int { return 1 }

#main
async fun main() {
    async let h = helper()
    print(await h)
    let st = Store { s: "", xs: [], m: [:], sb: StringBuilder(), r: Rec { name: "", tags: [] }, t: ("", []), o: None, e: Shape.Dot, l: L.Nil, f: (x: int) => x, nested: [] }
    print(await st.put_s(f"value {7}"))
    print(await st.put_xs([1, 2, 3]))
    var mine = [10, 20]
    print(await st.put_xs(mine))
    mine.push(30)
    print(await st.put_m(["a": 1, "b": 2]))
    var sb = StringBuilder()
    sb.append("built")
    await st.put_sb(sb)
    sb.append(" more")
    var tags = ["x", "y"]
    print(await st.put_r(Rec { name: "rec", tags: tags }))
    tags.push("z")
    await st.put_t(("t", [1, 2, 3, 4]))
    await st.put_o(Some("some"))
    await st.put_e(Shape.Line(3, 4))
    await st.put_l(L.Cons(5, L.Cons(6, L.Nil)))
    let k = 41
    await st.put_f((x: int) => x + k)
    await st.put_nested([["a"], ["b", "c"]])
    print(await st.report())
    print(await st.put_two("pre-", mine))
    print(await st.report())
    print(f"{mine.len()} {tags.len()} {sb.build()}")
}
""",
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


# MYLA-157: a `?` failing in a list or map literal after an element that owns
# a heap value (a 1 KB string): the half-built literal and that element must
# be released, or 1.2M iterations leak over a gigabyte (past the Python
# backend's 1 GiB arena; the self-hosted gate checks its peak).
STRESS_TRY_IN_LITERAL_SRC = (
    "fun fails(i: int) -> Result<str, str> {\n    return Err(\"no\")\n}\n"
    "fun in_list(i: int, pad: str) -> Result<[str], str> {\n"
    "    let xs = [pad + f\"{i}\", fails(i)?]\n    return Ok(xs)\n}\n"
    "fun in_map(i: int, pad: str) -> Result<[str: str], str> {\n"
    "    let m = [\"a\": pad + f\"{i}\", \"b\": fails(i)?]\n    return Ok(m)\n}\n"
    "#main\nfun main() {\n"
    "    var sb = StringBuilder()\n"
    "    for i in 0..1000 {\n        sb.append(\"x\")\n    }\n"
    "    let pad = sb.build()\n"
    "    var errs = 0\n"
    "    for k in 0..600000 {\n"
    "        match in_list(k, pad) { Ok(_) => { } Err(_) => { errs = errs + 1 } }\n"
    "        match in_map(k, pad) { Ok(_) => { } Err(_) => { errs = errs + 1 } }\n"
    "    }\n    print(errs)\n}\n"
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


# MYLA-380: a million pipelines of new strings through a generic adapter,
# with `continue`, `break` and a `return` from inside a loop over an
# iterator: a missed drop of the iterator, of what `next` gives or of the
# adapter's results would exhaust the arena
STRESS_ITERATORS_SRC = """struct ListIter<T> {
    xs: [T],
    i: int,
}

impl<T> Iterator<T> for ListIter<T> {
    fun next(var self) -> Option<T> {
        if self.i >= self.xs.len() { return None }
        self.i += 1
        return Some(self.xs[self.i - 1])
    }
}

struct Map<I, T, U> {
    inner: I,
    f: (T) -> U,
}

impl<I: Iterator<T>, T, U> Iterator<U> for Map<I, T, U> {
    fun next(var self) -> Option<U> {
        return match self.inner.next() {
            Some(v) => Some(self.f(v))
            None => None
        }
    }
}

fun make(n: int, k: int) -> [str] {
    var out: [str] = []
    for i in 0..n { out.push(f"item-{i}-{k}-padding") }
    return out
}

fun first_long<I: Iterator<str>>(it: I) -> int {
    for s in it {
        if s.len() > 22 { return s.len() }
    }
    return 0
}

fun main() {
    var total = 0
    for k in 0..1000000 {
        let words = Map { inner: ListIter { xs: make(8, k), i: 0 }, f: (s: str) => s + "!" }
        for w in words {
            if w.len() % 2 == 0 { continue }
            total += w.len()
            if total % 5 == 0 { break }
        }
        total += first_long(words)
    }
    print(total)
}
"""


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
        "        h.spare.push(grow(5))\n"
        "        let t = h.spare.pop()\n"
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
        "        _ => s.len(),\n"
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
        "        total = total + g.len() + p.tag.len() + label(p.tag)\n"
        "        var w = p.name\n"
        "        w = w + w\n"
        "        if w.len() > 100 {\n"
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
    "    for i in 0..n {\n        out.push(i)\n    }\n    return out\n}\n"
    "#main\nfun main() {\n"
    "    var acc = 0\n"
    "    for r in 0..200000 {\n"
    "        let xs = make(20)\n"          # fresh list each iteration (grows, drops)
    "        var ys = xs\n"                 # share -> CoW on next write
    "        ys[0] = 5\n"                   # forces a clone of the shared buffer
    "        ys.push(99)\n"
    "        let dropped = ys.pop()\n"
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
    "        c.remove(1)\n"               # rebuild deletion (alloc + value move)
    "        acc = acc + m.len() - m.len()\n"  # net 0, but keeps m live
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
    "        m.remove((r + 3) % 7)\n"
    "        total = total + m.len()\n"
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
    "    var i = 0\n    while i < n {\n        sb.append(\"abcde\")\n"
    "        i = i + 1\n    }\n    return sb\n}\n"
    "#main\nfun main() {\n"
    "    var acc = 0\n"
    "    for r in 0..200000 {\n"
    "        var sb = make(8)\n"            # fresh builder each iteration (grows)
    "        var c = sb\n"                   # share -> CoW on next write
    "        c.append(\"Z\")\n"             # clones the shared buffer, may grow
    "        acc = acc + sb.len() - sb.len()\n"  # net 0, but keeps sb live
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
    "        fns.push((n: int) => n + cap)\n"
    "        fns.push((n: int) => n + cap + 1)\n"
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
    "        var r = self.items\n        for x in other.items { r.push(x) }\n"
    "        return Bag { items: r }\n    }\n}\n"
    "fun total<T: Add>(xs: [T], zero: T) -> T {\n"
    "    var acc = zero\n    for x in xs { acc = acc + x }\n    return acc\n}\n"
    "#main\nfun main() {\n"
    "    var checksum = 0\n"
    "    for r in 0..200000 {\n"
    "        let a = Bag { items: [r, r] }\n"
    "        let b = Bag { items: [r] }\n"
    "        let c = total([a, b], Bag { items: [] })\n"
    "        checksum = checksum + c.items.len()\n"
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
    "    return Ok(m.len())\n}\n"
    "fun by_index(i: int) -> Result<int, str> {\n"
    "    var xs: [[int]] = [[]]\n"
    f"    xs[fail(i)?] = {_BIG_LIST}\n"
    "    return Ok(xs.len())\n}\n"
    "fun by_holder(i: int) -> Result<int, str> {\n"
    "    var xss: [[[int]]] = [[]]\n"
    f"    xss[fail(i)?].push({_BIG_LIST})\n"
    "    return Ok(xss.len())\n}\n"
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
    "        xs.push(f\"{r}:{c.n}\")\n"
    "        let key = f\"k{r}\"\n"
    "        m[key] = b.len()\n"
    "        let v = m[key]\n"
    "        if m.len() > 50 {\n"
    "            for k in m.keys() {\n                m.remove(k)\n            }\n"
    "        }\n"
    "        var sb = StringBuilder()\n"
    "        sb.append(b)\n"
    "        let built = sb.build()\n"
    "        total = total + xs.len() + built.len() - v\n"
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
    "    var out: [int] = []\n    for i in 0..n {\n        out.push(i)\n    }\n    return out\n}\n"
    "fun nonempty(xs: [int]) -> bool {\n    return xs.len() > 0\n}\n"
    "#main\nfun main() {\n"
    "    var acc = 0\n"
    "    for r in 0..600000 {\n"
    "        if nonempty(make(200)) {\n            acc = acc + 1\n        }\n"
    "        var k = 0\n"
    "        while k < make(30).len() {\n            k = k + 10\n        }\n"
    "        for i in 0..make(100).len() - 99 {\n            acc = acc + k\n        }\n"
    "        match r {\n            x if nonempty(make(50)) => {\n                acc = acc + 1\n            },\n            _ => {},\n        }\n"
    "        if r % 2 == 0 && nonempty(make(20)) {\n            acc = acc + 1\n        }\n"
    "        let b = r % 3 == 0 || make(10).len() > 5\n"
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
    "    var out: [int] = []\n    for i in 0..n {\n        out.push(i)\n    }\n    return out\n}\n"
    "fun find(xs: [[int]], i: int) -> Option<[int]> {\n"
    "    if i < xs.len() {\n        return Some(xs[i])\n    }\n    return None\n}\n"
    "fun first(xs: [[int]]) -> [int] {\n"
    "    match find(xs, 0) {\n        Some(v) => {\n            return v\n        },\n        None => {},\n    }\n"
    "    return []\n}\n"
    "fun total(xs: [[int]]) -> int {\n"
    "    var n = 0\n    var i = 0\n"
    "    while true {\n"
    "        match find(xs, i) {\n"
    "            Some(v) => {\n"
    "                i = i + 1\n"
    "                if v.len() == 100 {\n                    continue\n                }\n"
    "                n = n + v.len()\n"
    "            },\n"
    "            None => {\n                break\n            },\n"
    "        }\n"
    "    }\n"
    "    return n\n}\n"
    "#main\nfun main() {\n"
    "    var acc = 0\n"
    "    for r in 0..600000 {\n"
    "        let xs = [make(200), make(100), make(50)]\n"
    "        acc = acc + first(xs).len() + total(xs)\n"
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
    "    var out: [int] = []\n    for i in 0..n {\n        out.push(i)\n    }\n    return out\n}\n"
    "#main\nfun main() {\n"
    "    var acc = 0\n"
    "    for r in 0..600000 {\n"
    "        let b = Box.Full(make(200))\n"
    "        let xs = items(b)\n"
    "        let ys = match b {\n            Box.Full(zs) => zs,\n            Box.Empty => xs,\n        }\n"
    "        acc = acc + xs.len() + ys.len() - (match b {\n            Box.Full(ws) => ws,\n            Box.Empty => xs,\n        }).len()\n"
    "    }\n"
    "    print(acc)\n}\n"
)


STRESS_FRAGMENTED_FREE_SRC = (
    # Leaves 8000 freed cells of 8000 different sizes behind (each `keys(m)` on
    # a growing map frees a list one slot longer than the last), then allocates
    # 30000 small lists that none of those cells fit. An allocator that scans
    # one free list on every allocation does 240 million probes here;
    # size-class free lists find "nothing free" at once (MYLA-16).
    "#main\nfun main() {\n"
    "    var m: [int: int] = [:]\n"
    "    var i = 0\n"
    "    while i < 8000 {\n"
    "        m[i] = i\n"
    "        let ks = m.keys()\n"
    "        i = i + 1\n"
    "    }\n"
    "    var keep: [[int]] = []\n"
    "    var j = 0\n"
    "    while j < 30000 {\n"
    "        keep.push([j, j])\n"
    "        j = j + 1\n"
    "    }\n"
    "    print(keep.len() + m.len())\n}\n"
)

STRESS_LARGE_SIZES_SRC = (
    # Builds and drops 20000 strings of 20000 different sizes above 4 KiB
    # (1.7 GB in all). A freed large cell kept for an allocation of exactly its
    # size is never used again and the 1 GiB arena runs out; size classes for
    # large cells reuse them (MYLA-80, found as the language server's memory
    # growing with every check).
    "#main\nfun main() {\n"
    "    var sb = StringBuilder()\n"
    "    for k in 0..170000 { sb.append_byte('x') }\n"
    "    let big = sb.build()\n"
    "    var total = 0\n"
    "    for i in 0..20000 {\n"
    "        var part = StringBuilder()\n"
    "        part.append(big, 0, 4100 + 8 * i)\n"
    "        let s = part.build()\n"
    "        total = total + s.len() % 7\n"
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
    "        for k in 0..250 { xs.push(k) }\n"       # 1 KB a list: a leak exhausts the arena
    "        var m: [int: int] = [:]\n"
    "        m[i % 7] = 1\n"
    "        total = total + first_big(xs) % 3 + any_key(m) + nested([[1, 2], [3, i]])\n"
    "    }\n"
    "    print(total)\n}\n"
)

# Maps with compound keys (D163, MYLA-313): a struct key holding a string
# and a tuple key holding a string and a list, their words in the slots,
# inserted, overwritten, removed, listed, shared by a copy and dropped,
# far more often than the arena holds, so the keys' references must be
# taken and given back.
STRESS_MAP_COMPOUND_KEY_SRC = (
    "#derive(Eq, Hash)\n"
    "struct Who {\n"
    "    name: str,\n"
    "    n: int,\n"
    "}\n"
    "\n"
    "#main\n"
    "fun main() {\n"
    "    var total = 0\n"
    "    for r in 0..20000 {\n"
    "        var m: [Who: [str]] = [:]\n"
    "        var i = 0\n"
    "        while i < 12 {\n"
    "            let w = Who { name: f\"w{i % 5}\", n: r }\n"
    "            m[w] = [f\"v{i}\", \"x\"]\n"
    "            i += 1\n"
    "        }\n"
    "        let copy = m\n"
    "        m.remove(Who { name: \"w1\", n: r })\n"
    "        m[Who { name: f\"w{r % 3}\", n: r }] = [\"again\"]\n"
    "        for k in m.keys() { total += k.name.len() }\n"
    "        var pairs: [(str, [int]): int] = [:]\n"
    "        pairs[(f\"p{r}\", [r, r])] = 1\n"
    "        pairs[(f\"p{r}\", [r, r])] = 2\n"
    "        total += pairs[(f\"p{r}\", [r, r])] + copy.len() - m.len()\n"
    "    }\n"
    "    print(total)\n"
    "}\n"
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
    "        total = total + docs[\"a\"].len() % 2 + lists[i % 3][0] % 2 + nested[\"x\"][\"k\"] % 2\n"
    "    }\n"
    "    print(total)\n}\n"
)


# A program of three modules for `test_generic_constructors_of_a_module`.
GENERIC_MODULE_DEQUE = """pub struct Deque<T> {
    front: [T],
    back: [T],
}

pub fun new<T>() -> Deque<T> {
    return Deque { front: [], back: [] }
}

pub fun of<T>(xs: [T]) -> Deque<T> {
    return Deque { front: [], back: xs }
}

impl<T> Deque<T> {
    fun push_back(var self, x: T) {
        self.back.push(x)
    }

    fun push_front(var self, x: T) {
        self.front.push(x)
    }

    fun len(self) -> int {
        return self.front.len() + self.back.len()
    }

    fun first(self) -> Option<T> {
        if self.front.len() > 0 {
            return Some(self.front[^1])
        }
        if self.back.len() > 0 {
            return Some(self.back[0])
        }
        return None
    }

    fun emptied<U>(self) -> Deque<U> {
        return new()
    }
}
"""

GENERIC_MODULE_SET = """pub struct Set<T> {
    items: [T],
}

pub fun new<T>() -> Set<T> {
    return Set { items: [] }
}

impl<T: Eq> Set<T> {
    fun insert(var self, x: T) {
        for y in self.items {
            if y == x {
                return
            }
        }
        self.items.push(x)
    }

    fun len(self) -> int {
        return self.items.len()
    }
}
"""

GENERIC_MODULE_MAIN = """import .deque as deque
import .set as set
from .deque import Deque
from .set import Set

struct Graph {
    todo: Deque<int>,
    seen: Set<str>,
}

fun sizes(d: Deque<str>) -> int {
    return d.len()
}

fun main() {
    let d: Deque<int> = deque.new()
    print(d.len())
    var s: Set<str> = set.new()
    s.insert("a")
    s.insert("b")
    s.insert("a")
    print(s.len())
    var g = Graph { todo: deque.new(), seen: set.new() }
    g.todo.push_back(3)
    g.todo.push_front(2)
    g.seen.insert("x")
    print(g.todo.len())
    print(g.todo.first().unwrap_or(0))
    print(g.seen.len())
    print(sizes(deque.new()))
    g.todo = deque.new()
    print(g.todo.len())
    let e: Deque<str> = d.emptied()
    print(e.first().unwrap_or("none"))
    let big: Deque<int64> = deque.of([5000000000])
    print(big.first().unwrap_or(0))
}
"""


# The main module of `test_explicit_type_arguments_of_a_module` (MYLA-373):
# a module's generic functions and a generic method of its type, called with
# explicit type arguments where nothing else would fix them.
EXPLICIT_MODULE_MAIN = """import .deque as deque
import .set as set

fun main() {
    let d = deque.new<int>()
    print(d.len())
    var s = set.new<str>()
    s.insert("a")
    s.insert("a")
    print(s.len())
    print(d.emptied<str>().first().unwrap_or("none"))
    let big = deque.of<int64>([5000000000])
    print(big.first().unwrap_or(0))
    set.new<bool>()
    print(deque.new<char>().len() < 1)
}
"""

# `test_module_types_by_the_module_name` (MYLA-371): a module that re-exports
# another, and a main module naming both modules' types as `m.T` and through
# the re-export as `m.n.T`.
MODULE_TYPES_SHAPES = """pub import .deque as dq

pub struct Shape {
    name: str,
    sides: int,
}

pub typealias Named = (str, int)

pub fun tri() -> Shape {
    return Shape { name: "tri", sides: 3 }
}
"""

MODULE_TYPES_MAIN = """import .deque as deque
import .set as set
import .shapes as shapes

struct Graph {
    todo: deque.Deque<int>,
    seen: set.Set<str>,
}

fun sizes(ds: [deque.Deque<str>]) -> int {
    var n = 0
    for d in ds {
        n += d.len()
    }
    return n
}

fun fresh() -> shapes.dq.Deque<int> {
    return deque.of([7, 8])
}

fun describe(s: shapes.Shape) -> shapes.Named {
    return (s.name, s.sides)
}

fun main() {
    var g = Graph { todo: fresh(), seen: set.new() }
    g.todo.push_front(6)
    g.seen.insert("x")
    print(g.todo.len())
    print(g.todo.first().unwrap_or(0))
    print(g.seen.len())
    let d: deque.Deque<str> = deque.of(["a", "b"])
    print(sizes([d, d, deque.new<str>()]))
    let n = describe(shapes.tri())
    print(f"{n.0} {n.1}")
    let pick: (shapes.dq.Deque<int>) -> int = (q) => q.len()
    print(pick(g.todo))
    let o: Option<set.Set<str>> = Some(g.seen)
    match o {
        Some(s) => print(s.len())
        None => print(-1)
    }
}
"""

TRAIT_FUNCTIONS_ZERO = """// the trait, its impl for a built-in type and generic code over it (D172)
pub trait Zero {
    fun zero() -> Self
    fun label() -> str
}

impl Zero for int {
    fun zero() -> int { return 0 }
    fun label() -> str { return "int" }
}

pub fun sum<T: Zero + Add>(xs: [T]) -> T {
    var s = T.zero()
    for x in xs { s = s + x }
    return s
}

pub fun label_of<T: Zero>() -> str {
    return T.label()
}
"""

TRAIT_FUNCTIONS_MONEY = """// a type of this module with an impl of another module's trait (D172)
from .zero import Zero

pub struct Money {
    cents: int64,
}

impl Zero for Money {
    fun zero() -> Money { return Money { cents: 0 } }
    fun label() -> str { return "money" }
}

impl Add for Money {
    fun add(self, other: Money) -> Money { return Money { cents: self.cents + other.cents } }
}

pub struct Wallet<T> {
    held: [T],
}

impl<T: Zero> Zero for Wallet<T> {
    fun zero() -> Wallet<T> { return Wallet { held: [T.zero()] } }
    fun label() -> str { return "wallet of " + T.label() }
}
"""

TRAIT_FUNCTIONS_MAIN = """// D172 (MYLA-384): the trait in one module, an impl in another, the
// calls in a third: on a type imported by name, on a module's type
// (`m.Money.zero()`), on a built-in type, and through the trait's module's
// generic functions
import .zero as z
import .money as m
from .money import Money, Wallet

fun main() {
    print(Money.zero().cents)
    print(m.Money.zero().cents)
    print(m.Money.label())
    print(int.label())
    print(z.sum([Money { cents: 5000000000 }, Money { cents: 7 }]).cents)
    print(z.sum([1, 2, 3]))
    print(z.label_of<Wallet<Wallet<Money>>>())
    let w: Wallet<int> = Wallet.zero()
    print(w.held.len())
    let mw: m.Wallet<Money> = m.Wallet.zero()
    print(mw.held[0].cents)
}
"""

JSON_DERIVE_GEO = r"""// derived in a module of its own, whose names the loader qualifies
import std.json as json

#derive(Json)
pub struct Point {
    x: int,
    y: int,
}

#derive(Json)
pub enum Shape {
    Dot(Point),
    Segment(Point, Point),
    Nothing,
}

pub fun origin_text() -> str {
    return json.encode(Point { x: 0, y: 0 })
}
"""

JSON_DERIVE_SCENE = r"""// D172 (MYLA-385): a derived type of another module in a derived struct,
// read and written through the module's alias
import std.json as json
import .geo as geo
from .geo import Point, Shape

#derive(Json)
struct Scene {
    shapes: [geo.Shape],
    focus: Option<Point>,
}

fun main() {
    let s = Scene { shapes: [Shape.Dot(Point { x: 1, y: 2 }), Shape.Nothing, Shape.Segment(Point { x: 0, y: 0 }, Point { x: 3, y: 4 })], focus: Some(Point { x: 5, y: 6 }) }
    let text = json.encode(s)
    print(text)
    match json.decode<Scene>(text) {
        Ok(back) => print(json.encode(back) == text)
        Err(e) => print(f"{e}")
    }
    print(geo.origin_text())
    match json.decode<Scene>("{\"shapes\": [{\"Segment\": [{\"x\": 0, \"y\": 0}]}]}") {
        Ok(back) => print("ok")
        Err(e) => print(f"{e}")
    }
    let p: Result<geo.Point, json.JsonError> = json.decode("{\"x\": 9, \"y\": 8}")
    match p {
        Ok(v) => print(v.x * 10 + v.y)
        Err(e) => print(f"{e}")
    }
}
"""


TOML_DERIVE_GEO = r"""// derived in a module of its own, whose names the loader qualifies, for
// both formats at once
import std.json as json
import std.toml as toml

#derive(Json, Toml)
pub struct Point {
    x: int,
    y: int,
}

#derive(Json, Toml)
pub enum Shape {
    Dot(Point),
    Segment(Point, Point),
    Nothing,
}

pub fun origin_text() -> str {
    return json.encode(Point { x: 0, y: 0 })
}
"""

TOML_DERIVE_SCENE = r"""// MYLA-407: a derived type of another module in a derived struct, read and
// written through the module's alias; the module derives Json and Toml both
import std.toml as toml
import .geo as geo
from .geo import Point, Shape

#derive(Toml)
struct Scene {
    shapes: [geo.Shape],
    focus: Option<Point>,
}

fun main() {
    let s = Scene { shapes: [Shape.Dot(Point { x: 1, y: 2 }), Shape.Nothing, Shape.Segment(Point { x: 0, y: 0 }, Point { x: 3, y: 4 })], focus: Some(Point { x: 5, y: 6 }) }
    match toml.encode(s) {
        Ok(text) => {
            print(text)
            match toml.decode<Scene>(text) {
                Ok(back) => print(toml.encode(back) == Ok(text))
                Err(e) => print(f"{e}")
            }
        }
        Err(e) => print(f"{e}")
    }
    print(geo.origin_text())
    match toml.decode<Scene>("shapes = [{ Segment = [{ x = 0, y = 0 }] }]") {
        Ok(back) => print("ok")
        Err(e) => print(f"{e}")
    }
    let p: Result<geo.Point, toml.TomlError> = toml.decode("x = 9\ny = 8")
    match p {
        Ok(v) => print(v.x * 10 + v.y)
        Err(e) => print(f"{e}")
    }
}
"""


# C10 (MYLA-543): generic enums and structs nested in themselves, released
# each round: the peak memory of 20,000 rounds and of 200,000 must be alike
# (a round leaked some 700 bytes)
NESTED_GENERICS_SRC = r"""// C10 (MYLA-543): a generic enum or struct nested in itself
// (`Option<Option<Tree>>`, `Option<Option<[str]>>`, which a channel's
// `recv` gives) is released: `owns_heap` saw the inner `Option` by its name
// as the outer one and called it free of the heap
import std.process as process
import std.num as num
import std.task as task

enum Tree { Leaf, Node(Tree, int, Tree) }
struct Wrap<T> { v: T, n: int }

fun mk(n: int) -> Tree {
    if n <= 0 { return Tree.Leaf }
    return Tree.Node(mk(n - 1), n, Tree.Leaf)
}

async fun recv_n(ch: task.Channel<Option<[str]>>, n: int) -> int {
    var s = 0
    for i in 0..n {
        match await ch.recv() {
            Some(v) => { s += 1 }
            None => { s += 100 }
        }
    }
    return s
}

async fun job(j: Option<[str]>) -> Option<[str]> { return j }

#main
async fun main() {
    let rounds = num.parse_int(process.args()[1]).unwrap_or(10) as int
    var total = 0
    for i in 0..rounds {
        let o: Option<Option<Tree>> = Some(Some(mk(6)))
        match o {
            Some(v) => { total += 1 }
            None => {}
        }
        let w = Wrap { v: Wrap { v: [f"a{i}", "b"], n: 1 }, n: 2 }
        total += w.v.v.len()
        let r: Result<Option<[str]>, Option<str>> = Ok(Some([f"r{i}"]))
        match r {
            Ok(Some(xs)) => { total += xs.len() }
            _ => {}
        }
    }
    for i in 0..rounds / 10 {
        let ch: task.Channel<Option<[str]>> = task.channel(2)
        async let r = recv_n(ch, 2)
        let s1 = await ch.send(Some([f"a{i}", "b"]))
        let s2 = await ch.send(Some([f"c{i}", "d"]))
        total += await r
        await ch.close()
        let got = await task.pool(2, [Some([f"p{i}"]), None], job)
        total += got.len()
    }
    print(total)
}
"""


def _peak_kb(argv: list[str], exe: str | None) -> tuple[str, int]:
    """(stdout, peak resident memory in KB) of running `argv`."""
    with tempfile.TemporaryFile() as out:
        pid = os.fork()
        if pid == 0:
            try:
                os.dup2(out.fileno(), 1)
                os.execvp(exe or argv[0], argv)
            finally:
                os._exit(127)
        _, status, usage = os.wait4(pid, 0)
        out.seek(0)
        assert os.waitstatus_to_exitcode(status) == 0
        return out.read().decode(), usage.ru_maxrss


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TestCompilerParity(unittest.TestCase):
    def test_trait_functions_across_modules(self):
        # D172 (MYLA-384): the trait in one module, an impl in another, the
        # calls in a third: on a type imported by name, on a module's type
        # (`m.Money.zero()`), on a built-in type, and through the trait's
        # module's generic functions
        with tempfile.TemporaryDirectory() as tmp:
            write_program(tmp, TRAIT_FUNCTIONS_ZERO, "zero.my")
            write_program(tmp, TRAIT_FUNCTIONS_MONEY, "money.my")
            main = write_program(tmp, TRAIT_FUNCTIONS_MAIN)
            self.assertEqual(run_file_both_now(main), ('0\n0\nmoney\nint\n5000000007\n6\nwallet of wallet of money\n1\n0\n', "", 0))

    def test_json_derive_across_modules(self):
        # D172 (MYLA-385): `#derive(Json)` in a module whose names the loader
        # qualifies (`geo$Point`), its types fields of a derived struct in
        # another, decoded through a module's type (`geo.Point`)
        with tempfile.TemporaryDirectory() as tmp:
            write_program(tmp, JSON_DERIVE_GEO, "geo.my")
            main = write_program(tmp, JSON_DERIVE_SCENE)
            self.assertEqual(run_file_both_now(main), ('{"shapes":[{"Dot":{"x":1,"y":2}},"Nothing",{"Segment":[{"x":0,"y":0},{"x":3,"y":4}]}],"focus":{"x":5,"y":6}}\ntrue\n{"x":0,"y":0}\n$.shapes[0].Segment: expected an array of 2 items, found an array of 1 item\n98\n', "", 0))

    def test_toml_derive_across_modules(self):
        # MYLA-407: `#derive(Json, Toml)` in a module whose names the loader
        # qualifies, its types fields of a derived struct in another, decoded
        # through a module's type (`geo.Point`)
        with tempfile.TemporaryDirectory() as tmp:
            write_program(tmp, TOML_DERIVE_GEO, "geo.my")
            main = write_program(tmp, TOML_DERIVE_SCENE)
            self.assertEqual(run_file_both_now(main), ('shapes = [{ Dot = { x = 1, y = 2 } }, "Nothing", { Segment = [{ x = 0, y = 0 }, { x = 3, y = 4 }] }]\n\n[focus]\nx = 5\ny = 6\n\ntrue\n{"x":0,"y":0}\n$.shapes[0].Segment: expected an array of 2 items, found an array of 1 item\n98\n', "", 0))

    def test_generic_constructors_of_a_module(self):
        # MYLA-315: the shapes std.deque and std.set take (MYLA-330), a module's
        # `pub fun new<T>() -> Deque<T>` called as `deque.new()` where the
        # expected type fixes `T`: an annotation, a field, a parameter, an
        # assignment, a generic method's own type parameter
        with tempfile.TemporaryDirectory() as tmp:
            write_program(tmp, GENERIC_MODULE_DEQUE, "deque.my")
            write_program(tmp, GENERIC_MODULE_SET, "set.my")
            main = write_program(tmp, GENERIC_MODULE_MAIN)
            self.assertEqual(run_file_both_now(main), ("0\n2\n2\n2\n1\n0\n0\nnone\n5000000000\n", "", 0))

    def test_explicit_type_arguments_of_a_module(self):
        # MYLA-373: `deque.new<int>()`, `d.emptied<str>()`: the module's member
        # folds into its qualified name with its type arguments kept
        with tempfile.TemporaryDirectory() as tmp:
            write_program(tmp, GENERIC_MODULE_DEQUE, "deque.my")
            write_program(tmp, GENERIC_MODULE_SET, "set.my")
            main = write_program(tmp, EXPLICIT_MODULE_MAIN)
            self.assertEqual(run_file_both_now(main), ("0\n1\nnone\n5000000000\ntrue\n", "", 0))

    def test_module_types_by_the_module_name(self):
        # MYLA-371 (D170): `deque.Deque<int>` in a field, a list's element, a
        # return type through a re-export (`shapes.dq.Deque<int>`), a
        # function type and a generic type's argument; a struct and a type
        # alias of the module's own (`shapes.Shape`, `shapes.Named`)
        with tempfile.TemporaryDirectory() as tmp:
            write_program(tmp, GENERIC_MODULE_DEQUE, "deque.my")
            write_program(tmp, GENERIC_MODULE_SET, "set.my")
            write_program(tmp, MODULE_TYPES_SHAPES, "shapes.my")
            main = write_program(tmp, MODULE_TYPES_MAIN)
            self.assertEqual(run_file_both_now(main), ("3\n6\n1\n4\ntri 3\n3\n1\n", "", 0))

    def test_a_char_moved_past_the_scalars_is_a_runtime_error(self):
        # MYLA-318: `c + n` and `c - n` are checked as `n as char` is, past
        # U+10FFFF, into the surrogates, below 0 (the sum wraps as an int32),
        # at the operator; the native message has the value too (D183)
        cases = (("'\\u{10FFFF}', 1", "1114112"), ("'\\u{D7FF}', 1", "55296"), ("'a', -98", "-1"),
                 ("'a', 2147483647", "-2147483552"))
        for args, value in cases:
            with self.subTest(args=args), tempfile.TemporaryDirectory() as tmp:
                path = write_program(tmp, "fun moved(c: char, n: int) -> char {\n    return c + n\n}\n"
                                          f"fun main() {{\n    print(moved('a', 1))\n    print(moved({args}))\n}}\n")
                out, err, code = selfhost_run(path)
                self.assertEqual((out, code), ("b\n", 1))
                self.assertEqual(err.splitlines()[:2], [f"runtime error: invalid char: {value} is not a Unicode scalar value",
                                                        f"  --> {path}:2:14"])
                self.assertEqual(build_and_run_full(Program(path), entry_path=path),
                                 ("b\n", f"runtime error: invalid char: {value} is not a Unicode scalar value\n"
                                          f"  --> {path}:2:14\n", 1))

    def test_polymorphic_recursion_is_refused_where_it_is_built(self):
        # MYLA-415 (H5): a generic function calling itself with a larger type
        # asks for instances without end, and `myla build` never ended; it is
        # a type error at the call now, on every target, when the type
        # arguments grow too deep or (a pair of pairs of ...) too large; the
        # interpreter runs it
        myla = selfhost_tool("main")
        cases = (
            ("grow", "fun grow<T>(n: int, x: T) -> int {\n    if n == 0 { return 0 }\n"
                     "    return 1 + grow<[T]>(n - 1, [x])\n}\nfun main() { print(grow(3, 1)) }\n",
             "3:25", "65 types deep (the limit is 64)", "3\n"),
            ("g", "fun f<T>(n: int, x: T) -> int {\n    if n == 0 { return 0 }\n    return g(n - 1, (x, x))\n}\n"
                  "fun g<T>(n: int, x: T) -> int {\n    return f(n, x)\n}\nfun main() { print(f(3, 1)) }\n",
             "3:13", "more than 4096 types in all", "0\n"),
            ("h", "fun h<T>(n: int, x: T) -> int {\n"
                  "    let k = (m: int) => if m == 0 { 0 } else { h(m - 1, Some(x)) }\n    return k(n)\n}\n"
                  "fun main() { print(h(3, 1)) }\n",
             "2:49", "65 types deep (the limit is 64)", "0\n"),
        )
        for callee, src, at, why, out in cases:
            with self.subTest(callee=callee), tempfile.TemporaryDirectory() as tmp:
                path = write_program(tmp, src)
                ran = subprocess.run([myla, "run", path], capture_output=True, text=True, timeout=60)
                self.assertEqual((ran.stdout, ran.returncode), (out, 0), ran.stderr)
                for target in ("x86_64-linux", "aarch64-linux", "wasm32-wasi"):
                    built = subprocess.run([myla, "build", path, "-o", os.path.join(tmp, "out"), "--target", target],
                                           capture_output=True, text=True, timeout=60)
                    self.assertEqual(built.returncode, 1, built.stderr)
                    self.assertIn(f"type error: the instances of '{callee}' nest without end: this call asks for one "
                                  f"whose type arguments are {why}\n  --> {path}:{at}\n", built.stderr)
                    self.assertIn("(polymorphic recursion)", built.stderr)

    def test_a_deep_type_the_program_writes_is_no_recursion(self):
        # MYLA-544: a type 65 or 100 deep that the program writes is no
        # polymorphic recursion: native code builds its instance, which only
        # an instance past the limit asking for a deeper one was refused
        # for; the interpreter runs it
        for depth in (65, 100):
            t, v = "int", "5"
            for _ in range(depth):
                t, v = f"[{t}]", f"[{v}]"
            src = (f"fun mk<T>(x: T) -> T {{\n    return x\n}}\n"
                   f"fun main() {{\n    let x: {t} = {v}\n    print(mk(x) == x)\n}}\n")
            with self.subTest(depth=depth):
                interp, native = _both(src)
                self.assertEqual(native, interp)
                self.assertEqual(native, ("true\n", "", 0))

    def test_an_invalid_spec_of_a_builtin_format_is_a_runtime_error(self):
        # MYLA-544 (C8): a spec known only when it runs, invalid, is the
        # program's runtime error on both runners, and a case's under
        # `myla test`; the interpreter failed in its own std.fmt, which
        # ended `myla test` itself (the position differs: MYLA-565)
        src = ('fun show<T: Format>(x: T, spec: str) -> str {\n    return x.format(spec)\n}\n'
               '#test(5, "q")[panic("invalid format spec \'q\'")]\n#test(5, "x")["5"]\n'
               'fun f(n: int, s: str) -> str {\n    return show(n, s)\n}\n'
               'fun main() {\n    print(f(255, "x"))\n    print(f(1, "q"))\n}\n')
        interp, native = _both(src)
        for out, err, code in (interp, native):
            self.assertEqual((out, code), ("ff\n", 1))
            self.assertTrue(err.startswith("runtime error: invalid format spec 'q'\n"), err)
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, src)
            ran = subprocess.run([selfhost_tool("main"), "test", path], capture_output=True, text=True, timeout=60)
            self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
            self.assertIn("2/2 passed.", ran.stdout)

    def test_a_file_without_main_is_a_clean_error_for_build(self):
        # MYLA-415 (Z3): `CodeGen.sig_of` fell back on the first function, so
        # `myla build` of a library built that function as the entry point,
        # since D179 an unread empty body: a program doing nothing, exit 0
        # (wasm32: an internal error); now the interpreter's message, exit 1
        myla = selfhost_tool("main")
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, "fun f() -> int {\n    return 1\n}\n")
            ran = subprocess.run([myla, "run", path], capture_output=True, text=True, timeout=60)
            self.assertEqual((ran.returncode, ran.stderr),
                             (1, "runtime error: no entry point: define '#main' or a function named 'main'\n"))
            for flags in (["--target", "x86_64-linux"], ["-g"], ["--checked"], ["--target", "aarch64-linux"],
                          ["--target", "wasm32-wasi"]):
                with self.subTest(flags=flags):
                    out = os.path.join(tmp, "out")
                    built = subprocess.run([myla, "build", path, "-o", out] + flags, capture_output=True, text=True,
                                           timeout=60)
                    self.assertEqual((built.returncode, built.stderr),
                                     (1, "error: no entry point: define '#main' or a function named 'main'\n"))
                    self.assertFalse(os.path.exists(out))

    def test_runtime_errors_carry_the_interpreters_values(self):
        # D183 (MYLA-415): a native runtime error is the interpreter's text,
        # its values included; natively an index error said
        # `index out of bounds`, a missing key `map key not found`, a bad
        # char `invalid char`. The first two lines of the interpreter's
        # report, the message and the position, are the binary's stderr
        cases = {
            "list_read": "let xs = [1, 2, 3]\n    let i = 7\n    print(xs[i])",
            "list_negative": "let xs = [1, 2, 3]\n    let i = -1\n    print(xs[i])",
            "list_write": "var xs = [1, 2, 3]\n    let i = 5\n    xs[i] = 1\n    print(xs[0])",
            "from_the_end": "let xs = [1, 2, 3]\n    let i = 5\n    print(xs[^i])",
            "byte_list": "let xs: [uint8] = [1, 2, 3]\n    let i: uint8 = 3\n    print(xs[i])",
            "int64_index": "let xs = [1, 2, 3]\n    let i: int64 = 5000000000\n    print(xs[i])",
            "inner_list": "var xs = [[1], [2]]\n    let i = 1\n    let j = 4\n    xs[i][j] = 1\n    print(xs[0][0])",
            "string_read": "let s = \"abc\"\n    let i = 9\n    print(s[i])",
            "int_key": "let m = [1: 2]\n    let k = 5\n    print(m[k])",
            "str_key": "let m = [\"a\": 2]\n    let k = \"it's\"\n    print(m[k])",
            "escaped_key": "let m = [\"a\": 2]\n    let k = \"tab\\there\"\n    print(m[k])",
            "char_key": "let m = ['a': 2]\n    let k = 'z'\n    print(m[k])",
            "bool_key": "let m = [true: 2]\n    let k = false\n    print(m[k])",
            "tuple_key": "let m = [(1, \"a\"): 2]\n    let k = (3, \"b\")\n    print(m[k])",
            "int8_key": "let m: [int8: int] = [1: 2]\n    let k: int8 = -5\n    print(m[k])",
            # MYLA-441: a struct's, an enum's and a list's key too, natively
            # by a `__krepr_<T>` routine per type
            "struct_key": "let m = [P { x: 0, ys: [], c: 'a', b: true }: 1]\n"
                          "    let k = P { x: 1, ys: [7, 255], c: 'q', b: false }\n    print(m[k])",
            "empty_struct_key": "var m: [Empty: int] = [:]\n    let k = Empty {}\n    print(m[k])",
            "unit_variant_key": "let m = [Color.Red: 1]\n    let k = Color.Green\n    print(m[k])",
            "variant_key": "let m = [Color.Red: 1]\n    let k = Color.Rgb(-1, 2, 3)\n    print(m[k])",
            "named_variant_key": "let m = [Color.Red: 1]\n    let k = Color.Named(\"it's \\\"x\\\"\")\n    print(m[k])",
            "tuple_of_struct_key": "let m = [(P { x: 0, ys: [], c: 'a', b: true }, 1): 1]\n"
                                   "    let k = (P { x: 2, ys: [1], c: 'b', b: true }, 9)\n    print(m[k])",
            "list_key": "let m = [[1, 2]: 1]\n    let k = [3, -4, 5]\n    print(m[k])",
            "empty_list_key": "let m = [[1, 2]: 1]\n    let k: [int] = []\n    print(m[k])",
            "nested_list_key": "let m = [[[\"a\"]]: 1]\n    let k = [[\"b\", \"c\"], [], [\"d\"]]\n    print(m[k])",
            "list_of_bools_key": "let m = [[true]: 1]\n    let k = [false, true]\n    print(m[k])",
            "list_of_chars_key": "let m = [['a']: 1]\n    let k = ['x', 'y']\n    print(m[k])",
            "list_of_tuples_key": "let m = [[(1, 'a')]: 1]\n    let k = [(2, 'b'), (3, 'c')]\n    print(m[k])",
            "option_key": "let m = [Some(1): 1]\n    let k: Option<int> = None\n    print(m[k])",
            "option_payload_key": "let m = [Some(1): 1]\n    let k = Some(5)\n    print(m[k])",
            "generic_struct_key": "let m = [Pair { a: 1, b: \"x\" }: 1]\n    let k = Pair { a: 2, b: \"y\" }\n    print(m[k])",
            "enum_of_structs_key": "let m = [Shape.Dot: 1]\n"
                                   "    let k = Shape.Line(P { x: 1, ys: [2], c: 'c', b: false }, [Color.Red, Color.Green])\n"
                                   "    print(m[k])",
            "recursive_enum_in_a_key": "let m = [Holder { t: Tree.Leaf }: 1]\n"
                                       "    let k = Holder { t: Tree.Node(Tree.Leaf, 4, Tree.Node(Tree.Leaf, 5, Tree.Leaf)) }\n"
                                       "    print(m[k])",
            "unit_payload_key": "let m = [U.B: 1]\n    let k = U.A(())\n    print(m[k])",
            "float_fields_key": "var m: [F: int] = [:]\n    m[F { x: 1.0, y: 2.0f32, r: Ok(1) }] = 1\n"
                                "    print(m[F { x: 0.1, y: 0.1f32, r: Err(\"e\") }])",
            "list_key_of_a_place":"var m = [[1]: [2]]\n    let k = [5, 6]\n    m[k][0] = 3\n    print(m[[1]][0])",
            "uint64_key_in_a_struct":"let m = [W { v: 1 }: 1]\n    let k = W { v: 7 }\n    print(m[k])",
            "key_of_a_place": "var m = [1: [2]]\n    let k = 5\n    m[k][0] = 3\n    print(m[1][0])",
            # MYLA-440: a uint64 key unsigned, by the map's or the key's type
            "uint64_key": "let m: [uint64: int] = [1: 2]\n    let k: uint64 = 18446744073709551615\n    print(m[k])",
            "uint64_high_bit_key": "let m: [uint64: int] = [1: 2]\n    let k: uint64 = 9223372036854775808\n    print(m[k])",
            "uint64_literal_key": "let m: [uint64: int] = [1: 2]\n    print(m[18446744073709551615])",
            "uint64_tuple_key": ("let m: [(uint64, uint32): int] = [(1, 2): 2]\n"
                                 "    let k: (uint64, uint32) = (18446744073709551615, 4294967295)\n    print(m[k])"),
            "uint64_key_of_a_place": ("var m: [uint64: [int]] = [1: [2]]\n    let k: uint64 = 18446744073709551615\n"
                                      "    m[k][0] = 3\n    print(m[1][0])"),
            "uint32_key": "let m: [uint32: int] = [1: 2]\n    let k: uint32 = 4294967295\n    print(m[k])",
            "int64_key": "let m: [int64: int] = [1: 2]\n    let k: int64 = -9223372036854775808\n    print(m[k])",
            "surrogate": "let n = 55296\n    print(n as char)",
            "char_plus": "let c = 'a'\n    print(c + 1114111)",
            "append_range": "var sb = StringBuilder()\n    let a = 2\n    sb.append(\"abc\", a, 9)\n    print(sb.build())",
        }
        # the key types of the cases of a struct, enum or list key
        decls = ("#derive(Eq, Hash)\nstruct P { x: int, ys: [uint8], c: char, b: bool }\n"
                 "#derive(Eq, Hash)\nstruct Empty {}\n"
                 "#derive(Eq, Hash)\nenum Color { Red, Green, Rgb(int, int, int), Named(str) }\n"
                 "#derive(Eq, Hash)\nstruct Pair<A, B> { a: A, b: B }\n"
                 "#derive(Eq, Hash)\nenum Shape { Dot, Line(P, [Color]) }\n"
                 "#derive(Eq, Hash)\nenum Tree { Leaf, Node(Tree, int, Tree) }\n"
                 "#derive(Eq, Hash)\nstruct Holder { t: Tree }\n"
                 "#derive(Eq, Hash)\nstruct W { v: uint64 }\n"
                 "#derive(Eq, Hash)\nenum U { A(()), B }\n"
                 "struct F { x: float, y: float32, r: Result<int, str> }\n"
                 "impl Eq for F {\n    fun eq(self, other: F) -> bool { return self.x == other.x }\n}\n"
                 "impl Hash for F {\n    fun hash(self, h: Hasher) -> Hasher { return h.add(self.x as int64) }\n}\n")
        for name, body in cases.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as tmp:
                path = write_program(tmp, decls + "fun main() {\n    " + body + "\n}\n")
                out, err, code = selfhost_run(path)
                self.assertEqual(code, 1, err)
                lines = err.splitlines()
                self.assertTrue(lines[0].startswith("runtime error: ") and lines[1].startswith("  --> "), err)
                self.assertNotIn(lines[0], ("runtime error: index out of bounds", "runtime error: map key not found",
                                            "runtime error: invalid char"))
                self.assertEqual(build_and_run_full(Program(path), entry_path=path), (out, "\n".join(lines[:2]) + "\n", 1))

    def test_runtime_errors_name_imported_key_types_as_written(self):
        # MYLA-514: a missing key of a type declared in another module named
        # it with the loader's module id (`map key lib$Q { a: 1 } not
        # found`) on both runners; the name is the module's last segment
        # and the type's, as messages write it (MYLA-383), and a string's
        # `$` stays. The interpreter's text is the binary's (D183)
        lib = ("#derive(Eq, Hash)\npub struct Q { a: int, s: str }\n"
               "#derive(Eq, Hash)\npub enum Shape { Dot, Pair(Q, [int]) }\n")
        cases = {
            "struct_key": ("let m = [Q { a: 0, s: \"\" }: 1]\n    print(m[Q { a: 1, s: \"it's\" }])",
                           "map key lib.Q { a: 1, s: \"it's\" } not found"),
            "unit_variant_key": ("let m = [Shape.Pair(Q { a: 0, s: \"\" }, []): 1]\n    print(m[Shape.Dot])",
                                 "map key lib.Shape.Dot not found"),
            "variant_key": ("let m = [Shape.Dot: 1]\n    print(m[Shape.Pair(Q { a: 1, s: \"x$y\" }, [1, 2])])",
                            "map key lib.Shape.Pair(lib.Q { a: 1, s: 'x$y' }, [1, 2]) not found"),
            "nested_key": ("let m = [Holder { q: Q { a: 0, s: \"\" }, t: (Shape.Dot, 1) }: 1]\n"
                           "    print(m[Holder { q: Q { a: 2, s: \"a$b\" }, t: (Shape.Dot, 3) }])",
                           "map key Holder { q: lib.Q { a: 2, s: 'a$b' }, t: (lib.Shape.Dot, 3) } not found"),
            "list_of_imported_key": ("let m = [[Q { a: 0, s: \"\" }]: 1]\n    print(m[[Q { a: 5, s: \"$\" }]])",
                                     "map key [lib.Q { a: 5, s: '$' }] not found"),
            "option_of_imported_key": ("let m = [Some(Shape.Dot): 1]\n    let k: Option<Shape> = Some(Shape.Pair(Q { a: 3, s: \"\" }, []))\n"
                                       "    print(m[k])",
                                       "map key Option.Some(lib.Shape.Pair(lib.Q { a: 3, s: '' }, [])) not found"),
            "string_key_with_a_dollar": ("let m = [\"a\": 1]\n    print(m[\"lib$Q\"])", "map key 'lib$Q' not found"),
        }
        main = ("from .lib import Q, Shape\n"
                "#derive(Eq, Hash)\nstruct Holder { q: Q, t: (Shape, int) }\n"
                "fun main() {\n    {body}\n}\n")
        for name, (body, message) in cases.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as tmp:
                write_program(tmp, lib, "lib.my")
                path = write_program(tmp, main.replace("{body}", body))
                out, err, code = selfhost_run(path)
                self.assertEqual(code, 1, err)
                lines = err.splitlines()
                self.assertEqual(lines[0], "runtime error: " + message)
                self.assertTrue(lines[1].startswith("  --> "), err)
                self.assertEqual(build_and_run_full(Program(path), entry_path=path), (out, "\n".join(lines[:2]) + "\n", 1))

    def test_track_caller_reports_the_callers_position(self):
        # MYLA-435: a `#track_caller` function's `panic`, `assert` and
        # `unreachable` report where it was called, on every runner (a
        # call from one such function to another passes its caller's on);
        # std.option's `expect`s and std.args' spec checks are such. Each
        # case: its program's `main`, the call or index its error points
        # at (at its first bracket, as every runtime error at a call does)
        # and its message
        tracked = ("#track_caller\nfun must(ok: bool, why: str) {\n    if !ok { panic(why) }\n}\n"
                   "#track_caller\nfun never() -> int {\n    unreachable()\n}\n"
                   "#track_caller\nfun outer(x: Option<int>) -> int {\n    must(true, \"\")\n    return x.expect(\"outer\")\n}\n"
                   "fun middle(x: Option<int>) -> int {\n    return x.expect(\"middle\")\n}\n"
                   "#track_caller\nfun via_middle(x: Option<int>) -> int {\n    return middle(x)\n}\n"
                   "#track_caller\nfun first(xs: [int]) -> int {\n    return xs[0]\n}\n"
                   "#track_caller\nfun in_lambda(x: int) -> int {\n    let f = (y: int) => {\n"
                   "        assert(y < 10, \"big\")\n        return y\n    }\n    return f(x)\n}\n"
                   "struct Box<T> {\n    v: Option<T>,\n}\n"
                   "impl<T> Box<T> {\n    #track_caller\n    fun get(self) -> T {\n        return self.v.expect(\"an empty box\")\n    }\n}\n"
                   "#track_caller\nfun pick<T>(xs: [T], i: int) -> T {\n    assert(i < xs.len(), f\"no {i}\")\n    return xs[i]\n}\n")
        lib = "#track_caller\npub fun checked_half(n: int) -> int {\n    assert(n % 2 == 0, \"odd\")\n    return n / 2\n}\n"
        main = "from .lib import checked_half\n" + tracked + "fun main() {\n    print(1)\n    {body}\n}\n"
        cases = {
            "option_expect": ("let o: Option<int> = None\n    print(o.expect(\"none here\"))", "expect(\"none here\")", "none here"),
            "result_expect": ("let r: Result<int, str> = Err(\"e\")\n    print(r.expect(\"an error\"))", "expect(\"an error\")", "an error"),
            "panic": ("must(1 > 2, \"no\")", "must(1 > 2", "no"),
            "unreachable": ("print(never())", "never())", "reached unreachable code"),
            "through_a_tracked_function": ("print(outer(None))", "outer(None)", "outer"),
            "through_an_untracked_one": ("print(via_middle(None))", "expect(\"middle\")", "middle"),
            "a_method_of_a_generic_type": ("let b: Box<str> = Box { v: None }\n    print(b.get())", "get())", "an empty box"),
            "a_generic_function": ("print(pick([\"a\"], 3))", "pick([\"a\"]", "no 3"),
            "a_module_of_its_own": ("print(checked_half(4))\n    print(checked_half(7))", "checked_half(7)", "odd"),
            # an index's error is the function's own, and a lambda's
            # failure its own position
            "an_index": ("let xs: [int] = []\n    print(first(xs))", "xs[0]", "list index 0 out of bounds (len 0)"),
            "a_lambda_inside": ("print(in_lambda(12))", "assert(y < 10", "big"),
            # a whole program
            "in_a_task": ("async fun work(o: Option<int>) -> int {\n    return o.expect(\"in a task\")\n}\n\n"
                          "#main\nasync fun main() {\n    print(await work(Some(1)))\n    print(await work(None))\n}\n",
                          "expect(\"in a task\")", "in a task"),
            # std.args: a spec it can't read, an argument the spec doesn't
            # declare (through `get_or`, which calls `get`; MYLA-553)
            "an_args_spec": ("import std.args as args\n\nfun main() {\n    let s = args.spec(\"t\").option(\"out\", 'o')\n"
                             "    print(s.flag(\"verbose\", 'o').usage())\n}\n",
                             "flag(\"verbose\"", "args: '-o' is declared twice (--out and --verbose)"),
            "an_undeclared_argument": ("import std.args as args\n\nfun main() {\n    let s = args.spec(\"t\").option(\"out\", 'o')\n"
                                       "    let a = args.parse(s, [\"-o\", \"x\"]).expect(\"parsed\")\n"
                                       "    print(a.get_or(\"out\", \"\"))\n    print(a.get_or(\"in\", \"\"))\n}\n",
                                       "get_or(\"in\"", "args: 'in' is not an argument of the spec"),
        }
        for name, (body, needle, message) in cases.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as tmp:
                write_program(tmp, lib, "lib.my")
                source = body if "fun main" in body else main.replace("{body}", body)
                path = write_program(tmp, source)
                lines = source.splitlines()
                bracket = min(needle.index(c) for c in "([" if c in needle)
                at = [(i + 1, line.index(needle) + bracket + 1) for i, line in enumerate(lines) if needle in line]
                self.assertEqual(len(at), 1, needle)
                out, err, code = selfhost_run(path)
                self.assertEqual(code, 1, err)
                self.assertEqual(err.splitlines()[:2], [f"runtime error: {message}", f"  --> {path}:{at[0][0]}:{at[0][1]}"])
                self.assertEqual(build_and_run_full(Program(path), entry_path=path), (out, "\n".join(err.splitlines()[:2]) + "\n", 1))
                if name in ("option_expect", "through_a_tracked_function", "in_a_task"):
                    self.assertEqual(build_and_run_full(Program(path), entry_path=path, checked=True),
                                     (out, "\n".join(err.splitlines()[:2]) + "\n", 1))

    def test_become_runs_a_million_deep(self):
        # MYLA-128, MYLA-131: every `become` of the parity programs jumps, so
        # they run a million calls deep in the default stack
        programs = (
            ("become_keeps_the_stack_flat", "0..1000 {", "0..1000000 {",
             "1784293664\ntrue\ntrue\n3000000\n3000000\n2000000\n459109\n3\n"
             "1000001\n1000000\n2999997\n2999997\n1000\nc\nabc\n42\n789\ndone\n"),
            ("become_passes_aggregates_by_value", "", "",
             "counted 1000000\n3000000\nrs\n2\n1001\n1000\n3000000\n5\ntext!\n"
             "1000004\n11\n10\n13\nk\n"),
        )
        for name, old, new, expected in programs:
            with self.subTest(program=name):
                if program_excuse(name):
                    self.skipTest(program_excuse(name))
                source = PROGRAMS[name].replace("let deep = 20000", "let deep = 1000000")
                if old:
                    source = source.replace(old, new)
                self.assertEqual(build_and_run(source, timeout=60), (expected, 0))

    def test_become_releases_the_values_it_copies(self):
        # MYLA-131: each step's copy, with a longer string, is released; kept,
        # they would take more than the 1 GiB arena
        source = (
            "struct Named { name: str, steps: [int] }\n"
            "fun rename(t: Named, n: int) -> Named {\n"
            "    if n == 0 { return t }\n"
            "    become rename(Named { name: t.name + \"x\", steps: t.steps }, n - 1)\n"
            "}\n"
            "fun main() {\n"
            "    print(rename(Named { name: \"\", steps: [1] }, 50000).name.len())\n"
            "}\n")
        self.assertEqual(build_and_run(source, timeout=60), ("50000\n", 0))

    def test_compound_map_keys_are_released(self):
        # MYLA-313: the keys' words in the slots, retained and released
        out, code = build_and_run(STRESS_MAP_COMPOUND_KEY_SRC, timeout=60)
        self.assertEqual((out, code), ("226667\n", 0))
        self.assertEqual(_self_hosted(STRESS_MAP_COMPOUND_KEY_SRC), out)

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

    def test_iterators_release_what_they_yield(self):
        out, code = build_and_run(STRESS_ITERATORS_SRC, timeout=60)
        self.assertEqual(code, 0, "arena exhausted: a loop over an iterator leaked")
        total = 0
        for k in range(1000000):
            words = [f"item-{i}-{k}-padding!" for i in range(8)]
            for w in words:
                if len(w) % 2 == 0:
                    continue
                total += len(w)
                if total % 5 == 0:
                    break
            total += next((len(w) for w in words if len(w) > 22), 0)
        self.assertEqual(out.strip(), str(total))

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

    def test_runtime_errors_are_reported_alike(self):
        # D183: the report on stderr, the output before it and the status
        for name, src in RUNTIME_ERRORS.items():
            with self.subTest(program=name):
                interp, native = _both(src)
                self.assertEqual(interp[2], 1, interp[1])
                self.assertEqual((native[0], native[2]), (interp[0], interp[2]))
                self.assertEqual(native[1], _without_snippets(interp[1]))

    def test_a_uint64_index_is_reported_unsigned(self):
        # MYLA-546: 2^64-1 was `list index -1 out of bounds`
        for name, text in (("uint64_list_index", "list index 18446744073709551615 out of bounds (len 2)"),
                           ("uint64_index_assigned", "list index 9223372036854775808 out of bounds (len 2)"),
                           ("uint64_string_index", "string index 18446744073709551614 out of bounds (len 2)")):
            with self.subTest(program=name):
                interp, native = _both(RUNTIME_ERRORS[name])
                self.assertTrue(interp[1].startswith(f"runtime error: {text}\n"), interp[1])
                self.assertTrue(native[1].startswith(f"runtime error: {text}\n"), native[1])

    def test_a_runtime_spec_is_reported_at_the_call(self):
        # MYLA-565: at `x.format(spec)`, on every runner, not in std.fmt
        for name, text in (("runtime_spec_of_an_int", "invalid format spec 'q'"),
                           ("runtime_spec_of_a_float", "invalid format spec '9999999': a width above 1000000"),
                           ("runtime_spec_of_text", "invalid format spec '.x'"),
                           ("runtime_spec_with_std_fmt", "invalid format spec '<<<'")):
            with self.subTest(program=name):
                at = ":3:62\n" if name == "runtime_spec_with_std_fmt" else ":1:62\n"
                for runner, (out, err, code) in zip(("interpreted", "native"), _both(RUNTIME_ERRORS[name])):
                    self.assertTrue(err.startswith(f"runtime error: {text}\n"), (runner, err))
                    self.assertTrue(err.splitlines(True)[1].endswith(at), (runner, err))
                    self.assertNotIn("std/fmt.my", err, runner)

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

    def test_try_in_a_literal_releases_it(self):
        out, code = build_and_run(STRESS_TRY_IN_LITERAL_SRC)
        self.assertEqual(code, 0, "arena exhausted — a half-built literal leaked")
        self.assertEqual(out.strip(), "1200000")

    def test_try_after_a_staged_value_releases_it(self):
        out, code = build_and_run(STRESS_TRY_AFTER_STAGED_VALUE_SRC)
        self.assertEqual(code, 0, "arena exhausted — staged container values leaked")
        self.assertEqual(out.strip(), "7500000")

    def test_break_continue_drop_live_heap(self):
        # `break`/`continue` must drop heap owners bound in the loop body scope.
        out, code = build_and_run(STRESS_LOOPCTL_SRC)
        self.assertEqual(code, 0, "arena exhausted — break/continue leaked locals")
        self.assertEqual(out.strip(), "200001\n133333")

    def test_nested_generic_enums_are_released(self):
        # C10 (MYLA-543): `Option<Option<Tree>>`, `Wrap<Wrap<[str]>>`, a
        # channel's `Option<Option<[str]>>` in a child, `task.pool`'s jobs
        with tempfile.TemporaryDirectory() as tmp:
            binary = os.path.join(tmp, "prog")
            native_build(Program(write_program(tmp, NESTED_GENERICS_SRC)), binary)
            small = _peak_kb(*run_argv(binary, "prog", ["20000"]))
            large = _peak_kb(*run_argv(binary, "prog", ["200000"]))
        self.assertEqual((small[0], large[0]), ("88000\n", "880000\n"))
        self.assertLess(large[1] - small[1], 8 * 1024, "the rounds leaked")

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

    def test_assert_with_a_computed_message(self):
        # MYLA-355: a message computed in the failing branch (an f-string, a
        # concatenation) is a temporary of that branch only: the passing path
        # mustn't drop it
        for msg in ('f"bad {t}"', '"bad " + t'):
            with self.subTest(message=msg):
                src = ('#main\nfun main() {\n    let t = "a"\n'
                       f'    assert(t == "a", {msg})\n    print(1)\n'
                       f'    assert(t == "b", {msg})\n    print(2)\n}}\n')
                out, code = build_and_run(src)
                self.assertEqual(out, "1\n")
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


# What a program prints where the retired Python interpreter's recording no
# longer holds (a later decision changed its meaning) or there is none (a
# program added or changed since): its output, pinned here.
PINNED = {
    # MYLA-553, MYLA-580, MYLA-546: new; native code gives the same
    "iter_ldexp_and_padding_in_bulk": '0,63,64,199,299, 630\nb1 d1 c1 \n6\ninf -0 8.98846567431158e307 5e-324\n1000000     |  xy\n1999996 éé|éé\n1000000 -000|0005\n100 0x00|00ff\n1000003 0000|00ff\n4097 0000|0101\n999999 abca|cabc\n139998 ßß|ßab\n',
    # MYLA-545: new; failed to parse before (`expected field name or tuple index after '.'`)
    "tuple_index_chain": "1\n6\n9.5\n16\n13\n",
    # MYLA-496: new; native code gives the same, before the change and after
    "for_over_a_map_walks_its_slots": '3003 4504497\n0,1,2,3,4,5,6,7,8,9, 15\n0=0 2=4 4=16 6=36 8=64 100=0 101=1 102=2 103=3 104=4 105=5 106=6 107=7 108=8 109=9 \n1=1 3=3 4=4 6=6 7=7 2=20 9=90 5=50 \n4 9 -1\n12\nk3 k43 k83 k123 k163 \n415 0 16,0,\np1:1 p2:2 p4:4 p5:5 p0:9 \n2b 0c 1d \n250=true 252=true 253=false 254=true \n1a 2b 11a 12b \n0 415\n',
    # MYLA-429: new; native code gives the same, before the change and after
    "map_shrinks_on_remove": "6 3=6 202=404 401=802 600=1200 799=1598 998=1996 \n1000 0 1998 500\n3=6 202=404 401=802 600=1200 799=1598 998=1996 5000=1 201=7 \n8 0 []\n1=1 \n6 k7:v7,w7 k57:v57,w57 k107:v107,w107 k157:v157,w157 k207:v207,w207 k257:v257,w257 \n3 false true\n1 z false\n2 98 99 1\n5 1,-1=p1 98,-98=p98 195,-195=p195 292,-292=p292 389,-389=p389 \n5 1/t1 98/t98 195/t195 292/t292 389/t389 98 false\n1 s199 200 1 s0\n10 0=0 3=1 6=2 9=3 2=4 5=5 8=6 1=7 4=8 7=9 \n",
    # D175: a const that overflows is an error (`G + G` was 144), and the
    # quotient `MIN / -1` overflows where it is checked; new outputs
    "consts_fold_through_references": "25\n-4\n-5\nfalse\n29\n150\n",
    "int64_min_divided_by_minus_one": "0\n0\n-9223372036854775808\n7\n0\n-3\n1\n0\n-2147483648\n0\n",
    # D175: they wrap through the wrapping methods now; the recording's output
    "unsigned_wrap": "0\n0\n",
    "signed_wrap_and_div": "-128\n-3\n-1\n-3\n",
    # D175 (MYLA-395): new; the output filled in below, checked against both
    "wrapping_methods": '-128\n127\n1\n-128\n254\n255\n1\n0\n255\n-2\n65533\n-2147483648\n2\n1\n1\n9223372036854775807\n-9223372036854775808\n-9223372036854775808\n0\n1\n217083232\n5868319654627689028\n2896040334\n-3\n',
    # MYLA-379 (D173): new; native code gives the same
    "io_error_text": 'cannot read: not found (NotFound)\nnot found (NotFound)\ntrue\npermission denied (PermissionDenied)\nnot found (NotFound)\nalready exists (AlreadyExists)\nnot a directory (NotADirectory)\nis a directory (IsADirectory)\ndirectory not empty (NotEmpty)\ninterrupted (Interrupted)\ncancelled (Cancelled)\nunsupported (Unsupported)\nbroken pipe (BrokenPipe)\ninvalid input (InvalidInput)\nconnection refused (ConnectionRefused)\nconnection reset (ConnectionReset)\nconnection aborted (ConnectionAborted)\nnot connected (NotConnected)\naddress in use (AddrInUse)\naddress not available (AddrNotAvailable)\ntimed out (TimedOut)\nhost unreachable (HostUnreachable)\nnetwork unreachable (NetworkUnreachable)\ninvalid data (InvalidData)\nerror 5 (Other(5))\n<error -3 (Other(-3))>\n',
    # MYLA-379: new; native code gives the same
    "option_result_equality": 'true\nfalse\nfalse\ntrue\nfalse\ntrue\ntrue\ntrue\nfalse\ntrue\ntrue\ntrue\ntrue\nfalse\nfalse\ntrue\nfalse\ntrue\nfalse\ntrue\nfalse\ntrue\nfalse\ntrue\ntrue\nfalse\ntrue\nfalse\ntrue\ntrue\nfalse\ntrue\ntrue\ntrue\ntrue\ntrue\nfalse\ntrue\n2\n',
    # MYLA-379: new; native code gives the same
    "derive_on_generic_types": 'true\nfalse\ntrue\ntrue\nfalse\ntrue\nfalse\ntrue\ntrue\nfalse\ntrue\nfalse\ntrue\ntrue\nfalse\nfalse\ntrue\ntrue\nfalse\n2\nagain\ntrue\nfalse\n2\n3\n7\n0\n3\n1\ntrue\n',
    # MYLA-379: new; native code gives the same
    "json_derive_generic": '{"items":[{"x":1,"y":2},{"x":3,"y":4}],"next":"p2"}\ntrue\n{"items":["a","b"]}\nx\nexpected an integer, found a string\n["Nothing",{"One":1},{"Two":[2,"b"]}]\ntrue\n{"items":[{"items":[{"One":{"x":0,"y":0}}]}]}\ntrue\n',
    # MYLA-385: new; native code gives the same
    "json_derive_structs": '{"x":1,"y":-2}\n{"id":4000000000,"items":[{"name":"a","at":{"x":1,"y":-2},"tags":["t1","t2"],"counts":{"k":3,"j":4}},{"name":"b\\"q","at":{"x":0,"y":0},"tags":[],"label":"lbl","counts":{}}]}\ntrue\nlbl\ntrue\n4\n4000000000\n4 5\ntrue\n15\n{"small":-128,"byte":255,"wide":-9000000000,"huge":1.8446744073709552e+19,"ratio":null,"single":0.1,"flag":true,"letter":"é","raw":[null,1],"maybe":[1,2]}\n{"small":127,"byte":0,"wide":9223372036854775807,"huge":9.223372036854776e+18,"ratio":2.5,"single":1.5,"flag":false,"letter":"x","raw":null}\ntrue\n9223372036854775808\n1.5\nx\n5 6 4\n{}\ntrue\n[[1,2],[3]]\n{"a":1,"b":null}\n"c"\nnull\n2\n-5\ntrue\n',
    # MYLA-385: new; native code gives the same
    "json_derive_enums": '"Empty"\n{"Dot":{"x":1,"y":2}}\n{"Circle":[{"x":0,"y":0},1.5]}\n{"Line":[{"x":0,"y":0},{"x":3,"y":4},"edge"]}\n{"Tagged":null}\n{"Tagged":"t"}\n{"color":"Green","shapes":["Empty",{"Dot":{"x":1,"y":2}},{"Circle":[{"x":0,"y":0},1.5]},{"Line":[{"x":0,"y":0},{"x":3,"y":4},"edge"]},{"Tagged":null},{"Tagged":"t"}],"hidden":"Blue"}\ntrue\n6\n3 4 edge\ngreen\n"Red"\n["Red","Blue"]\n["Blue","Red","Green"]\n{"Circle":[{"x":5,"y":6},2.0]}\n{\n  "Dot": {\n    "x": 0,\n    "y": 0\n  }\n}\n',
    # MYLA-385: new; native code gives the same
    "json_derive_recursive": '{"label":"root","kids":[{"label":"a","kids":[]},{"label":"b","kids":[{"label":"c","kids":[]}]}]}\n4 true\n{"Sum":[{"Num":1},{"Neg":[{"Num":5}]},{"Call":["f",[{"Num":2},{"Num":3}]]}]}\n-2\n{"name":"src","files":[{"name":"a.my"}],"parent":[{"name":"/","files":[]}]}\ntrue\n',
    # MYLA-385: new; native code gives the same
    "json_derive_errors": 'ok 1\nmissing field at $.items[2].label: missing field | $.items[2].label: missing field\nwrong type at $.items[2].label: expected a string, found the number 5 | $.items[2].label: expected a string, found the number 5\nout of range at $.items[0].level: 128 is out of range for int8 | $.items[0].level: 128 is out of range for int8\nout of range at $.items[0].level: -129 is out of range for int8 | $.items[0].level: -129 is out of range for int8\nwrong type at $.items[0].level: expected an integer, found the number 1.5 | $.items[0].level: expected an integer, found the number 1.5\nunknown variant at $.kinds[1]: unknown variant \'Square\' of \'Kind\', expected one of \'Plain\', \'Pair\', \'One\' | $.kinds[1]: unknown variant \'Square\' of \'Kind\', expected one of \'Plain\', \'Pair\', \'One\'\nwrong type at $.kinds[0].Pair: expected an array of 2 items, found an array of 1 item | $.kinds[0].Pair: expected an array of 2 items, found an array of 1 item\nwrong type at $.kinds[0].Pair[1]: expected an integer, found true | $.kinds[0].Pair[1]: expected an integer, found true\nwrong type at $.kinds[0]: variant \'Pair\' of \'Kind\' has a payload: write it as {"Pair": …} | $.kinds[0]: variant \'Pair\' of \'Kind\' has a payload: write it as {"Pair": …}\nwrong type at $.kinds[0]: variant \'Plain\' of \'Kind\' has no payload: write it as "Plain" | $.kinds[0]: variant \'Plain\' of \'Kind\' has no payload: write it as "Plain"\nmissing field at $.kinds[0].One.level: missing field | $.kinds[0].One.level: missing field\nwrong type at $.kinds[0]: expected a variant of \'Kind\' (a string, or an object of one member), found an object | $.kinds[0]: expected a variant of \'Kind\' (a string, or an object of one member), found an object\nout of range at $.extra["a b"]: 300 is out of range for uint8 | $.extra["a b"]: 300 is out of range for uint8\nwrong type at $.note.label: expected a string, found null | $.note.label: expected a string, found null\nwrong type at $.items: expected an array, found an object | $.items: expected an array, found an object\nmissing field at $.items: missing field | $.items: missing field\nwrong type at $: expected an object for \'Doc\', found an empty array | $: expected an object for \'Doc\', found an empty array\nsyntax at : Expecting value | 1:12: Expecting value\n$: expected a string of one character, found a string of 2\n$: 1e+30 is out of range for uint64\n$: -1 is out of range for uint64\n$: 2147483648 is out of range for int32\n18446744073709549568\n$: expected a color, found the number 3\n',
    # MYLA-407: new; native code gives the same
    "toml_derive_structs": 'demo 3 0.5 true é\ntrue\n20240229\n2\ntrue\ntrue\ntrue\nc\n3\ntitle = "demo"\nversion = 3\nratio = 0.5\nenabled = true\nletter = "é"\ncreated = 1979-05-27T07:32:00-08:00\nday = 2024-02-29\n\n[[servers]]\nname = "alpha"\nat = { x = 10, y = 20 }\nports = [80, 443]\n\n[servers.labels]\nenv = "prod"\n"a b" = "c"\n\n[[servers]]\nname = "beta"\nat = { x = 0, y = -1 }\nports = []\nlabels = {}\nbackup = "alpha"\n\n[owner]\nx = 1\ny = 2\n\n[tags]\na = [1, -2]\n\ntrue\nsmall = -128\nbyte = 255\nwide = -9000000000\nhuge = 9.223372036854776e+18\nsingle = 0.1\nlimit = -inf\nraw = [1, "x"]\n\n-128 255 -9000000000 9223372036854775808 0.1 -inf [1, "x"]\n1.8446744073709552e+19\n\ntrue\ntrue\n[a]\nx = 1\ny = 2\n\n["b c"]\nx = 3\ny = 4\n\n',
    # MYLA-407: new; native code gives the same
    "toml_derive_enums": '"Empty"\n{ Dot = { x = 1, y = 2 } }\n{ Circle = [{ x = 0, y = 0 }, 1.5] }\n{ Line = [{ x = 0, y = 0 }, { x = 3, y = 4 }, "edge"] }\ncolor = "Green"\nshapes = ["Empty", { Dot = { x = 1, y = 2 } }, { Circle = [{ x = 0, y = 0 }, 1.5] }, { Line = [{ x = 0, y = 0 }, { x = 3, y = 4 }, "edge"] }]\nhidden = "Blue"\n\ntrue\n[Dot]\nx = 5\ny = 6\n\n$: expected a table for a TOML document, found a string\n1 d\ntrue\n["Empty", { Circle = [{ x = 5, y = 6 }, 2.0] }]\n["Blue", "Red"]\n',
    # MYLA-407: new; native code gives the same
    "toml_derive_generic": 'items = [{ x = 1, y = 2 }, { x = 3, y = 4 }]\nnext = "p2"\n\ntrue\nitems = ["a", "b"]\n\n$.items[0]: expected an integer, found a string\n["Nothing", { One = 1 }, { Two = [2, "b"] }]\ntrue\nlabel = "root"\n\n[[kids]]\nlabel = "a"\nkids = []\n\n[[kids]]\nlabel = "b"\n\n[[kids.kids]]\nlabel = "c"\nkids = []\n\nc true\n{ Sum = [{ Num = 1 }, { Call = ["neg", [{ Num = 5 }]] }, { Num = 2 }] }\n-2 true\n',
    # MYLA-407: new; native code gives the same
    "toml_derive_errors": 'ok 1\nmissing field at $.items[2].label: missing field | $.items[2].label: missing field\nwrong type at $.items[2].label: expected a string, found the integer 5 | $.items[2].label: expected a string, found the integer 5\nout of range at $.items[0].level: 128 is out of range for int8 | $.items[0].level: 128 is out of range for int8\nout of range at $.items[0].level: -129 is out of range for int8 | $.items[0].level: -129 is out of range for int8\nwrong type at $.items[0].level: expected an integer, found the float 1.0 | $.items[0].level: expected an integer, found the float 1.0\nunknown variant at $.kinds[1]: unknown variant \'Square\' of \'Kind\', expected one of \'Plain\', \'Pair\', \'One\' | $.kinds[1]: unknown variant \'Square\' of \'Kind\', expected one of \'Plain\', \'Pair\', \'One\'\nwrong type at $.kinds[0].Pair: expected an array of 2 items, found an array of 1 item | $.kinds[0].Pair: expected an array of 2 items, found an array of 1 item\nwrong type at $.kinds[0].Pair[1]: expected an integer, found true | $.kinds[0].Pair[1]: expected an integer, found true\nwrong type at $.kinds[0]: variant \'Pair\' of \'Kind\' has a payload: write it as { Pair = … } | $.kinds[0]: variant \'Pair\' of \'Kind\' has a payload: write it as { Pair = … }\nwrong type at $.kinds[0]: variant \'Plain\' of \'Kind\' has no payload: write it as "Plain" | $.kinds[0]: variant \'Plain\' of \'Kind\' has no payload: write it as "Plain"\nmissing field at $.kinds[0].One.level: missing field | $.kinds[0].One.level: missing field\nwrong type at $.kinds[0]: expected a variant of \'Kind\' (a string, or a table of one key), found a table | $.kinds[0]: expected a variant of \'Kind\' (a string, or a table of one key), found a table\nout of range at $.extra["a b"]: 300 is out of range for uint8 | $.extra["a b"]: 300 is out of range for uint8\nwrong type at $.note.label: expected a string, found the date 1979-05-27 | $.note.label: expected a string, found the date 1979-05-27\nwrong type at $.items: expected an array, found a table | $.items: expected an array, found a table\nmissing field at $.items: missing field | $.items: missing field\nsyntax at : expected \',\' or \'}\' in an inline table | 5:17: expected \',\' or \'}\' in an inline table\n$.n: 2147483648 is out of range for int32\n$.n: -1 is out of range for uint64\n$.c: expected a string of one character, found a string of 2\nwrong type: $: expected a table for a TOML document, found a string\n$: expected a table for a TOML document, found an array of 2 items\nat = "21.5C"\n\n21.5\n$.at: expected a temperature, found a string\n',
    # MYLA-384: new; native code gives the same
    "trait_functions_zero": '0\n5000000000\n6\n5000000001\n3.75\n3\n400\n0\n0\n0\n',
    # MYLA-384: new; native code gives the same
    "trait_functions_default": 'true\nfalse\nx\n7 1\n7\nnone\ntrue\n7\nnone\nkept\n8\n2\nx\nnone\n2\n',
    # MYLA-384: new; native code gives the same
    "trait_functions_parse": "42\ntrue\n(3, 4)\nempty\nbad '3'\n(10, 20)\ntrue\ntrue\n7\nbad 'x'\n0\ntrue\nbad 'maybe'\n",
    # MYLA-384: new; native code gives the same
    "trait_functions_with_methods": 'square of 9, unit 1\nrectangle of 10, unit 2\n8\n32\n21\na shelf of squares\na shelf of rectangles\n3\n16\nrectangle\n',
    # MYLA-384: new; native code gives the same
    "trait_functions_become": '3\n7\n',
    # MYLA-384: new; native code gives the same
    "trait_functions_async": '6\nabc\n30\npair of pair of str\n0\n',
    # MYLA-318: new; native code gives the same
    "for_over_a_string": '15\n15\nh|é|l|l|o|,| |w|ö|r|l|d| |😀|!|\n5\nD\n-\nh\ni\nb\no\nb\na\nb\nc\nx\ny\nxyzz\n97,65533,65533,98,65533,65533\ntrue\n9\nr\n2\n',
    # MYLA-318: new; native code gives the same
    "for_over_a_string_async": '6\na\nb\n',
    # MYLA-318: new; native code gives the same
    # MYLA-340's lane: the interpreter waited forever, natively it returned
    "wait_with_no_descriptor": 'before\nafter\n2\n',
    # MYLA-380: new
    "iterators": '3\n2\n1\n10\n10\n0\n12\n18\n24\n30\n36\n270\n10\n3\n5 4 4 3\nin the loop 3\n3\nquick,brown,jumps\n3\nx!\nyy!\nzzz!\np\nq\n60\n10\n9\n-1\n55\n107\n208\n',
    # MYLA-387's notifiers: what the program says each line is
    "notifier_ping_pong": "1000\n1000\ntrue\ntrue\ntrue\n",
    "notifier_notify_all": "4950\n21\nfalse\n",
    "notifier_wake_before_wait": "3\nfalse\nfalse\ntrue\ntrue\ntrue\n",
    "notifier_cancelled_waiter": "woken false, cancelled true\n" * 3 + "true\n",
    "notifier_timed_out_wait": "false\ntrue\ntrue\nfalse\nfalse false true\n",
    "notifier_wakes_a_receiver": "389700\n",
    "iterators_async": '26\n8\n8\n',
    "iterator_adapters": '0\n10\n20\ntick\ntick\n0\n1\n7\n8\n<1>\n<2>\nstep 2\nstep 1\n10\n3\n12\nstep 3\nstep 2\nstep 1\nstep 3\n10\n9\n',
    # MYLA-381: new
    "std_iter_pipelines": '36\n45000000000\n5\n<1>\n<4>\n<9>\n4 6\n4321\nb2,a1,c3\nb,c,z\n0:one,1:two,2:three,3:four,4:five\nx3,x2,x1\n5,8,13,21,34\n9\n34\ntrue\nfalse\nfig\nplum\nnone\n3 9\n',
    # MYLA-391: the interpreter printed 'ERR: VUnit'
    "method_on_a_generic_temporary": '36\n100\n',
    # MYLA-414 (H1): new; the interpreter lost the width, the sign and the float size
    "generic_code_per_width": 'int8: 126 -127 63 1 2 true false -128 127 127 S127 true\nint16: 32766 -32767 16383 1 2 true false -32768 32767 32767 S32767 true\nint32: 2147483646 -2147483647 1073741823 1 2 true false -2147483648 2147483647 2147483647 S2147483647 true\nint64: 9223372036854775806 -9223372036854775807 4611686018427387903 1 2 true false -9223372036854775808 9223372036854775807 9223372036854775807 S9223372036854775807 true\nuint8: 254 1 127 1 2 true false 0 255 255 S255 true\nuint16: 65534 1 32767 1 2 true false 0 65535 65535 S65535 true\nuint32: 4294967294 1 2147483647 1 2 true false 0 4294967295 4294967295 S4294967295 true\nuint64: 18446744073709551614 1 9223372036854775807 1 2 true false 0 18446744073709551615 18446744073709551615 S18446744073709551615 true\n18446744073709551614\n18446744073709551614\n255\ntrue\ntrue\n0.010000000707805157\n0.6000000238418579\n0.6000000238418579\n0.33333334\n0.3333333333333333\n<18446744073709551615>\ntrue\n<-128>\n',
    # MYLA-414 (H6, M4): new; the interpreter lost the mutations and printed 'ERR: VUnit'
    "receivers_of_type_parameter_type": '4 11 31\n22 31 31 4\n',
    # MYLA-414 (B6): new; the interpreter sorted signed and lost 'twice' (an internal error)
    "generic_var_self_past_a_written_key": '6\ntrue\n1\n5\n18446744073709551615\n7\n9223372036854775808\n18446744073709551614\n',
    # MYLA-436: new; the interpreter called an element's or a key's written
    # generic `eq` or `hash` without binding its type parameters
    "generic_eq_and_hash_the_interpreter_calls": 'false\nfalse\nfalse\nfalse\nfalse\nfalse\nfalse\nfalse\nfalse\nfalse\nhash 18446744073709551615\nhash 18446744073709551615\ntrue\nhash 18446744073709551615\nhash 18446744073709551615\ntrue\nfalse\nfalse\nfalse\n2\n5\n1\n1\nfalse\ntrue\ntrue\n',
    "map_keys_hashed_once": 'hash\n-- set\nhash\n-- get\nhash\neq\n2\n-- +=\nhash\neq\n-- += of a computed key\nhash\neq\n-- += of a call\nhash\neq\nhash\neq\n-- contains, get_or\nhash\neq\ntrue\nhash\neq\nhash\neq\n7\nhash\n-- += of a string\nhash\neq\nhash\neq\nab\nhash\n-- nested set\nhash\neq\n-- push\nhash\neq\n-- nested get\nhash\neq\n3\n-- nested +=\nhash\neq\n-- var self\nhash\neq\nhash\neq\n4\nhash\n-- field set\nhash\neq\n-- field +=\nhash\neq\nhash\neq\nhash\neq\n7\nhash\neq\ncd\nhash\nhash\n-- map in a map\nhash\neq\nhash\neq\nhash\neq\nhash\neq\nhash\neq\nhash\neq\n6\nhash\n-- tuple key\nhash\neq\nhash\neq\n5\nhash\nhash\nhash\nhash\nhash\nhash\nhash\nhash\nhash\nhash\nhash\nhash\nhash\nhash\nhash\nhash\nhash\nhash\nhash\nhash\n-- keys moved by the argument\nhash\neq\nhash\neq\nhash\neq\nhash\neq\nhash\neq\nhash\neq\nhash\neq\nhash\neq\nhash\neq\nhash\neq\nhash\neq\nhash\neq\nhash\neq\nhash\neq\nhash\neq\nhash\neq\nhash\neq\nhash\neq\nhash\neq\n17\n-- remove\nhash\neq\nhash\nfalse\n',
    # MYLA-546: new; the runners compared colliding keys in other orders, and the
    # interpreter hashed a literal's key before its value
    "written_hash_and_eq_run_alike": 'hash 0\nhash 1\nhash 2\nhash 3\neq 0 3\nhash 4\neq 1 4\nhash 5\neq 2 5\nhash 6\neq 0 6\neq 3 6\n0 1 2 3 4 5 6 \n-- lookups\nhash 6\neq 0 6\neq 3 6\neq 6 6\n6\nhash 9\neq 0 9\neq 3 9\neq 6 9\nfalse\n-- removed, then added\nhash 3\neq 0 3\neq 3 3\nhash 9\neq 0 9\neq 6 9\nhash 12\neq 0 12\neq 6 12\neq 9 12\n0 1 2 4 5 6 9 12 \nhash 12\neq 0 12\neq 6 12\neq 9 12\neq 12 12\n12\nhash 15\neq 0 15\neq 6 15\neq 9 15\neq 12 15\n-1\n-- many removed\nhash 100\neq 1 100\neq 4 100\nhash 101\neq 2 101\neq 5 101\nhash 102\neq 0 102\neq 6 102\neq 9 102\neq 12 102\nhash 103\neq 1 103\neq 4 103\neq 100 103\nhash 104\neq 2 104\neq 5 104\neq 101 104\nhash 105\neq 0 105\neq 6 105\neq 9 105\neq 12 105\neq 102 105\nhash 106\neq 1 106\neq 4 106\neq 100 106\neq 103 106\nhash 107\neq 2 107\neq 5 107\neq 101 107\neq 104 107\nhash 108\neq 0 108\neq 6 108\neq 9 108\neq 12 108\neq 102 108\neq 105 108\nhash 109\neq 1 109\neq 4 109\neq 100 109\neq 103 109\neq 106 109\nhash 110\neq 2 110\neq 5 110\neq 101 110\neq 104 110\neq 107 110\nhash 111\neq 0 111\neq 6 111\neq 9 111\neq 12 111\neq 102 111\neq 105 111\neq 108 111\nhash 112\neq 1 112\neq 4 112\neq 100 112\neq 103 112\neq 106 112\neq 109 112\nhash 113\neq 2 113\neq 5 113\neq 101 113\neq 104 113\neq 107 113\neq 110 113\nhash 114\neq 0 114\neq 6 114\neq 9 114\neq 12 114\neq 102 114\neq 105 114\neq 108 114\neq 111 114\nhash 115\neq 1 115\neq 4 115\neq 100 115\neq 103 115\neq 106 115\neq 109 115\neq 112 115\nhash 116\neq 2 116\neq 5 116\neq 101 116\neq 104 116\neq 107 116\neq 110 116\neq 113 116\nhash 117\neq 0 117\neq 6 117\neq 9 117\neq 12 117\neq 102 117\neq 105 117\neq 108 117\neq 111 117\neq 114 117\nhash 118\neq 1 118\neq 4 118\neq 100 118\neq 103 118\neq 106 118\neq 109 118\neq 112 118\neq 115 118\nhash 119\neq 2 119\neq 5 119\neq 101 119\neq 104 119\neq 107 119\neq 110 119\neq 113 119\neq 116 119\nhash 120\neq 0 120\neq 6 120\neq 9 120\neq 12 120\neq 102 120\neq 105 120\neq 108 120\neq 111 120\neq 114 120\neq 117 120\nhash 121\neq 1 121\neq 4 121\neq 100 121\neq 103 121\neq 106 121\neq 109 121\neq 112 121\neq 115 121\neq 118 121\nhash 122\neq 2 122\neq 5 122\neq 101 122\neq 104 122\neq 107 122\neq 110 122\neq 113 122\neq 116 122\neq 119 122\nhash 123\neq 0 123\neq 6 123\neq 9 123\neq 12 123\neq 102 123\neq 105 123\neq 108 123\neq 111 123\neq 114 123\neq 117 123\neq 120 123\nhash 124\neq 1 124\neq 4 124\neq 100 124\neq 103 124\neq 106 124\neq 109 124\neq 112 124\neq 115 124\neq 118 124\neq 121 124\nhash 125\neq 2 125\neq 5 125\neq 101 125\neq 104 125\neq 107 125\neq 110 125\neq 113 125\neq 116 125\neq 119 125\neq 122 125\nhash 126\neq 0 126\neq 6 126\neq 9 126\neq 12 126\neq 102 126\neq 105 126\neq 108 126\neq 111 126\neq 114 126\neq 117 126\neq 120 126\neq 123 126\nhash 127\neq 1 127\neq 4 127\neq 100 127\neq 103 127\neq 106 127\neq 109 127\neq 112 127\neq 115 127\neq 118 127\neq 121 127\neq 124 127\nhash 128\neq 2 128\neq 5 128\neq 101 128\neq 104 128\neq 107 128\neq 110 128\neq 113 128\neq 116 128\neq 119 128\neq 122 128\neq 125 128\nhash 129\neq 0 129\neq 6 129\neq 9 129\neq 12 129\neq 102 129\neq 105 129\neq 108 129\neq 111 129\neq 114 129\neq 117 129\neq 120 129\neq 123 129\neq 126 129\nhash 130\neq 1 130\neq 4 130\neq 100 130\neq 103 130\neq 106 130\neq 109 130\neq 112 130\neq 115 130\neq 118 130\neq 121 130\neq 124 130\neq 127 130\nhash 131\neq 2 131\neq 5 131\neq 101 131\neq 104 131\neq 107 131\neq 110 131\neq 113 131\neq 116 131\neq 119 131\neq 122 131\neq 125 131\neq 128 131\nhash 132\neq 0 132\neq 6 132\neq 9 132\neq 12 132\neq 102 132\neq 105 132\neq 108 132\neq 111 132\neq 114 132\neq 117 132\neq 120 132\neq 123 132\neq 126 132\neq 129 132\nhash 133\neq 1 133\neq 4 133\neq 100 133\neq 103 133\neq 106 133\neq 109 133\neq 112 133\neq 115 133\neq 118 133\neq 121 133\neq 124 133\neq 127 133\neq 130 133\nhash 134\neq 2 134\neq 5 134\neq 101 134\neq 104 134\neq 107 134\neq 110 134\neq 113 134\neq 116 134\neq 119 134\neq 122 134\neq 125 134\neq 128 134\neq 131 134\nhash 135\neq 0 135\neq 6 135\neq 9 135\neq 12 135\neq 102 135\neq 105 135\neq 108 135\neq 111 135\neq 114 135\neq 117 135\neq 120 135\neq 123 135\neq 126 135\neq 129 135\neq 132 135\nhash 136\neq 1 136\neq 4 136\neq 100 136\neq 103 136\neq 106 136\neq 109 136\neq 112 136\neq 115 136\neq 118 136\neq 121 136\neq 124 136\neq 127 136\neq 130 136\neq 133 136\nhash 137\neq 2 137\neq 5 137\neq 101 137\neq 104 137\neq 107 137\neq 110 137\neq 113 137\neq 116 137\neq 119 137\neq 122 137\neq 125 137\neq 128 137\neq 131 137\neq 134 137\nhash 138\neq 0 138\neq 6 138\neq 9 138\neq 12 138\neq 102 138\neq 105 138\neq 108 138\neq 111 138\neq 114 138\neq 117 138\neq 120 138\neq 123 138\neq 126 138\neq 129 138\neq 132 138\neq 135 138\nhash 139\neq 1 139\neq 4 139\neq 100 139\neq 103 139\neq 106 139\neq 109 139\neq 112 139\neq 115 139\neq 118 139\neq 121 139\neq 124 139\neq 127 139\neq 130 139\neq 133 139\neq 136 139\nhash 100\neq 1 100\neq 4 100\neq 100 100\nhash 101\neq 2 101\neq 5 101\neq 101 101\nhash 102\neq 0 102\neq 6 102\neq 9 102\neq 12 102\neq 102 102\nhash 103\neq 1 103\neq 4 103\neq 103 103\nhash 104\neq 2 104\neq 5 104\neq 104 104\nhash 105\neq 0 105\neq 6 105\neq 9 105\neq 12 105\neq 105 105\nhash 106\neq 1 106\neq 4 106\neq 106 106\nhash 107\neq 2 107\neq 5 107\neq 107 107\nhash 108\neq 0 108\neq 6 108\neq 9 108\neq 12 108\neq 108 108\nhash 109\neq 1 109\neq 4 109\neq 109 109\nhash 110\neq 2 110\neq 5 110\neq 110 110\nhash 111\neq 0 111\neq 6 111\neq 9 111\neq 12 111\neq 111 111\nhash 112\neq 1 112\neq 4 112\neq 112 112\nhash 113\neq 2 113\neq 5 113\neq 113 113\nhash 114\neq 0 114\neq 6 114\neq 9 114\neq 12 114\neq 114 114\nhash 115\neq 1 115\neq 4 115\neq 115 115\nhash 116\neq 2 116\neq 5 116\neq 116 116\nhash 117\neq 0 117\neq 6 117\neq 9 117\neq 12 117\neq 117 117\nhash 118\neq 1 118\neq 4 118\neq 118 118\nhash 119\neq 2 119\neq 5 119\neq 119 119\nhash 120\neq 0 120\neq 6 120\neq 9 120\neq 12 120\neq 120 120\nhash 121\neq 1 121\neq 4 121\neq 121 121\nhash 122\neq 2 122\neq 5 122\neq 122 122\nhash 123\neq 0 123\neq 6 123\neq 9 123\neq 12 123\neq 123 123\nhash 124\neq 1 124\neq 4 124\neq 124 124\nhash 125\neq 2 125\neq 5 125\neq 125 125\nhash 126\neq 0 126\neq 6 126\neq 9 126\neq 12 126\neq 126 126\nhash 127\neq 1 127\neq 4 127\neq 127 127\nhash 128\neq 2 128\neq 5 128\neq 128 128\nhash 129\neq 0 129\neq 6 129\neq 9 129\neq 12 129\neq 129 129\nhash 130\neq 1 130\neq 4 130\neq 130 130\nhash 131\neq 2 131\neq 5 131\neq 131 131\nhash 132\neq 0 132\neq 6 132\neq 9 132\neq 12 132\neq 132 132\nhash 133\neq 1 133\neq 4 133\neq 133 133\nhash 134\neq 2 134\neq 5 134\neq 134 134\nhash 135\neq 0 135\neq 6 135\neq 9 135\neq 12 135\neq 135 135\nhash 30\neq 0 30\neq 6 30\neq 9 30\neq 12 30\neq 138 30\n0 1 2 4 5 6 9 12 136 137 138 139 30 \nhash 30\neq 0 30\neq 6 30\neq 9 30\neq 12 30\neq 138 30\neq 30 30\n30\n-- literals\nkey 1\nval 1\nhash 1\nkey 4\nval 4\nhash 4\neq 1 4\nkey 1\nval 9\nhash 1\neq 1 1\nhash 1\neq 1 1\n2 9\nkey 2\nkey 5\nval 50\nhash 5\nkey 8\nval 80\nhash 8\neq 5 8\nhash 2\nkey 11\nkey 14\nval 140\nhash 14\nhash 11\neq 2 11\n2\n',
    # MYLA-414 (L3): new; the interpreter printed 'ERR: VUnit'
    "actor_function_field": '1205\n',
    # MYLA-414 (L4): new; the interpreter printed 'a' for the numbers
    "char_literal_typed_uint8": '97\n97\n97\n98\n97 98\ntrue\n2\na\n',
    # MYLA-414 (S2): new; the interpreter holds these bytes packed
    "packed_byte_lists": '5\n101\n111\nel\nolleh\ntrue\ntrue\ntrue\ntrue\n532\ntrue\ntrue\ntrue\ntrue\nhello!\nHello!\n33\n5\n72\n4\n100\nabcd\ntrue\n0\ntrue\n',
    # MYLA-367: new; native code gave "undefined reference to 'myla_Box.eq'"
    "operators_of_generic_impls": 'true\ntrue\nfalse\ntrue\nfalse\ntrue\ntrue\n<a> <42> <s>\n<a>\n',
    "string_ordering": 'true true false false\ntrue true false false\nfalse false true true\ntrue true false false\nfalse true false true\nfalse true false true\ntrue true false false\nfalse false true true\nfalse false true true\ntrue true false false\ntrue true false false\ntrue true false false\n,Apple,apple,apples,banana,fig,pear,z,é\n,Apple,apple,apples,banana,fig,pear,z,é\ntrue\na,b,b,c,d\n5\nlime\na,c,m,x\ntrue\na,b\n',
    # MYLA-318: new; native code gives the same
    "char_arithmetic": '15\n-15\n23\ny\na\nb\nc\nz\nc\n132\n😁\ntrue\nuryyb, jbeyq\n98\n25\n3,2,1\n',
    # MYLA-318: new; native code gives the same
    "aoc_library_helpers": '....\n..#.\n....\ntrue\nfalse\ntrue\n1\n2\n0\n42\n-1\n',
    # MYLA-365, MYLA-366: new; native code gives the same
    "try_in_a_call_argument": "err bad\n",
    "method_on_a_type_parameter_field": "5\n",
    # MYLA-313: new; the interpreter gives the same
    "compound_map_keys": "19 cells, (6, 2) at 10, (3, 0) at 7\nfalse\n2 again\nfalse\nk0=true k2=false k3=true k5=true k1=false\n71 k1 1\n12 1 false\n2 c b\n5\n2 2\n2 1\n2\nnone\n3\n10\nRed 2\nblue 3\n2 2 true\n",
    # MYLA-313: new; the interpreter gives the same
    "hash_trait_and_derive": "0xb5b61ff8e7f24a67 0xb5b61ff8e7f24a67 0xd6456ad28572a8f 0x70bc9b8185eefae3\n0x390831630ea9884a 0x59b81abf6522ad07 0x2a4f1d7cb516c72\n0xff3dc34ebf38684d 0x70bc9b8185eefae3 0xfc4894f325fbbe64\n0xb588589b83562bca 0xb33117f322973c8e\ntrue\ntrue\ntrue\n0x4e0a109fae7c734b\n0xed98eb641d3fbd53\ntrue\ntrue\n0x670e93ec0fc81a67 0x969687c72d6781a0\ntrue\n0xd93bdbded0c7bfaa\n0x547db8c134aeb86a\n0x3da68fd7b9e49217\ntrue\ntrue\n0x9da70211eac47ab5\n",
    # MYLA-313: new; the interpreter gives the same
    "tuple_and_list_equality": "true\nfalse\nfalse\ntrue\nfalse\ntrue\nfalse\ntrue\ntrue\nfalse\ntrue\ntrue\nfalse\ntrue\nfalse\ntrue\ntrue\ntrue\ntrue\ntrue\ntrue\nfalse\ntrue\ntrue\nfalse\ntrue\ntrue\nfalse\ntrue\nfalse\ntrue\ntrue\n",
    # MYLA-358: new; the interpreter gives the same
    "literal_left_of_unsigned_division": "0\n10\n0\n100\n0\n4000000005\n1\ntrue\n",
    # MYLA-356: new, so no recording; the interpreter gives the same
    "lambda_parameters_from_known_arguments": "6\n3\n5\ntrue\n3\n",
    # MYLA-315: new; the interpreter gives the same
    "generic_constructors_from_the_expected_type": "0\n1\n0\n4\nq\nno top\n0\nb\nhihi\n0\n3\n5000000000\n"
                                                   "5000000000\n0\n7\n",
    # MYLA-371: new; the interpreter gives the same
    "std_module_types_by_the_module_name": "digit at 2\nempty\n3\n2\ntrue\n0\n",
    # MYLA-373: new; the interpreter gives the same
    "explicit_type_arguments": "0\n1\n0\n5000000000\n8\nseven\n<3>\n0\n0\n0\nhi\n200\ntrue\ntrue\ntrue\nlt\ntrue\ntrue\n",
    # MYLA-315: new; the interpreter gives the same
    "generic_arguments_hinted_by_the_expected_type": "4\n5000000000\ns\n-1\n12\n200\n",
    # D102: the unsuffixed 123.456 is a float64 now (the recording's
    # float32 printed 123.456001); floats print in their shortest form (D155)
    "float_arithmetic": "3.75\n-0.75\n3.375\n3.5\n1.5\n-3.5\n0.30000000000000004\n0.3\n2\n100000\n"
                        "123.456\n0.0009765625\n",
    # the program says float32 since D102; the output is the recording's, its
    # float in the shortest form (D155)
    "float32_overflow_gives_infinity": "inf\n-inf\ninf\nnan\n3.4028235e38\n",
    # (a float prints in its shortest form, with an exponent from 1e16, D155)
    "float64_overflow_gives_infinity": "inf\n-inf\n3.5e38\nnan\n1.7976931348623157e308\n",
    # the builtins outside the closures' scope are methods since MYLA-221;
    # the output is the recording's
    "local_closure_shadows_a_builtin": "42\n7\n3\npushed!\n3\n2\n",
    # MYLA-386: generic actors
    "generic_actor_cell": "150\n1000\n1000\n300\n150\n300\nreset\n3\n2\n3\n7\n3.75\n",
    "generic_actor_queue": "300\n44850\n0\n50\n150\n2\n2\np\n352\n",
    "generic_actor_of_structs": "80\n3160\n1\nfalse\n8\n8\n280\nnew\n5\nthree\n-\n2\npen\n",
    "generic_actor_in_generic_code": "2\n1\nright left\n2\n32\nhello\n100\n2\n9\n1\n3\none\n5\n",
    "generic_actor_bounds_and_children": "10\n51\nxyy\n13\n<1>\n6\n102\n",
    "generic_actors_nested": "c\n2\n3\n6\n",
    # MYLA-392: new; native code couldn't lower it ("a function used as a value")
    "await_in_a_nested_match": "24\n0\n0\n7\n42\n0\n-1\nabc\n6\n2\n0\n",
    # MYLA-390: new
    "for_tuple_patterns": 'a=1\nbb=2\nccc=3\nx\ny\n30\n1:#\n2:##\n3:###\n6\n15\n1\n2\n3\n0 p\n1 q\naa\nccca\ncccbb\ncccccc\n14\n',
    # MYLA-390: new
    "append_char": '16\n97\n233\n8364\n128512\n10\n1114111\n0\nök\nß!\n0\nx\nxy\n2000\n',
    # MYLA-401: new ("cannot infer type parameter(s) R" before); native code gives the same
    "literal_element_types_from_later_elements": 'L1RaL3\n3\n252\n1\nbad\n2\n3\nx\n2\n5000000007\n42\n2\nb\n2\n3\n252\n',
    # MYLA-406: new ("method 'keys' collides with a field of 'Lru'" before); native code gives the same
    "a_field_and_a_method_of_one_name": '3\n3\n1\n10\n3\nq\n2\n5\nrex\npet rex\npet rex\n3\n4\n',
    # MYLA-416 (D186): new ("cannot call a value of type 'int32'" before, the
    # literals and holes read as generic calls); native code gives the same
    "comparisons_in_literals_and_holes": "4\nfalse\ntrue\ntrue\n1\n2\ntrue true\nbelow: false, above: false\n"
                                         "false5 > (9)\n false and true\n2\n5\nseven\n2\n",
    # M24 (MYLA-417): new ("expected '() -> ()', found '() -> ()'" before); native code gives the same
    "unit_as_a_type_argument": '3\n2\n2\n2\n2\n7\n',
    # L2 (MYLA-417): new ("[-1, -128, 5i8]" was a type error, "[1, 2, x]" left 2 an int32); native code gives the same
    "literals_take_the_type_a_later_element_fixes": '-10000000000\n155\n-2.25\n200000000000000\n600\n1400\n60000\n197\n-128\n',
    # MYLA-449: new ("integer literal 4000000000 does not fit in 'int32'" before); native code gives the same
    "literals_wait_for_the_element_that_fixes_a_wider_type": '9000000000\n-6000000000\n-1000000000\nac\n18000000000000000002\n4000000001\n',
    # MYLA-448: new ("cannot infer type parameter(s) E", "T for 'blank'" before); native code gives the same
    "compound_assignments_type_as_their_plain_form": '26\n18\n42\nxy-\n0 1 5000000003 8\n',
    # D182 (MYLA-417): new ("'Option<int32>' isn't Hash" before); native code gives the same
    "option_and_result_as_map_keys": '3\nuno\nnone\nfalse\n13\n2\n3\ntrue\nfalse\n5\n',
    # MYLA-417: new ("cannot infer type parameter(s) E", "T for 'try_mk'" before); native code gives the same
    "inference_through_lambdas_try_and_variants": 'true\ntrue\ntrue\ntrue\ntrue\ntrue\ntrue\nfalse\ntrue\ntrue\n',
    # MYLA-417: new ("cannot reassign 'self'" before); native, aarch64 and wasm32 give the same
    "enum_var_self_assigns_self": '3\n2\n1\n0\nabbccc|\namber\namber green\n10\n',
    # MYLA-538: new; the same before the change and after, on both runners
    "impl_bounds_of_generic_traits_met": 'true\nfalse\ntrue\ntrue\ntrue\nfalse\ntrue\n12\n8\n20\ntrue\ntrue\ntrue\n',
    # MYLA-544 (C8): new; the same on both runners
    "format_method_on_a_builtin_type_parameter": '[5]\n[-005]\n[0x00ff]\n[ffffffffffffffff]\n[1111111111111111111111111111111111111111111111111111111111111111]\n[3.14]\n[   2.500]\n[ λ ]\n[  true]\n[ab***]\n[P!]\nV(+7)\n[V(V( c))]\n1 2  3\na b\n10\n',
    # MYLA-544: new; the same on both runners
    "literals_left_of_typed_operands": '5000000005\n4\nfalse\ntrue\n-3.75\n3\n10\n-1\n1.5\n5000000002\n3\ntrue\n-97\n',
    # MYLA-417 (C1): new; the same on both runners
    "actor_getter_of_a_field_s_name": '6\n11\n',
    # MYLA-415 (B1): native code segfaulted (the captured enum deep-copied as a box)
    "closures_capturing_recursive_enums_across_tasks": '3\n324\n13\n7\n327\n327\n3\n3\n324\n30\n336\n',
    # MYLA-543: native code read freed cells (B2)
    "operands_kept_when_a_later_operand_writes_their_variable": 's10!\ns50!\ns30s11!\ns20!\nfalse false\ntrue\ntrue\ntrue\n3 s40p\ns10T\ns10!,s111,s112,\ns21v 2 s10,\n',
    # MYLA-543: native code read freed cells (B2)
    "bases_kept_when_their_index_writes_their_variable": 's11\ns31\ns32\ns21\ns40\n49\ns11,s12,\n10\ns71\n1\n',
    # MYLA-543: native code read freed cells (B2)
    "holes_and_keys_kept_when_a_later_one_writes_their_variable": 's10!s110\ns30-!\ns10!\nok\n',
    # MYLA-543: native code ran the value first
    "a_method_call_takes_its_receivers_place_first": 'push: 12 2\nmap element push: 12 2\nindex read first: 2 3\nindex 1\nvalue 2\nindex 3\nvalue 4\n1 4\n',
    # MYLA-543 (C11, D194): native code was `main can't be lowered to the IR`
    "recursive_enums_as_map_keys": '6\n30\ntrue\nfalse\n25\n5 false\n1515\n5 10\ntrue\n-1\n4 6 0 42\n56\n6\nbin leaf\n50 1999\n',
    # MYLA-415 (H2): native code segfaulted (a string, list or map argument kept)
    "actors_store_every_heap_type": '1\n7\n3\n2\n2\n2\nvalue 7 2 1 built! rec/2 t4 some 7 5 42 2\n14\npre-value 7 3 1 built! rec/2 t4 some 7 5 42 2\n3 3 built more\n',
    # MYLA-415 (H3): native code segfaulted in __deepb_ and on a child's result
    "recursive_enums_across_tasks": '3\n2\n8\n66\n5\nh 8 3 99 3 2\n6\n12\n1\n2\n79\ntrue\n66\n2\n',
    # MYLA-415 (H4): native code wrote into the copy, or into the freed cell
    "keys_that_change_their_container": '2 3 true\n302 false 399\n4 3 false\n303 99 150\n3 y added\n99 2\n77 303\n5 0 2\n9\n4 3\n5 304\nab a\nbcd\n55 303\n3 301\n50 1\n4 3\n202 false\n0: zero 2 0 3\n1:  5 3 3\n2:  2 0 302\n203 202\n',
    # MYLA-415 (M3): native code answered equal for one cell without comparing
    "list_equal_to_itself": 'false false true false\nfalse true\nfalse\nfalse true\neq called\neq called\ntrue\nfalse\nfalse\ntrue true true true true\ntrue false\n',
    # MYLA-415 (M2, MYLA-367): native code didn't link ('undefined reference to myla_Box.add')
    "arithmetic_operators_of_generic_impls": '3\n5\n42\n4\n1\n3.75\nabcd\nababab\n15000000000\n3\n3 xy\nlinked\n',
    # MYLA-415 (M15): stack overflow on aarch64 and wasm32 (release and deep copy recursed)
    "values_nested_through_closures": '7\n1\n1\n2\n5\n50001 100000 50000 100000\nreleased\n',
}


def _self_hosted(src: str) -> str:
    """What the self-hosted interpreter prints for `src`."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "main.my")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(src)
        out, err, code = selfhost_run(path)
    return out


def _both(src: str) -> tuple[tuple[str, str, int], tuple[str, str, int]]:
    """(stdout, stderr, exit) of the self-hosted interpreter and of native
    code for `src`, from one file, so that positions read alike."""
    with tempfile.TemporaryDirectory() as tmp:
        path = write_program(tmp, src)
        return selfhost_run(path), build_and_run_full(Program(path))


def _without_snippets(stderr: str) -> str:
    """A runtime error's report without the source lines the interpreter
    shows under its position (native code shows none)."""
    return "".join(line for line in stderr.splitlines(True) if not re.match(r"\s*\d*\s*\|", line))


# Programs that end with a runtime error: the report is the interpreter's on
# stderr (D183), its source lines aside, with the same output and status.
RUNTIME_ERRORS = {
    "divide_by_zero": "#main\nfun main() {\n    var z = 0\n    print(1 / z)\n}\n",
    "panic_after_output": '#main\nfun main() {\n    print(1)\n    panic("boom")\n    print(2)\n}\n',
    "assert_with_a_message": '#main\nfun main() {\n    print(7)\n    assert(1 > 2, "nope")\n    print(8)\n}\n',
    "assert_without_one": "#main\nfun main() {\n    assert(1 > 2)\n}\n",
    "unreachable": ("enum E { A, B }\nfun g(e: E) -> int32 {\n    return match e {\n        E.A => 1,\n"
                    "        E.B => unreachable(),\n    }\n}\n#main\nfun main() {\n    print(g(E.B))\n}\n"),
    "list_index": "fun main() {\n    let xs = [1, 2]\n    var i = 5\n    print(xs[i])\n}\n",
    "negative_list_index": "fun main() {\n    let xs = [1, 2]\n    var i = -1\n    print(xs[i])\n}\n",
    "missing_map_key": 'fun main() {\n    let m = ["a": 1]\n    print(m["b"])\n}\n',
    # MYLA-440: a uint64 key unsigned in generic code, by the type it binds
    "missing_uint64_key_in_generic_code": ("struct Table {\n    m: [uint64: str],\n}\n\n"
                                           "fun look<K: Eq + Hash, V>(m: [K: V], k: K) -> V {\n    return m[k]\n}\n\n"
                                           "fun main() {\n    let t = Table { m: [1: \"a\"] }\n    print(look(t.m, 1))\n"
                                           "    print(look(t.m, 18446744073709551615))\n}\n"),
    # MYLA-543: float fields as Python's `repr` writes them (`3.0`, `1e+300`), natively `3`, `1e300`
    "missing_key_with_float_fields": 'struct Fl { a: float, b: float, c: float, d: float32, e: float }\n\nimpl Eq for Fl {\n    fun eq(self, o: Fl) -> bool { return self.a == o.a }\n}\n\nimpl Hash for Fl {\n    fun hash(self, h: Hasher) -> Hasher { return h.add(1) }\n}\n\nfun main() {\n    var m: [Fl: int] = [:]\n    var z = 0.0\n    print(m[Fl { a: 3.0, b: -z, c: 1e300, d: 1e10f32, e: 1.5e-7 }])\n}\n',
    "string_index": 'fun main() {\n    let s = "ab"\n    var i = 9\n    print(s[i])\n}\n',
    # MYLA-546: a uint64 index of 2^63 or more was reported signed, on both runners
    "uint64_list_index": "fun main() {\n    let xs = [1, 2]\n    var i: uint64 = 18446744073709551615\n    print(xs[i])\n}\n",
    "uint64_index_assigned": "fun main() {\n    var xs = [[1], [2]]\n    var i: uint64 = 9223372036854775808\n    xs[i].push(3)\n}\n",
    "uint64_string_index": ('fun main() {\n    let s = "ab"\n    let i: [uint64] = [18446744073709551614]\n'
                            '    print(s[i[0]])\n}\n'),
    "error_after_stderr": 'from std.io import eprint\n\nfun main() {\n    eprint("before\\n")\n    panic("then")\n}\n',
    # MYLA-565: a spec given at run time to `x.format(spec)` on a builtin
    # `T: Format` is the caller's mistake, reported at the call (D183);
    # natively it was inside std.fmt, interpreted too once std.fmt is loaded
    "runtime_spec_of_an_int": ('fun show<T: Format>(x: T, spec: str) -> str { return x.format(spec) }\n'
                               'fun main() {\n    print(show(5, ">4"))\n    print(show(5, "q"))\n}\n'),
    "runtime_spec_of_a_float": ('fun show<T: Format>(x: T, spec: str) -> str { return x.format(spec) }\n'
                                'fun main() {\n    print(show(2.5, ".1"))\n    print(show(2.5, "9999999"))\n}\n'),
    "runtime_spec_of_text": ('fun show<T: Format>(x: T, spec: str) -> str { return x.format(spec) }\n'
                             'fun main() {\n    print(show("ab", "^4"))\n    print(show(true, ".x"))\n}\n'),
    "runtime_spec_with_std_fmt": ('import std.fmt as fmt\n\nfun show<T: Format>(x: T, spec: str) -> str { return x.format(spec) }\n'
                                  'fun main() {\n    print(fmt.pad("a", ">2"))\n    print(show(\'c\', "<<<"))\n}\n'),
}



def _make(name: str, src: str):
    def test(self):
        # native code against the self-hosted interpreter, the reference
        # (D101), stderr too (D183), and against the recording or the
        # pinned output
        interp, native = _both(src)
        self.assertEqual(native[2], 0)
        self.assertEqual(native, interp)
        self.assertEqual(native[0], PINNED[name] if name in PINNED else interpret(src))
    return test


for _name, _src in PROGRAMS.items():
    setattr(TestCompilerParity, f"test_{_name}", _make(_name, _src))


if __name__ == "__main__":
    unittest.main()
