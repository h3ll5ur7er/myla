"""Burn tests: hand-written programs exercising codegen corners, each asserting
the native binary's output matches the interpreter (and exit codes for traps)."""
import os
import tempfile
import unittest

from tests.burn._targets import program_excuse
from tests.burn._native import (CAN_BUILD_NATIVE, SKIP_REASON, Program, build_and_run, build_and_run_full, interpret,
                                run_file_both_now, selfhost_run, write_program)

PROGRAMS = {
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
        "    match get(moves, Dir.East) {\n"
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
        "    match get(m, k) {\n        Some(v) => { r = v }\n        None => { r = -1 }\n    }\n"
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
        "    return match get(m, k) {\n"
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
    # one free list on every allocation does 240 million probes here (about
    # 14 s); size-class free lists find "nothing free" at once (MYLA-16).
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
        # at the operator; the native message has no values (MYLA-17)
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
                                 ("b\n", f"runtime error: invalid char\n  --> {path}:2:14\n", 1))

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
    "iterators_async": '26\n8\n8\n',
    "iterator_adapters": '0\n10\n20\ntick\ntick\n0\n1\n7\n8\n<1>\n<2>\nstep 2\nstep 1\n10\n3\n12\nstep 3\nstep 2\nstep 1\nstep 3\n10\n9\n',
    # MYLA-381: new
    "std_iter_pipelines": '36\n45000000000\n5\n<1>\n<4>\n<9>\n4 6\n4321\nb2,a1,c3\nb,c,z\n0:one,1:two,2:three,3:four,4:five\nx3,x2,x1\n5,8,13,21,34\n9\n34\ntrue\nfalse\nfig\nplum\nnone\n3 9\n',
    # MYLA-391: the interpreter printed 'ERR: VUnit'
    "method_on_a_generic_temporary": '36\n100\n',
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
}


def _self_hosted(src: str) -> str:
    """What the self-hosted interpreter prints for `src`."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "main.my")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(src)
        out, err, code = selfhost_run(path)
    return out


def _make(name: str, src: str):
    def test(self):
        # native code against the self-hosted interpreter, the reference
        # (D101), and against the recording or the pinned output
        native_out, code = build_and_run(src)
        self.assertEqual(code, 0)
        self.assertEqual(native_out, _self_hosted(src))
        self.assertEqual(native_out, PINNED[name] if name in PINNED else interpret(src))
    return test


for _name, _src in PROGRAMS.items():
    setattr(TestCompilerParity, f"test_{_name}", _make(_name, _src))


if __name__ == "__main__":
    unittest.main()
