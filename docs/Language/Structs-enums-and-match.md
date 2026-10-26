# Structs, enums and match

[TOC]

## Structs

```myla
struct Point {
    x: int,
    y: int,
}

struct Pair<A, B> {
    first: A,
    second: B,
}

fun main() {
    var p = Point { x: 1, y: 2 }
    p.x = 10
    let q = p                   // a copy
    p.y = 0
    print(q.y)                  // 2
    let pr = Pair { first: "one", second: 1 }
    print(pr.first)
}
```

- Fields are `name: Type`, separated by commas or newlines; a trailing comma is fine. Types may be declared in any order.
- A literal gives every field exactly once, in any order. A generic struct's type arguments are inferred from the field values (or the expected type); `Pair<int, str> { … }` is not valid syntax.
- Structs are values: binding, passing and returning copies them (cheaply for heap-backed fields, which are copy-on-write).
- A struct can't contain itself, directly or through other structs and tuples ("would have infinite size"); put the cycle through an enum, which is boxed.

## Enums

```myla
enum Expr {
    Num(int),
    Add(Expr, Expr),
    Neg(Expr),
}

fun eval(e: Expr) -> int {
    return match e {
        Num(n) => n
        Add(a, b) => eval(a) + eval(b)
        Neg(x) => -eval(x)
    }
}

fun main() {
    let e = Expr.Add(Expr.Num(2), Expr.Neg(Expr.Num(5)))
    print(eval(e))
}
```

- Variants have no payload or a positional payload (D32); named-field variants don't exist.
- Construct with the enum's name: `Expr.Num(1)`, `Color.Red`. Only the prelude's `Some`, `None`, `Ok` and `Err` work without it (D31).
- A generic variant without a payload (`List.Nil`, `None`) needs the expected type from context.
- **Recursive enums** are allowed: an enum that takes part in a cycle is *boxed*, stored as a pointer to a reference-counted heap cell wherever it appears inside another aggregate. This is invisible in the language; see [[Architecture/Native-backend]].

## match

`match` is an expression (D30):

```myla
fun describe(t: (int, bool)) -> str {
    return match t {
        (0, _) => "zero"
        (n, true) if n > 100 => "big and true"
        (1, _) | (2, _) => "small"
        _ => {
            let s = "other"
            s
        }
    }
}

fun main() {
    print(describe((2, false)))
}
```

- Arms are `pattern [if guard] => body`, separated by newlines or commas. A body is an expression, or a block whose final expression statement is its value. An arm that always returns (or calls `panic`/`unreachable`) doesn't need a value.
- The scrutinee is evaluated once; arms are tried top to bottom; bindings are copies.
- Used as a value, all arm values must have one type (unsuffixed integer literals adopt the type of the others).
- The arms of a `match` used as a statement need no value: an arm block may end in another `match` statement or a call ([[MYLA-59]]). In a `match` used as a value, the last expression statement of a block arm is its value.

### Patterns

| Pattern | Example | Matches |
| --- | --- | --- |
| Wildcard | `_` | Anything |
| Binding | `x` | Anything, and binds it |
| Literal | `42`, `-1`, `'a'`, `"go"`, `true` | Equal integer, `char`, `str` or `bool` (no float literals). An integer literal must be a value of the scrutinee's type: `-1` on a `uint8` or `128` on an `int8` is a type error ([[MYLA-7]]) |
| Variant | `Some(x)`, `Shape.Rect(w, h)`, `.Red`, `Red` | That variant, with payload patterns |
| Tuple | `(a, _, 0)` | A tuple of that arity |
| Struct | `Point { x: 0, y }` | A struct; `y` alone binds field `y`; unlisted fields are ignored |
| Or | `1 | 2 | 3` | Any alternative; every alternative binds the same names with the same types |

A bare name that is a payload-less variant of the scrutinee's enum is a variant test, not a binding (`Red` above).

### Exhaustiveness and redundancy

The checker requires a match to cover every value ([[src/myla/types.py#L2522-L2610]]):

- On an enum, every variant must be covered by an arm without a guard whose sub-patterns are all irrefutable, or there must be a catch-all arm.
- On a `bool`, both `true` and `false` literal arms, or a catch-all.
- On anything else (integers, strings, tuples, structs), a catch-all arm (`_` or a binding, or a pattern that can't fail).
- An arm after a catch-all, or one whose variants are all covered already, is a type error.

These rules are conservative: nested matches such as `Some(Ok(v))`, `Some(Err(e))`, `None`, and `true | false` on a `bool`, are rejected even though they are exhaustive ([[MYLA-14]]). Add a `_` arm.
