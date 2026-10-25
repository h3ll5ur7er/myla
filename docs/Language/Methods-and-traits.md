# Methods and traits

The checker lowers every method to a function named `Type.method` with `self` as its first parameter (`Checker._resolve_impls`, [[src/myla/types.py#L1187-L1316]]).

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
```

- A method's first parameter is `self` (read-only copy) or `var self` (changes the caller's value, D47).
- A `var self` method needs a **mutable place** as its receiver: a `var` variable or one of its fields or elements. Calling it on a `let` binding or a temporary is a type error.
- `impl` works on structs, enums and built-in scalars (`int32`, `bool`, `str`, `StringBuilder`, …). Methods on built-in types must use `self`. Lists, maps and tuples can't have methods.
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
```

- A trait lists method signatures; there are no default bodies. `Self` is the implementing type.
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

## #derive(Eq)

```myla
#derive(Eq)
enum Color { Red, Green, Custom(int, int, int) }

fun main() {
    print(Color.Custom(1, 2, 3) == Color.Custom(1, 2, 3))
}
```

`#derive(Eq)` on a non-generic struct or enum synthesises a structural `impl Eq`. Every field or payload must be an integer, `bool`, `str` or a named type that is `Eq` itself (`char` and float fields are rejected for now: [[MYLA-13]]). A type can't both derive `Eq` and implement it. `Eq` is the only derivable trait so far; `Ord` is the planned next one.

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
```

A type parameter may carry bounds `T: Add + Eq` (built-in or user traits, D53). The bound is checked where the function is called, against the concrete type (primitives count as implementing their built-in operator traits). Inside the body, a bound permits that trait's **operators** on `T`; methods of a user trait can't be called on a `T` yet, because method lookup needs a concrete type.
