# Expressions and operators

The parser implements precedence by one function per level ([[src/myla/parser.py#L663-L763]]); the operator typing rules are in `Checker._infer_binary` ([[src/myla/types.py#L2750-L2881]]).

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
| integer ↔ `char` | The codepoint, unchecked one way and wrapped the other |
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
- `f >> g` with two one-argument function values is `(x) => g(f(x))`; `f`'s result type must equal `g`'s parameter type. With integer operands `>>` is the shift (D24).
- A call with `_` arguments is a lambda over the holes, left to right; the other arguments (and a method's receiver) are captured by value. Every parameter must be listed: there is no automatic currying (D51). It works on functions, methods and function values, not on generic functions.

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

The interpreter evaluates operands, arguments and literal elements left to right. Native code (both backends) currently evaluates binary operands and call arguments right to left, so side effects in operands come out in a different order ([[MYLA-8]]). Until that is fixed, don't rely on the order of side effects within one expression.
