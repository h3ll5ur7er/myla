# Expressions and operators

The parser implements precedence by one function per level (`pipe` down to `unary` in [[selfhost/parser.my]]); the operator typing rules are in `Checker.infer_binary` ([[selfhost/checker.my]]).

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
- **Integer division** truncates toward zero; `%` has the sign of the dividend. Division or remainder by zero is a runtime error. The one quotient that doesn't fit, the minimum of a signed type divided by -1, overflows like any other result that doesn't fit (below): `integer overflow` where overflow is checked, the minimum again in a plain build (`-2147483648 / -1 == -2147483648`). Its remainder by -1 is 0 everywhere (`-2147483648 % -1 == 0`): the remainder fits, so it isn't an overflow.
- **Float arithmetic** follows IEEE-754: dividing by zero gives ±inf or NaN; `%` is `fmod`, exact (the remainder of the true quotient truncated). A NaN prints as `nan`. Which NaN an operation gives (its sign and payload) isn't observable: `std.math`'s `to_bits`, `copysign` and the other functions that read a float's sign or payload see every NaN as `0x7FF8000000000000` (D128): the processors differ (x86-64's `0.0 / 0.0` is `0xFFF8…`, aarch64's `0x7FF8…`), and `copysign(1.0, 0.0 / 0.0)` is `1` on both.
- **Overflow** (D175, refining D4): an integer `+`, `-`, `*`, unary `-` or `/` whose result doesn't fit the operands' type is the runtime error `integer overflow`, at the operator, where programs are run and tested: in the interpreter (`myla run`, `myla repl`), under `myla test` (interpreted and `--native`) and in a build with `myla build --checked`. A plain `myla build` wraps (two's complement at the width) with no check, so the release build pays nothing. `uint8` `0 - 1` overflows as `int32` `2147483647 + 1` does, and so does `-x` of an unsigned `x` other than 0. A negative literal is a literal, not a negation (`-128i8` fits). Code that means to wrap says so with the builtin methods `x.wrapping_add(y)`, `wrapping_sub`, `wrapping_mul` and `x.wrapping_neg()` of every integer type ([[Language/Standard-library/Int]]), which wrap everywhere and are the plain operator's one instruction natively; `std.int`'s `checked_*`, `saturating_*` and `overflowing_*` say the other intents. A `const` whose value overflows is a compile-time error (`const integer overflow`), as a constant division by zero is. Casts (`as`) and the bitwise operators never overflow. `int` stays `int32` (D6).
- **Characters** (D165, [[MYLA-318]]): `c - d` on two `char`s is the distance between their code points, an `int32` (`'p' - 'a' == 15`); `c + n` and `c - n`, with `c` a `char` and `n` an `int32`, are the `char` that far from `c`, checked as a cast to `char` is: one that isn't a Unicode scalar (below 0, a surrogate, past U+10FFFF) is the runtime error `invalid char` where the operator stands. The `char` is the left operand (`n + c` isn't one of them), the integer an `int32` (another type is converted with `as int32`: D4 mixes no types), and two `char`s can't be added. A char literal of at most 127 is still an integer where one is expected, and beside an integer it doesn't move, as before: `s[i] - 'a'` and `'0' + d` with `d: uint8` are `uint8`s, `n + 'a'` with `n: int` an `int32`, and `let k: int = 'a' + 1` is 98; but `'a' + 1` and `'a' + n` with `n: int` are chars now (they were `int32`s).
- **Comparison** `< <= > >=`: same numeric type, two `char`s, or two strings, byte by byte: the first byte that differs decides, unsigned, and a string that begins another comes first, the order `list_dir` sorts in (D165, [[MYLA-318]]). On structs and enums: through `Ord` (`a.cmp(b) < 0`). `str` is `Ord`, as the numbers and `char` are, so a generic `T: Ord` takes it (`xs.sort()` on a `[str]`, a `Heap<str>`).
- **Equality** `== !=`: same type, one of integer, float, `char`, `bool` or `str`; structs and enums through `Eq` (a generic one's when its type arguments meet its impl's bounds: `Pair<int, str>` of `#derive(Eq) struct Pair<A, B>`); `Option` and `Result` when their payloads are `Eq`, the right side typed by the left one and `None == opt` by the right one ([[MYLA-379]]); tuples and lists of `Eq` elements, element by element (D163). Maps can't be compared.
- **Logic** `&& || !`: `bool` only.
- **Bitwise** `& | ^ ~`: integers only.
- **Shifts** `<<` `>>`: the result has the left operand's type; the amount may be any integer type. A constant amount outside `0 … width-1` is a type error; a run-time amount outside it is the runtime error `shift amount out of range` where overflow is checked (D175), and masked to the width (`n & (width - 1)`) in a plain build. The bits shifted out are lost without an error (`1 << 31` is the `int32` minimum): a shift is a bit operation. `>>` is arithmetic on signed types and logical on unsigned ones (D44).
- **String concatenation** `str + str` makes a new string (D41).

