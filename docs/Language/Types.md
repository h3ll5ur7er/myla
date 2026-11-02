# Types

Every expression has a type known before the program runs. Types are resolved by the checker in [[selfhost/checker.my]] (the enum `Type` at the top of the file).

[TOC]

## Scalars

| Type | Values | Notes |
| --- | --- | --- |
| `int8` `int16` `int32` `int64` | two's-complement signed | Arithmetic wraps at the width |
| `uint8` `uint16` `uint32` `uint64` | unsigned | Arithmetic wraps modulo 2^width; printed without sign |
| `int` | alias of `int32` | The default for integer literals |
| `float32` `float64` | IEEE-754 | `float` is an alias of **`float32`**, the default for float literals |
| `char` | a Unicode scalar (0…0x10FFFF, no surrogates) | Compares with `<`; no arithmetic (cast to an integer) |
| `bool` | `true`, `false` | Conditions must be `bool`; there is no truthiness |
| `str` | immutable UTF-8 bytes | `len` counts bytes; `s[i]` is a `uint8` |
| `StringBuilder` | a growable byte buffer | Value semantics, copy-on-write |

There is no implicit conversion: `int32 + int64` is a type error, and so is `float32 + float64`. Literals are flexible (they adopt the type the context expects), and `x as T` converts explicitly ([[Language/Expressions-and-operators]]).

There is no unit type and no `void`: a function without `-> T` returns nothing, and calling it is not an expression with a value.

## Aliases

```myla
typealias Byte = uint8
typealias Grid = [[Byte]]

fun main() {
    let g: Grid = [[1, 2], [3]]
    print(len(g))
}
// output:
// 2
```

An alias is another name for the same type, not a new type (D5). Aliases may be declared in any order; cycles are an error.

## Tuples

`(int, str)` with literals `(1, "a")`. A 1-tuple is written `(int,)` / `(1,)`; there is no 0-tuple (D35). Elements are read with `t.0`, `t.1` (a constant index) or destructured with `let (a, b) = t`. Tuples can't be compared with `==`.

## Structs and enums

User-defined named types: `struct Point { x: int, y: int }` and `enum Shape { Circle(float64), Rect(float64, float64) }`, optionally generic (`struct Box<T> { value: T }`). See [[Language/Structs-enums-and-match]].

## Lists and maps

- `[T]`: a list of `T`.
- `[K: V]`: a hash map. The key type must be an integer type, `char`, `bool` or `str` (D37).

Both are reference-counted, copy-on-write values: a copy is cheap, and writing through one copy never changes another. See [[Language/Collections-and-strings]].

## Function types

`(int, str) -> bool`, `() -> int`. A function value is any top-level non-generic `fun`, a lambda, or a partial application; closures and plain functions share the type ([[Language/Functions-and-closures]]). A function type in source needs a result type: a function that returns nothing can be stored in a binding inferred from a lambda, but its type can't be written.

## Option and Result

Every program has this prelude (`prelude_src` in [[selfhost/checker.my]]):

```
enum Option<T> { Some(T), None }
enum Result<T, E> { Ok(T), Err(E) }
fun get<K, V>(m: [K: V], k: K) -> Option<V>
```

`Some`, `None`, `Ok` and `Err` may be used without the enum name. A bare `None` (or `Ok`/`Err`/`Some` whose type arguments can't be inferred) needs the expected type from an annotation, parameter or return type. The `?` operator propagates `None`/`Err` ([[Language/Expressions-and-operators]]).

## Type parameters and Self

Inside a generic declaration, a type parameter `T` stands for any type; only operations valid for every type are allowed on it, unless a bound such as `T: Add` permits more ([[Language/Generics]]). `Self` exists only in `trait` signatures and means the implementing type ([[Language/Methods-and-traits]]).

## Equality and printing by type

| Type | `==` | `<` | `print`/`format` | map key |
| --- | --- | --- | --- | --- |
| integers, floats | yes | yes | yes | integers only |
| `char` | yes | yes | yes (as the glyph) | yes |
| `bool` | yes | no | `true`/`false` | yes |
| `str` | yes (bytes) | no | yes | yes |
| struct, enum | with `Eq` (`impl Eq` or `#derive(Eq)`) | with `Ord` | no | no |
| tuple, list, map, function, `StringBuilder` | no | no | no | no |
