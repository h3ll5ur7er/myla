# Expressions and operators

The parser implements precedence by one function per level (`Parser._pipe` down to `Parser._unary` in [[src/myla/parser.py]]); the operator typing rules are in `Checker._infer_binary` ([[src/myla/types.py]]).

[TOC]

## Precedence

From loosest to tightest. Every binary level is left-associative.

| Level | Operators | Notes |
| --- | --- | --- |
| 1 | `|>` | Pipeline: the left value becomes the first argument |
| 2 | `||` | Short-circuits |
| 3 | `&&` | Short-circuits |
| 4 | `==` `!=` | |
| 5 | `<` `<=` `>` `>=` | `a < b < c` parses but doesn't type-check |
| 6 | `|` | Bitwise operators bind tighter than comparisons, unlike C |
| 7 | `^` | |
| 8 | `&` | |
| 9 | `<<` `>>` | Two touching `<`/`>` tokens; `>>` also composes functions |
| 10 | `+` `-` | `+` also concatenates strings |
| 11 | `*` `/` `%` | |
| 12 | `as` | `x as T`; `-x as T` is `(-x) as T` |
| 13 | `-` `!` `~` (prefix) | Right-associative |
| 14 | `f(…)` `x[i]` `x.f` `t.0` `x?` (postfix) | |

`a & b == c` therefore means `(a & b) == c`.

## Typing rules

- **Arithmetic** `+ - * / %`: both operands have the same integer or float type, and so does the result. An unsuffixed literal adopts the other operand's type. On a struct or enum, the operator calls the type's operator trait ([[Language/Methods-and-traits]]).
- **Integer division** truncates toward zero; `%` has the sign of the dividend. Division or remainder by zero is a runtime error.
- **Float arithmetic** follows IEEE-754: dividing by zero gives ±inf or NaN; `%` is `fmod`. A `float32` result is rounded to single precision after every operation.
- **Overflow** wraps (two's complement) at the operand width, in both backends.
- **Comparison** `< <= > >=`: same numeric type, or two `char`s. On structs and enums: through `Ord` (`a.cmp(b) < 0`).
- **Equality** `== !=`: same type, one of integer, float, `char`, `bool` or `str`; structs and enums through `Eq`. Tuples, lists and maps can't be compared.
- **Logic** `&& || !`: `bool` only.
- **Bitwise** `& | ^ ~`: integers only.
- **Shifts** `<<` `>>`: the result has the left operand's type; the amount may be any integer type. A constant amount outside `0 … width-1` is a type error; a run-time amount is masked to the width (`n & (width - 1)`). `>>` is arithmetic on signed types and logical on unsigned ones (D44).
- **String concatenation** `str + str` makes a new string (D41).

## Casts

`x as T` converts between numeric types and `char` (D26, D59):

| From → to | Behaviour |
| --- | --- |
| integer → integer | Wraps to the target width; widening sign- or zero-extends by the source's signedness |
| integer → float | Rounds to nearest |
| float → integer | Truncates toward zero and saturates: out-of-range values and ±inf clamp to the target's minimum or maximum, NaN gives `0` (D59) |
| float → float | Widens, or rounds to `float32` |
| integer ↔ `char` | Integer to `char`: the codepoint if it is a Unicode scalar (at most `0x10FFFF`, not a surrogate `0xD800`…`0xDFFF`), else a runtime error at the cast (`invalid char: 55296 is not a Unicode scalar value`; D98, [[MYLA-177]]); every `uint8` is one. `char` to integer: the codepoint, wrapped to the width |
| `char` ↔ float, `bool`, `str` | Not allowed |

The operand is typed without a hint from the target, so `300 as uint8` is `44`, not an error.

## Pipelines, composition, partial application

```myla
fun inc(x: int) -> int { return x + 1 }
fun mul(x: int, k: int) -> int { return x * k }

fun main() {
    let a = 5 |> inc |> mul(3)       // mul(inc(5), 3) = 18
    let f = inc >> inc               // (x) => inc(inc(x))
    let triple = mul(_, 3)           // (h) => mul(h, 3)
    print(a)
    print(f(1))
    print(triple(4))
}
```

- `x |> f` is `f(x)`, and `x |> f(a, b)` is `f(x, a, b)`. It is rewritten by the parser (D50).
- `f >> g` with two one-argument function values is `(x) => g(f(x))`; `f`'s result type must equal `g`'s parameter type. With integer operands `>>` is the shift (D24). Both operands are functions or both are integers; anything else is an error (`shift amount for '>>' must be an integer`).
- A call with `_` arguments is a lambda over the holes, left to right. The other arguments (and a method's receiver) are evaluated once, left to right, when the partial is made, and every call reuses those values (D51, D60): `let p = g(f(1), _)` runs `f(1)` right there, not at each `p(…)`. Every parameter must be listed: there is no automatic currying. It works on functions, methods and function values bound to a name, not on generic functions.

## The `?` operator

`expr?` on an `Option<T>` or `Result<T, E>` evaluates to the `Some`/`Ok` payload, or returns `None`/`Err(e)` from the enclosing function. The function must return the same carrier, and for `Result` the same error type: there is no conversion (D36).

```myla
fun parse_digit(c: uint8) -> Result<int, str> {
    if c >= '0' && c <= '9' {
        return Ok((c - '0') as int)
    }
    return Err("not a digit")
}

fun sum2(s: str) -> Result<int, str> {
    let a = parse_digit(s[0])?
    let b = parse_digit(s[1])?
    return Ok(a + b)
}

fun main() {
    match sum2("47") {
        Ok(n) => print(n)
        Err(e) => print(e)
    }
}
```

Inside a lambda, `?` returns from the lambda, so it needs the **lambda's** result type, not the enclosing function's: pass the lambda where a function type is expected, or annotate the variable it is bound to.

```myla
let next: (int) -> Option<int> = (x: int) => Some(half(x)? + 1)   // fine in any function
let bad = (x: int) => Some(half(x)? + 1)     // error: the lambda's result type isn't known
```

The checker rewrites `?` into a `match` once the carrier is known, so the backends never see it.

## Evaluation order

Subexpressions evaluate left to right, in the interpreter and in native code alike ([[MYLA-8]]):

- A binary operator evaluates its left operand, then its right. `&&` and `||` skip the right operand when the left one decides.
- A call evaluates the arguments in order; a method call evaluates the receiver first, and a call through a function value evaluates the callee first. `x |> f(y)` is `f(x, y)`, so `x` comes first.
- A `var self` method writes into its receiver, so it takes the receiver's place first (its indices, once) and its value only after the arguments, as `push` does: in `c.add(c.bump_get())` the change `bump_get` makes to `c` is kept ([[MYLA-238]]). A read-only receiver's value is taken first; native code still takes it after the arguments ([[MYLA-237]]).
- Struct, tuple, list and enum literals evaluate their elements in the order written (a struct literal in the order of its fields as written, not as declared). A map literal evaluates each key, then its value.
- `format` and `f"…"` evaluate their arguments left to right.
- A partial application `f(a, _)` evaluates its receiver and filled arguments when it is made (D60). `_` stands only as a call argument (`'_' placeholder is only valid as a call argument`).
- An assignment evaluates the value first, then the place: `xs[i] = v` evaluates `v`, then `xs`, then `i`. `push(xs, v)`, `append_byte(sb, b)` and the other writes into a container likewise evaluate the value before they touch the container (MYLA-4).
