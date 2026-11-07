# Types

Every expression has a type known before the program runs. Types are resolved by the checker in [[selfhost/checker.my]] (the enum `Type` at the top of the file).

[TOC]

## Scalars

| Type | Values | Notes |
| --- | --- | --- |
| `int8` `int16` `int32` `int64` | two's-complement signed | Arithmetic wraps at the width |
| `uint8` `uint16` `uint32` `uint64` | unsigned | Arithmetic wraps modulo 2^width; printed without sign |
| `int` | alias of `int32` | The default for integer literals |
| `float32` `float64` | IEEE-754 | `float` is an alias of `float64`, the default for float literals (D102) |
| `char` | a Unicode scalar (0…0x10FFFF, no surrogates) | Compares with `<`; `c - d` is an `int32`, `c + n` and `c - n` with an `int32` are a `char` ([[Language/Expressions-and-operators#typing-rules]]) |
| `bool` | `true`, `false` | Conditions must be `bool`; there is no truthiness |
| `str` | immutable UTF-8 bytes | `len` counts bytes; `s[i]` is a `uint8`; `for c in s` visits the characters; `<` orders byte-wise |
| `StringBuilder` | a growable byte buffer | Value semantics, copy-on-write |

There is no implicit conversion: `int32 + int64` is a type error, and so is `float32 + float64`. Literals are flexible (they adopt the type the context expects), and `x as T` converts explicitly ([[Language/Expressions-and-operators]]).

A function without `-> T` returns the unit value `()` (D140, see the unit type below): there is no separate `void`.

## Aliases

```myla
typealias Byte = uint8
typealias Grid = [[Byte]]

fun main() {
    let g: Grid = [[1, 2], [3]]
    print(g.len())
}
// output:
// 2
```

An alias is another name for the same type, not a new type (D5). Aliases may be declared in any order; cycles are an error.

## Tuples

`(int, str)` with literals `(1, "a")`. A 1-tuple is written `(int,)` / `(1,)` (D35). Elements are read with `t.0`, `t.1` (a constant index) or destructured with `let (a, b) = t`. Tuples can't be compared with `==`.

## The unit type

`()` is a type with one value, also written `()` (D138, [[MYLA-278]]): what a function gives back when it succeeds or fails with nothing to give.

```myla
from std.fs import write_to_file, IoError

fun save(path: str, text: str) -> Result<(), IoError> {
    write_to_file(path, text)?
    return Ok(())
}

fun main() {
    match save("notes.txt", "hi") {
        Ok(()) => print("saved")
        Err(e) => print("not saved")
    }
}
// output:
// saved
```

- It works wherever a type does: `Option<()>`, `[()]`, a map `[str: ()]` used as a set, a field, a payload (`Done(())`), a type argument.
- `()` is also its pattern (`Ok(())`, `let ((), n) = pair`), and the only one it needs: a `match` on it is exhaustive with one arm.
- `==` is always `true` and `!=` always `false` (both sides still run), and a struct or enum with a `()` member can `#derive(Eq)`. There is no ordering, and `print` and f-strings don't take it.
- It takes no memory: a list of units holds only its length, and a `Result<(), E>` is as large as its `Err`.
- It is the 0-tuple: `type_name` writes it `()`, as the empty element list of a tuple.
- A function without a result type returns `()` (D140): `fun f()` and `fun f() -> ()` are the same, `return` and `return ()` too, and a call of it is the value `()` (`let u = log("hi")`, `Ok(log("hi"))`). Its type is written `(str) -> ()`.

## Structs and enums

User-defined named types: `struct Point { x: int, y: int }` and `enum Shape { Circle(float64), Rect(float64, float64) }`, optionally generic (`struct Box<T> { value: T }`). See [[Language/Structs-enums-and-match]].

## Lists and maps

- `[T]`: a list of `T`.
- `[K: V]`: a hash map. The key type is any type that is `Eq` and `Hash`: an integer type, `char`, `bool`, `str`, a tuple or list of such, or a struct or enum deriving or implementing both (D163; D37 had the primitives only).

Both are reference-counted, copy-on-write values: a copy is cheap, and writing through one copy never changes another. See [[Language/Collections-and-strings]].

## Function types

`(int, str) -> bool`, `() -> int`. A function value is any top-level non-generic `fun`, a lambda, or a partial application; closures and plain functions share the type ([[Language/Functions-and-closures]]). A function type in source needs a result type; for a function without one it is `()`: `(str) -> ()` (D140).

## Option and Result

Every program has this prelude (`prelude_src` in [[selfhost/checker.my]]):

```
enum Option<T> { Some(T), None }
enum Result<T, E> { Ok(T), Err(E) }
fun get<K: Eq + Hash, V>(m: [K: V], k: K) -> Option<V>
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
| `str` | yes (bytes) | yes (bytes, MYLA-318) | yes | yes |
| struct, enum | with `Eq` (`impl Eq` or `#derive(Eq)`) | with `Ord` | no | with `Eq` and `Hash` (D163) |
| `()` | yes (always equal) | no | no | yes |
| tuple, list | when the elements are `Eq` (D163) | no | no | when the elements are `Eq` and `Hash` |
| map, function, `StringBuilder` | no | no | no | no |