```myla
fun main() {
    let c = 'x'
    print(c - 'a')                  // 23, an int32
    print(c + 1)                    // the char y
    var counts = [0, 0, 0]
    for ch in "abacab" { counts[ch - 'a'] += 1 }
    print(counts[0])
    print("apple" < "banana" && "Zebra" < "apple")
}
// output:
// 23
// y
// 3
// true
```

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
// output:
// 18
// 3
// 12
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
// output:
// 11
```

Inside a lambda, `?` returns from the lambda, so it needs the **lambda's** result type, not the enclosing function's: pass the lambda where a function type is expected, or annotate the variable it is bound to.

```myla fragment
let next: (int) -> Option<int> = (x: int) => Some(half(x)? + 1)   // fine in any function
let bad = (x: int) => Some(half(x)? + 1)     // error: the lambda's result type isn't known
```

The checker rewrites `?` into a `match` once the carrier is known, so the backends never see it.

## Evaluation order

Subexpressions evaluate left to right, in the interpreter and in native code alike ([[MYLA-8]]):

- A binary operator evaluates its left operand, then its right. `&&` and `||` skip the right operand when the left one decides.
- A call evaluates the arguments in order; a method call evaluates the receiver first, and a call through a function value evaluates the callee first. `x |> f(y)` is `f(x, y)`, so `x` comes first.
- A `var self` method writes into its receiver, so it takes the receiver's place first (its indices, once) and its value only after the arguments, as `push` does: in `c.add(c.bump_get())` the change `bump_get` makes to `c` is kept ([[MYLA-238]]). A read-only receiver's value, and every argument's, is taken when it is evaluated: a later argument that writes the same variable (`c.plus(c.bump_get())`, `f(d, d.bump_get())`) doesn't change what was passed ([[MYLA-237]]).
- Struct, tuple, list and enum literals evaluate their elements in the order written (a struct literal in the order of its fields as written, not as declared). A map literal evaluates each key, then its value.
- `format` and `f"…"` evaluate their arguments left to right.
- An operand's value is the one it had when it was evaluated, whatever a later operand of the same expression does to the variable it was read from: in `h.xs[0] + h.repl()`, where `repl` replaces `h.xs`, the left operand is the old element; likewise the base of an index or a slice (`h.g[0][h.k()]`, `h.xs[h.k():]`), each hole of an f-string or `format`, a map literal's key before its value, and a function value read from a list before its arguments (`h.fs[0](h.k())`) ([[MYLA-543]], B2).
- A partial application `f(a, _)` evaluates its receiver and filled arguments when it is made (D60). `_` stands only as a call argument (`'_' placeholder is only valid as a call argument`).
- An assignment evaluates the value first, then the place: `xs[i] = v` evaluates `v`, then `xs`, then `i`. `xs.push(v)`, `sb.append_byte(b)` and the other writes into a container likewise evaluate the value before they touch the container (MYLA-4). Every key, index and argument of such a write is computed before the container is written: in `m.remove(k())`, `m[k()] = v`, `xs[f()] = v`, `sb.append(g())` and `h.xs.put_at(h.grow(1), 5)` a call that copies the container keeps the copy as it was, and one that grows it sees the write land in the grown one ([[MYLA-415]], H4); the indices of a place go left to right, `g[h.bump()][h.bump()]`. A method call on a place takes the place first, its indices and keys once, then its arguments, then writes (D193): `c.g[c.k()].push(c.v())` runs `k`, then `v`, as `c.g[c.k()].insert(0, c.v())` and a `var self` method do.
