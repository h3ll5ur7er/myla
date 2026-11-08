# Methods and traits

The checker lowers every method to a function named `Type.method` with `self` as its first parameter (`Checker.resolve_impls` in [[selfhost/checker.my]]).

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
- A type may have several `impl` blocks; a method name must be unique per type and differ from every field name. There is no orphan rule (D45): any module may add methods to any type.
- The only call form is `receiver.method(args)` (D46). There are no static or associated functions (every method takes `self`), and `Type.method` isn't a value; wrap it in a lambda.

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

- A trait lists method signatures; there are no default bodies. `Self` is the implementing type, and it means nothing outside a trait declaration (`'Self' is only valid inside a trait declaration`).
- `impl Trait for T` must provide exactly the trait's methods, with the same receivers and with parameter and result types equal to the signature after `Self` is replaced by `T`.
- A type implements a trait at most once.
- **Generic traits** (D55) take type parameters, `trait Comparable<T> { fun compare(self, other: T) -> int }`, implemented as `impl Comparable<int32> for Version`. Still at most one impl per trait and type, whatever the arguments, so calls never need overload resolution.
- There are no trait objects and no dynamic dispatch: traits are checked at compile time and methods are called statically.

## Operator overloading

A fixed set of built-in traits backs the operators on structs and enums (D52):

| Trait | Method | Operators |
| --- | --- | --- |
| `Add` `Sub` `Mul` `Div` `Rem` | `add` `sub` `mul` `div` `rem` `(self, other: Self) -> Self` | `+ - * / %` |
| `Eq` | `eq(self, other: Self) -> bool` | `==`, `!=` |
| `Ord` | `cmp(self, other: Self) -> int` (negative, zero, positive) | `< <= > >=` |

`a + b` on a struct becomes `a.add(b)`; `a < b` becomes `a.cmp(b) < 0`. Both operands must have the same type. Primitive types keep their built-in operators (a user `impl Add for int32` doesn't change `+`), and the bitwise operators can't be overloaded.

## #derive(Eq) and #derive(Hash)

```myla
#derive(Eq)
enum Color { Red, Green, Custom(int, int, int) }

fun main() {
    print(Color.Custom(1, 2, 3) == Color.Custom(1, 2, 3))
}
// output:
// true
```

`#derive(Eq)` on a non-generic struct or enum synthesises a structural `impl Eq`: the fields in turn, or the variant and then its payload. Every field or payload must be `Eq` itself: an integer, a float, `char`, `bool`, `str`, a tuple or list of `Eq` elements, or a named type that is `Eq`. A type can't both derive `Eq` and implement it.

`#derive(Hash)` writes an `impl Hash` (D163, [[MYLA-313]]) that adds the fields in order, `h.add(self.x).add(self.y)`, and for an enum the variant's index (as a `uint64`) and then its payload. It needs an `Eq` of the type, derived (`#derive(Eq, Hash)`) or written, and refuses a field that isn't `Hash`, a float among them. A type can't both derive `Hash` and implement it. `Eq` and `Hash` are the derivable traits so far; `Ord` is the planned next one.

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
