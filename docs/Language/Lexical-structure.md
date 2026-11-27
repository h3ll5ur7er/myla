# Lexical structure

How source text becomes tokens. The lexer is [[selfhost/lexer.my]]; token kinds and keywords are in [[selfhost/tokens.my]].

[TOC]

## Source files

A program is one or more UTF-8 files with the extension `.my`. A file is a sequence of top-level declarations: `struct`, `enum`, `fun`, `impl`, `trait`, `typealias`, `const` and imports. Statements at the top level are a parse error.

## Whitespace, newlines, semicolons and comments

- Spaces, tabs and carriage returns separate tokens.
- A **newline ends a statement or declaration**. Runs of blank lines count as one, and leading and trailing newlines are dropped.
- A **`;`** may stand for that newline (D61): between the statements of a block, between top-level declarations, between the methods of an `impl` or a trait, and after a bare `return`. A run of `;` and newlines is one separator, so a trailing `;` is harmless. Line breaks stay the normal style; `;` is for short code that reads better on one line. Anywhere else, including between call arguments, list elements, struct fields and match arms, `;` is a syntax error.

```myla
const W: int = 3; const H: int = 4

trait Shape { fun area(self) -> int; fun name(self) -> str }

fun abs(x: int) -> int { if x < 0 { return -x }; return x }

fun main() {
    let a = abs(W - H); print(a)
}
// output:
// 1
```

