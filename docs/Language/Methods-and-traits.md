# Methods and traits

The checker lowers every method to a function named `Type.method` with `self` as its first parameter, and a trait's function without `self` to one named the same way without it (`Checker.resolve_impls` in [[selfhost/checker.my]]; [Functions without self](#functions-without-self), D172).

[TOC]

## Methods

```myla
struct Counter {
    count: int,
}

impl Counter {
    fun get(self) -> int {
        return self.count
    }

    fun add(var self, n: int) {
        self.count = self.count + n
    }
}

impl int32 {
    fun double(self) -> int32 { return self * 2 }
}

fun main() {
    var c = Counter { count: 0 }
    c.add(5)
    print(c.get())
    print(c.get().double())
}
// output:
// 5
// 10
```

- A method's first parameter is `self` (read-only copy) or `var self` (changes the caller's value, D47).
- A `var self` method needs a **mutable place** as its receiver: a `var` variable or one of its fields or elements. Calling it on a `let` binding or a temporary is a type error.
- `impl` works on structs, enums, the built-in scalars (`int32`, `float64`, `bool`, `char`, `str`, `StringBuilder`, …), lists and maps: `impl [int] { … }`, `impl [str: int] { … }`, and generic ones, `impl<T> [T] { … }` ([[MYLA-221]]). A list's or map's methods are keyed by its kind, as a generic struct's are by its name: an `impl [int]`'s `total` is a method of every list that only an `[int32]` may call (`method 'total' is for '[int32]', not '[str]'`), and two impls on lists can't both have a `total`. A `var self` method on a built-in type changes the caller's value as a struct's does (D144): `self.push(x)` on a list, and `self = v`, which only a built-in value's `var self` method may write (a struct's changes its fields; a read-only `self` can't be assigned). An async one isn't supported yet. Tuples can't have methods.

```myla
impl int {
    fun bump(var self, by: int) -> int {
        self = self + by
        return self
    }
}

fun main() {
    var n = 5
    print(n.bump(3))
    var counts = [1, 2]
    counts[0].bump(10)
    print(n)
    print(counts[0])
}
// output:
// 8
// 8
// 11
```
- A generic type takes a generic impl that names every parameter in order: `impl<T> Box<T> { … }`. Methods may have their own type parameters.
- A type may have several `impl` blocks; a method name must be unique per type. There is no orphan rule (D45): any module may add methods to any type.
- A method may share its name with a field ([[MYLA-406]], as in Rust): `c.keys` is the field and `c.keys()` the method, so a getter can be named like what it reads, as an actor's state is (`await counter.count()`). Not with a field that holds a function: `h.on(x)` calls such a field ([[Language/Functions-and-closures]]), so a method `on` beside it is an error at the method ("method 'on' has the name of a field of 'Handler' that holds a function"). Calling a field that holds no function, where no method has its name, says so: `type 'C' has no method 'keys'`, with the help `'keys' is a field of type '[int32]', not a function`. A field of a type parameter's type may hold a function at one instantiation only (`struct Cell<T> { get: T }` with `T` a function type): where `c.get(5)` finds a method `get` and the field `get` holds a function there, the call is an error at it, `'get' is a method of 'Cell<(int32) -> int32>' and its field 'get' holds a function here: bind the field first: let g = c.get` (D178), so that a method another module adds beside such a field changes no call silently.

