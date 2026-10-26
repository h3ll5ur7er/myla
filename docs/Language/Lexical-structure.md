# Lexical structure

How source text becomes tokens. The lexer is [[src/myla/lexer.py]]; token kinds and keywords are in [[src/myla/tokens.py]].

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
```

- Newlines are skipped in these places only: inside call argument lists, attribute argument lists, list and map literals, struct literals, struct and enum bodies, `impl`/`trait` bodies and between match arms. A binary expression can **not** continue on the next line, and neither can a parenthesised expression or a tuple:

```myla
fun main() {
    let total = add(
        1,
        2
    )
    print(total)
}

fun add(a: int, b: int) -> int {
    return a + b
}
```

- Trailing commas are allowed in struct and enum bodies, struct, list, map and tuple literals, tuple and payload types, and patterns, but **not** in call arguments or function parameter lists (`f(1, 2,)` is a parse error).
- `else` may sit on the line after the closing `}` of its `if`.
- `// …` comments run to the end of the line; `/* … */` comments may span lines and do **not** nest (the first `*/` ends them). An unterminated block comment is a lex error.

## Identifiers and keywords

An identifier starts with a letter or `_` and continues with letters, digits and `_`. They are case-sensitive. By convention types are `PascalCase` and everything else `snake_case`.

Reserved keywords:

```
let var fun return struct enum impl trait self match typealias as pub
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
```

- `_` may only stand between two digits.
- There are no negative literals: `-5` is unary minus applied to `5`.
- An unsuffixed literal takes the integer type its context expects (an annotation, a parameter, the other operand), defaulting to `int`. It must fit that type, or it is a type error. For signed types the check allows a magnitude up to 2^(width-1), so that `-128i8` works; `128i8` is therefore accepted and wraps to -128. A literal *pattern* is checked as the value it denotes, so `128` or `-1` can't match an `int8` or `uint8` ([[MYLA-7]]).
- A literal directly followed by letters that aren't a suffix (`5x`) is a lex error.

## Float literals

A decimal number with a fraction (`1.5`), an exponent (`2e10`, `1.5e-3`) or a float suffix (`2f32`, `0.1f64`) is a float. Hex, binary and octal literals are always integers. `2..10` stays a range and `t.0` a tuple index, because a fraction needs a digit after the dot.

An unsuffixed float literal takes the float type its context expects, defaulting to `float32` (the `float` alias, D19).

## Character literals

`'a'`, `'é'`, `'😀'`, and the escapes `'\n'`, `'\t'`, `'\r'`, `'\\'`, `'\''`, `'\0'` and `'\u{1F600}'` (1–6 hex digits, not a surrogate, at most `10FFFF`). The value is the Unicode scalar.

A character literal has type `char`, except that an **ASCII** literal also fits an integer type when one is expected, so byte comparisons read naturally: `s[i] == 'a'` compares a `uint8` with 97 (D42).

## String literals

`"…"` with the escapes `\n`, `\t`, `\\` and `\"`. Other escapes (including `\r`, `\0` and `\u`) are lex errors in strings. A string can't span lines.

## Interpolated strings

`f"…"` strings embed expressions in `{ }`; `{{` and `}}` are literal braces:

```myla
fun main() {
    let name = "Myla"
    let n = 3
    print(f"{name} has {n * 2} {"braces"}: {{}}")
}
```

The lexer rewrites an f-string into a call `format("… {} …", expr, …)`: each hole is cut out by counting braces (skipping nested string and char literals) and lexed again as an expression. So holes accept any expression, and the checker treats the result exactly like `format` ([[Language/Collections-and-strings]]). F-strings are single-line, an empty hole `{}` is an error, and there are no format specifiers.

## Operators and punctuation

```
+ - * / % & | ^ ~ ! = == != < <= > >= && || |> -> => ..
( ) { } [ ] , : . # ?
```

`<<` and `>>` are not tokens. The parser reads two `<` or two `>` tokens that touch (no space between them) as a shift, so that nested generics such as `Option<List<int>>` close normally (D44). Consequently `a > > b` is not a shift. The same rule causes `Option<int>= x` to lex `>=` as one token and fail ([[MYLA-15]]).