- A statement goes on across a line break (D104 (3), [[MYLA-224]]):
  - inside `( )` and `[ ]`: call arguments, parameters, parenthesised expressions, tuples, indexes, list and map literals (but a `{ }` block inside them has statements again, so a lambda's body or a `match` inside an argument list works as everywhere else);
  - after a binary operator that ends the line (`+`, `&&`, `|>`, …), except `>`, which also closes a generic type (`let x: Option<int>` ends its line), and `as`, whose type goes on its line (`x as` at a line's end is an error: expected a type);
  - inside struct literals, struct and enum bodies, `impl`/`trait` bodies and between match arms, as before.
- A line that starts with an operator still starts a new statement, so a chain puts the operator at the end of the line. A line inside brackets that starts with a word only a statement or declaration starts (`let`, `return`, `fun`, `while`, `for`, …) ends the bracket that was never closed, so a missing `)` gives one error and the parser goes on.

```myla
fun main() {
    let total = add(
        1,
        2
    )
    let ok = total > 2 &&
        total < 10
    let scaled = (total
        * 10
        + 1)
    print(scaled)
    print(ok)
}

fun add(
    a: int,
    b: int
) -> int {
    return a + b
}
// output:
// 31
// true
```

- A trailing comma may follow the last element of every comma-separated list (D104 (4), [[MYLA-225]]): call and attribute arguments, the parameters of functions, methods and lambdas, list, map and tuple literals, struct fields and literals, enum variants and their payloads, generic arguments and parameters, tuple and function types, patterns and import lists. A one-element tuple needs its comma: `(1,)` is a tuple, `(1)` the number in parentheses, and `()` the unit value ([[Language/Types]], D138).
- `else` may sit on the line after the closing `}` of its `if`.
- `// …` comments run to the end of the line; `/* … */` comments may span lines and do **not** nest (the first `*/` ends them). An unterminated block comment is a lex error.

## Identifiers and keywords

An identifier follows Unicode's identifier syntax: it starts with `_` or an XID_Start character (a letter of any script, or a letter number such as `Ⅻ`) and continues with XID_Continue characters (those, digits of any script, combining marks such as the accent in a decomposed `é`, `_` and a few others such as `·`): `größe`, `π`, `日本`. Identifiers aren't normalized, so a precomposed and a decomposed `é` make different names. Keywords and number literals stay ASCII (`١` is no digit of a literal). The lexer uses a generated table (`selfhost/unicode.my`, written by `scripts/gen_unicode_tables.py`, D72). They are case-sensitive. By convention types are `PascalCase` and everything else `snake_case`.

Reserved keywords:

```
let var fun return become actor async await struct enum impl trait self match typealias as pub
import from const break continue if else while for in true false
bool str int8 int16 int32 int64 uint8 uint16 uint32 uint64
```

These are **not** keywords but built-in names, resolved by the checker: `int`, `float`, `float32`, `float64`, `char`, `StringBuilder`, `Self`, `Option`, `Result`, `Some`, `None`, `Ok`, `Err` and the built-in functions ([[Language/Standard-library]]). A bare `_` is the wildcard in patterns and bindings, and the hole of a partial application.

## Integer literals

```myla
fun main() {
    let a = 42            // int (= int32)
    let b = 255u8         // suffix: i8 i16 i32 i64 u8 u16 u32 u64
    let c = 0xFF_FF       // hex, with _ separators
    let d = 0b1010_0101u8 // binary, suffixed
    let e = 0o755         // octal
    let f = 1_000_000i64
    print(a + c)
    print(b)
    print(d)
    print(e)
    print(f)
}
// output:
// 65577
// 255
// 165
// 493
// 1000000
```

- `_` may only stand between two digits.
- There are no negative literals: `-5` is unary minus applied to `5`, but a negated literal is checked as the value it denotes: `-128i8` and `let a: int8 = -128` work, `128i8` and `let b: uint8 = -1` are type errors, and so is `let c: uint8 = -'a'` (a char literal where an integer is expected is its code, so `-'a'` is -97; [[MYLA-417]], [[MYLA-544]]).
- An unsuffixed literal takes the integer type its context expects (an annotation, a parameter, the other operand on either side, `5000000000 + big` and `-1 + big` as `big + 5000000000` with `big: int64`, a range's other bound, another arm of an `if` or a `match`), defaulting to `int`. It must fit that type, or it is a type error ([[MYLA-544]]). One that doesn't fit `int` waits for that type, in either arm: `if c { big } else { 5000000000 }` and `match c { true => -5000000000, false => big }` are `int64`s ([[MYLA-609]]). A literal *pattern* is checked as the value it denotes, so `128` or `-1` can't match an `int8` or `uint8` ([[MYLA-7]]).
- A literal directly followed by letters that aren't a suffix (`5x`) is a lex error.

## Float literals

A decimal number with a fraction (`1.5`), an exponent (`2e10`, `1.5e-3`) or a float suffix (`2f32`, `0.1f64`) is a float. Hex, binary and octal literals are always integers. `2..10` stays a range and `t.0` a tuple index, because a fraction needs a digit after the dot; a number right after a `.` is always a tuple index, with no fraction or exponent, so `v.0.0` is two of them ([[MYLA-545]]).

An unsuffixed float literal takes the float type its context expects, defaulting to `float64` (the `float` alias, D102; it was `float32` until November 2026, D19).

## Character literals

`'a'`, `'é'`, `'😀'`, and the escapes (the same in strings): `\n`, `\t`, `\r`, `\0`, `\\`, `\'`, `\"` and `\u{1F600}` (1–6 hex digits, not a surrogate, at most `10FFFF`), as in `'\n'` or `'\u{e9}'`. Any other escape is a lex error. The value is the Unicode scalar.

A character literal has type `char`, except that an **ASCII** literal also fits an integer type when one is expected, so byte comparisons read naturally: `s[i] == 'a'` compares a `uint8` with 97 (D42).

## String literals

`"…"` with the escapes characters take (D72): `\n`, `\t`, `\r`, `\0`, `\\`, `\"`, `\'` and `\u{…}`, so `"\r\n"` is a protocol's line ending and `"\u{20AC}"` is `€` (stored as its UTF-8 bytes). A `\u{…}` naming a surrogate or a value above `10FFFF` is a lex error, as in a character. A string can't span lines.

## Interpolated strings

`f"…"` strings embed expressions in `{ }`; `{{` and `}}` are literal braces:

```myla
fun main() {
    let name = "Myla"
    let n = 3
    print(f"{name} has {n * 2} {"braces"}: {{}}")
}
// output:
// Myla has 6 braces: {}
```

The lexer rewrites an f-string into a call `format("… {} …", expr, …)`: each hole is cut out by counting braces (skipping nested string and char literals) and lexed again as an expression. So holes accept any expression, and the checker treats the result exactly like `format` ([[Language/Collections-and-strings]]). F-strings are single-line, an empty hole `{}` is an error, and a hole may carry a format spec after a colon, `{x:>8.3}` (D139, [[Language/Collections-and-strings]]). Their text takes the escapes of strings; an escaped brace such as `\u{7B}` is text, not a hole.

## Operators and punctuation

```
+ - * / % & | ^ ~ ! = == != < <= > >= && || |> -> => ..
( ) { } [ ] , : . # ?
```

`<<` and `>>` are not tokens. The parser reads two `<` or two `>` tokens that touch (no space between them) as a shift, so that nested generics such as `Option<List<int>>` close normally (D44). Consequently `a > > b` is not a shift. `>=` is one token, but where it would close type arguments (`let x: Option<int>= None`) the parser splits it into `>` and `=` ([[MYLA-15]]).