```myla
struct Lru {
    keys: [int],
}

impl Lru {
    fun keys(self) -> [int] {
        return self.keys[::-1]
    }
}

fun main() {
    let c = Lru { keys: [1, 2, 3] }
    print(c.keys[0])
    print(c.keys()[0])
}
// output:
// 1
// 3
```
- A method's call form is `receiver.method(args)` (D46). A type has no static methods of its own (every method in an `impl` of no trait takes `self`); a trait's functions without `self` are called on the type, `int.zero()` ([Functions without self](#functions-without-self), D172). `Type.method` isn't a value; wrap it in a lambda.

## Traits

```myla
trait Shape {
    fun area(self) -> int
    fun bigger(self, other: Self) -> bool
}

struct Sq { side: int }

impl Shape for Sq {
    fun area(self) -> int { return self.side * self.side }
    fun bigger(self, other: Sq) -> bool { return self.area() > other.area() }
}

fun main() {
    let a = Sq { side: 3 }
    print(a.bigger(Sq { side: 2 }))
}
// output:
// true
```

- A trait lists method signatures, and functions without `self` ([below](#functions-without-self)); there are no default bodies. `Self` is the implementing type, and it means nothing outside a trait declaration (`'Self' is only valid inside a trait declaration`).
- `impl Trait for T` must provide exactly the trait's methods, with the same receivers and with parameter and result types equal to the signature after `Self` is replaced by `T`.
- A type implements a trait at most once.
- **Generic traits** (D55) take type parameters, `trait Comparable<T> { fun compare(self, other: T) -> int }`, implemented as `impl Comparable<int32> for Version`. Still at most one impl per trait and type, whatever the arguments, so calls never need overload resolution.
- The prelude has one, `trait Iterator<T> { fun next(var self) -> Option<T> }`, which `for` loops over ([Iterators](#iterators), D171).
- There are no trait objects and no dynamic dispatch: traits are checked at compile time and methods are called statically.

## Functions without self

```myla
trait Zero {
    fun zero() -> Self
}

impl Zero for int {
    fun zero() -> int { return 0 }
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
    print(total([1, 2, 3]))
    print(total([Money { cents: 150 }, Money { cents: 250 }]).cents)
    let none: [Money] = []
    print(total(none).cents)
}
// output:
// 0
// 6
// 400
// 0
```

A trait may declare, and its impls define, a **function without `self`** (D172, [[MYLA-384]]): `fun zero() -> Self`, `fun parse(text: str) -> Result<Self, ParseError>`. `Self` in its signature is the implementing type, as in a method's. It is called on a type, not on a value:

- on a type that implements the trait: a struct or enum (`Money.zero()`, a module's `m.Money.zero()`), a built-in type (`int.zero()`, `str.zero()`, and a type keyword before `.`, `int64.zero()`), or an alias of one;
- on a type parameter bounded by the trait: `T.zero()` under `T: Zero`, inside a generic function, a generic impl's methods and functions, and their lambdas.

The call is resolved statically, by the one impl the type has (D55): the checker types it by the function's signature with `Self` replaced; natively each generic instance calls its own type's function ([[Architecture/Monomorphization]]); the interpreter binds a generic function's type parameters in its frame when a program calls such a function on one, and calls the function of the type `T` is bound to.

A generic type's function is called on the type's name alone, `Box.zero()`: its type arguments come from the arguments and the expected type, as a generic function's do (`let b: Box<int> = Box.zero()`); `Box<int>.zero()` would read as a comparison and is an error. A list or map type can't stand before `.` (`[int].zero()`): a generic function names it, `make<[int]>()` with `fun make<T: Zero>() -> T { return T.zero() }`.

```myla
trait Parse {
    fun parse(text: str) -> Option<Self>
    fun kind() -> str
}

impl Parse for int {
    fun parse(text: str) -> Option<int> {
        if text.len() == 0 { return None }
        var n = 0
        for c in text {
            if c < '0' || c > '9' { return None }
            n = n * 10 + (c - '0')
        }
        return Some(n)
    }

    fun kind() -> str { return "int" }
}

// a generic impl: its function calls its `T`'s
impl<T: Parse> Parse for [T] {
    fun parse(text: str) -> Option<[T]> {
        var out: [T] = []
        for part in text.split(",") { out.push(T.parse(part)?) }
        return Some(out)
    }

    fun kind() -> str { return "list of " + T.kind() }
}

fun decode<T: Parse>(text: str) -> Option<T> {
    return T.parse(text)
}

fun describe<T: Parse>() -> str {
    return T.kind()
}

fun main() {
    let xs: Option<[int]> = decode("1,2,3")
    print(xs.unwrap_or([]).len())
    print(describe<[[int]]>())
}
// output:
// 3
// list of list of int
```

- Only a trait's functions go without `self`: an `impl` of no trait can't have one (`function 'f' in 'impl P' has no 'self': only a trait's functions go without one`), so a type has no static methods of its own; write a free function. The reason not to allow them: a type's own constructors read as well as free functions of its module (`deque.new()`), and keeping them out keeps one way of writing them.
- An impl gives the function as the trait declares it, without a receiver; a method of the trait keeps its receiver (`has receiver 'self' but the trait declares a function without 'self'`).
- A function without `self` isn't called on a value (`'zero' is a function of 'int32' without 'self': call it on the type, 'int32.zero(…)', not on a value`), and a method isn't called on a type (`'area' is a method of 'Sq' (it takes 'self'): call it on a value`).
- On a type that doesn't implement the trait, `type 'str' has no function 'zero'`, with the trait that declares one named; on a type parameter without the bound, `type parameter 'T' has no function 'zero': it has no bounds`.
- What a name before `.` means: a local variable first (a method call on its value), then a type parameter of the function, a type, and a module bound by `import … as` (the loader folds `m.f` and `m.T.f` into the module's names first; a type and a module of one name in one file is already an error, `import of 'm' collides with an existing name`).
- An enum's function can't have a variant's name (`Color.Red()` is the variant).
- `T.zero` without a call isn't a value; wrap the call in a lambda, `() => T.zero()`. A `become` can't call one yet.

## Operator overloading

A fixed set of built-in traits backs the operators on structs and enums (D52):

| Trait | Method | Operators |
| --- | --- | --- |
| `Add` `Sub` `Mul` `Div` `Rem` | `add` `sub` `mul` `div` `rem` `(self, other: Self) -> Self` | `+ - * / %` |
| `Eq` | `eq(self, other: Self) -> bool` | `==`, `!=` |
| `Ord` | `cmp(self, other: Self) -> int` (negative, zero, positive) | `< <= > >=` |

`a + b` on a struct becomes `a.add(b)`; `a < b` becomes `a.cmp(b) < 0`. Both operands must have the same type. Primitive types keep their built-in operators (a user `impl Add for int32` doesn't change `+`), and the bitwise operators can't be overloaded.

## #derive(Eq), #derive(Hash), #derive(Json) and #derive(Toml)

```myla
#derive(Eq)
enum Color { Red, Green, Custom(int, int, int) }

fun main() {
    print(Color.Custom(1, 2, 3) == Color.Custom(1, 2, 3))
}
// output:
// true
```

`#derive(Eq)` on a struct or enum synthesises a structural `impl Eq`: the fields in turn, or the variant and then its payload. Every field or payload must be `Eq` itself: an integer, a float, `char`, `bool`, `str`, a tuple or list of `Eq` elements, an `Option` or `Result` of them, or a named type that is `Eq`. A type can't both derive `Eq` and implement it.

On a generic type ([[MYLA-379]]) the impl is bounded by the trait on every type parameter, `impl<A: Eq, B: Eq> Eq for Pair<A, B>`, so `Pair<int, str>` has `==` and `Pair<int, Pos>` hasn't while `Pos` isn't `Eq` (`operator '==' is not defined for 'Pair<int32, Pos>': 'Pos' isn't Eq (…)`). A field of a type parameter is `Eq` by that bound; any other field is checked as a concrete type's is (`[str: T]` is a map, never `Eq`). `#derive(Hash)` bounds it by `T: Hash`, `#derive(Json)` by `T: ToJson` and `T: FromJson`. The prelude's `Option` and `Result` derive `Eq` and `Hash` this way (D182).

```myla
#derive(Eq, Hash)
struct Pair<A, B> {
    a: A,
    b: B,
}

#derive(Eq)
enum Tree<T> {
    Leaf,
    Node(T, [Tree<T>]),
}

fun main() {
    let p = Pair { a: 1, b: "x" }
    print(p == Pair { a: 1, b: "x" })
    var seen: [Pair<int, str>: bool] = [:]
    seen[p] = true
    print(seen.contains(Pair { a: 1, b: "y" }))
    let t: Tree<int> = Tree.Node(1, [Tree.Leaf])
    print(t != Tree.Node(1, []))
    print(Some(p) == None)
}
// output:
// true
// false
// true
// false
```

A float field compares with the floats' own `==`, in both runners: a value holding NaN is unequal to itself, and one holding `0.0` equals one holding `-0.0` ([[MYLA-316]]).

```myla
#derive(Eq)
struct Reading {
    unit: char,
    value: float,
}

fun main() {
    let a = Reading { unit: 'C', value: 0.0 }
    print(a == Reading { unit: 'C', value: -0.0 })
    print(a == Reading { unit: 'F', value: 0.0 })
    let zero = 0.0
    let b = Reading { unit: 'C', value: zero / zero }
    print(b == b)
}
// output:
// true
// false
// false
```

`#derive(Hash)` writes an `impl Hash` (D163, [[MYLA-313]]) that adds the fields in order, `h.add(self.x).add(self.y)`, and for an enum the variant's index (as a `uint64`) and then its payload. It needs an `Eq` of the type, derived (`#derive(Eq, Hash)`) or written, and refuses a field that isn't `Hash`, a float among them. A type can't both derive `Hash` and implement it.

`#derive(Json)` writes an `impl ToJson` and an `impl FromJson` against `std.json` (D172, [[MYLA-385]]), which the program imports: a struct as an object of its fields (an `Option` field left out when `None`), an enum externally tagged (`"Red"`, `{"Dot": x}`, `{"Line": [a, b]}`), so that `json.encode(v)` and `json.decode<T>(text)` work on it; every field must have a JSON form itself, and recursive types work. The rules and the built-in types' forms are on [[Language/Standard-library/Json#typed-values]].

`#derive(Toml)` writes an `impl ToToml` and an `impl FromToml` against `std.toml` ([[MYLA-407]]) the same way: a struct as a table of its fields, an enum externally tagged (`"Red"`, `{ Dot = x }`, `{ Line = [a, b] }`), so that `toml.encode(v)` (a `Result`: a document must be a table) and `toml.decode<T>(text)` work on it. TOML has no null, so an `Option` may be a struct's field, left out when `None`, and nothing else (not in a list, a map or a payload). The rules are on [[Language/Standard-library/Toml#typed-values]]. A type may derive both, `#derive(Json, Toml)`.

The derives are generated as Myla source and checked with the program (`derived_hash_src`, `derived_struct_src` and `derived_enum_src` for both formats, a `Serial` naming the format's items, in [[selfhost/checker.my]], and a generic type's `derived_eq_src`; a concrete type's `Eq` is the runners' own structural comparison); `#derive(Json)`'s and `#derive(Toml)`'s source names the module's items by the loader's qualified names (`std$json$Json`, `std$toml$Toml`), which only the checker's own parser accepts (`parse_qualified`). `Eq`, `Hash`, `Json` and `Toml` are the derivable traits so far; `Ord` is the planned next one.

## Hash

```myla
import std.hash as hash

#derive(Eq, Hash)
struct Pos {
    x: int,
    y: int,
}

// a name compared and hashed without regard to case
struct Tag {
    text: str,
}

impl Eq for Tag {
    fun eq(self, other: Tag) -> bool {
        return self.text.to_lower() == other.text.to_lower()
    }
}

impl Hash for Tag {
    fun hash(self, h: Hasher) -> Hasher {
        return h.add(self.text.to_lower())
    }
}

fun main() {
    let p = Pos { x: 1, y: 2 }
    print(p.hash(hash.new()) == hash.new().add(1).add(2))
    var seen: [Tag: int] = [:]
    seen[Tag { text: "Red" }] = 1
    seen[Tag { text: "RED" }] = 2
    print(seen.len())
}
// output:
// true
// 1
```

`trait Hash { fun hash(self, h: Hasher) -> Hasher }` is in the prelude with the `Hasher` it passes through, by value since Myla has no `var` parameters (D163). The hasher's methods and its algorithm are [[Language/Standard-library/Hash]]'s: `h.add(x)` adds any `Hash` value (it is `x.hash(h)`), `add_u64`, `add_str` and the others add one of a built-in type, `finish()` gives the hash. A map's key type is any type that is `Eq` and `Hash` ([[Language/Collections-and-strings]]).

- The integers, `char`, `bool` and `str` are `Hash`, and a tuple and a list are when their elements are (a list adds its length, then its elements). Floats aren't: NaN is unequal to itself. A hand-written impl may add `math.to_bits(x)` of a float field, as long as its `Eq` agrees.
- That `a == b` gives `a.hash(h) == b.hash(h)` is the promise of a written impl: a map finds a key only among those of the same hash. A derived `Hash` with a derived `Eq` keeps it.
- A tuple's `hash` is the language's, as no impl can name a tuple of every length: `(1, "a").hash(h)` adds `1`, then `"a"`.
- A generic function that hashes takes `T: Hash` (`h.add(x)` and `x.hash(h)` on a `T: Hash`), and one with a map keyed by a type parameter `K` needs `K: Eq + Hash` written (D167, [[Language/Collections-and-strings]]).

## Bounds

```myla
fun sum<T: Add>(xs: [T], zero: T) -> T {
    var acc = zero
    for x in xs {
        acc = acc + x
    }
    return acc
}

fun main() {
    print(sum([1, 2, 3], 0))
}
// output:
// 6
```

A type parameter may carry bounds `T: Add + Eq` (built-in or user traits, D53; `Hash` is the prelude's). The bound is checked where the function is called, against the concrete type (primitives count as implementing their built-in operator traits, and the printable ones `Format`, D162). Inside the body, a bound permits that trait's **operators** on `T` (`Add`, `Eq`, `Ord`, …: their methods are their operators) and the **methods** of a user trait or of `Format`, with `Self` the type parameter; a `T: Format` goes in a format hole as its type does ([[MYLA-291]]). The interpreter calls the method of the value's type, native code the method of the type the copy is made for ([[Architecture/Monomorphization]]).

```myla
trait Shape {
    fun area(self) -> int
}

struct Sq {
    side: int,
}

impl Shape for Sq {
    fun area(self) -> int {
        return self.side * self.side
    }
}

impl Format for Sq {
    fun format(self, spec: str) -> str {
        return f"Sq({self.side})"
    }
}

fun describe<T: Shape + Format>(x: T) -> str {
    return f"{x} has area {x.area()}"
}

fun main() {
    print(describe(Sq { side: 3 }))
}
// output:
// Sq(3) has area 9
```

A method a bound doesn't give is an error at the call: `type parameter 'T' has no method 'area': it has no bounds`.

A bound may name a **generic trait with its arguments**, `I: Iterator<T>` or `I: Iterator<int>`, in a function's, a method's and an impl's type parameters (D171). Inside the body the trait's methods take its arguments: `it.next()` on an `I: Iterator<T>` is an `Option<T>`. At the call the argument's type must implement the trait with those arguments: its one impl (D55) gives them, so a `Words` that is an `Iterator<str>` doesn't satisfy `I: Iterator<int>` (`type 'Words' does not satisfy the bound 'I: Iterator<int32>' required by 'total': it implements 'Iterator<str>'`). The same impl **fixes a type parameter only the bound names**: in `fun count<I: Iterator<T>, T>(it: I) -> int`, the argument's type gives `I`, and `I`'s impl of `Iterator` gives `T`, for the arguments after it too, so a lambda there takes `T` without an annotation ([[Language/Generics]]). A generic trait without its arguments is an error (`trait 'Iterator' expects 1 type argument(s) in the bound 'I: Iterator', got 0 (write 'I: Iterator<T>')`), as are arguments on a trait that has none.

A bound names **a module's trait** by the module's name, as a type names its type ([[Language/Modules]], D170, [[MYLA-398]]): with `import std.json as json`, `fun show<T: json.ToJson>(v: T)`, and with a module `shapes` that exports `trait Pair<T>`, `P: shapes.Pair<T>`; `from std.json import ToJson` and `T: ToJson` still work. The name must be a trait the module exports: `'json.Json' is an enum of module 'std.json', not a trait`, `module 'std.json' does not export a trait 'ToText'`, `unknown module 'geo' in the trait 'geo.Show'`, each reported at the type parameter.

```myla
import std.json as json

#derive(Json)
struct Pt {
    x: int,
}

fun show<T: json.ToJson>(v: T) -> str {
    return json.encode(v)
}

fun main() {
    print(show(Pt { x: 4 }))
}
// output:
// {"x":4}
```

## Iterators

An iterator is a value with a `next`: it implements the prelude's `trait Iterator<T> { fun next(var self) -> Option<T> }` (D171). The adapters and consumers over one, chained with `|>`, are [[Language/Standard-library/Iter]]'s. `for x in e` over a type that implements `Iterator<T>` is

```myla fragment
var it = e
while let Some(x) = it.next() {
    // the loop's body
}
```

so the loop works on a **copy** of `e`, and `break`, `continue`, `return` and `?` in its body do what they do in that `while`. An iterator is a value like any other: `let b = a` copies its position, and `a.next()` doesn't move `b` (Swift's behaviour, not Rust's moves). Lists, maps, strings and ranges keep their own loops ([[Language/Statements#loops]]).

```myla
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

// An adapter: an iterator over another one, its impl bounded by the trait
// with its arguments
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

fun total<I: Iterator<int>>(it: I) -> int {
    var s = 0
    for x in it { s += x }
    return s
}

fun main() {
    for x in map(Countdown { n: 3 }, (x) => x * 10) {
        if x == 20 { continue }
        print(x)
    }
    var a = Countdown { n: 5 }
    let first = a.next().unwrap_or(0)
    let b = a
    print(f"{first} {total(a)} {total(b)}")
}
// output:
// 30
// 10
// 5 10 10
```

- A type is an iterator only through an impl of `Iterator` (or, for a type parameter, its bound): a `next` method of its own isn't enough (`` `for ... in` requires a list, a map, a string, a range or an Iterator, found 'Countdown' (it needs 'impl Iterator<T> for Countdown') ``).
- An adapter's type is a nest of generics (`Map<Countdown, int, int>`); a local needs no annotation, but a function that returns one spells it. There are no trait objects, so a list can't hold iterators of different types.
- The checker checks the loop as the `while` above, with a hidden variable no program can name, and gives the interpreters and the code generator that loop in place of the `for` (`check_for_iterator`, `fill_in` in [[selfhost/checker.my]]): both run it as they run one written so, natively each `next` the concrete type's ([[Architecture/Monomorphization]]).
- Interpreted, each `next` is a method call with its `var self` copied back, nested once per adapter: a lazy `Range → Map → Filter` sum ran some 19 times slower than a hand-written loop and 4 times slower than `xs.map(…).filter(…)`, where natively it ran 2.2 times slower than the loop, 4.3 times faster than the eager methods, in constant memory ([[MYLA-380]]).

