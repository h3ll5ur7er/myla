# Myla (Rust edition) — Language Specification

This document describes the language as implemented by the interpreter in
`crates/myla-interp`, which is the reference semantics. Where the native back
end differs, that is noted in [architecture.md](architecture.md).

## 1. Lexical structure

- **Encoding:** UTF-8 source.
- **Whitespace:** spaces and tabs are insignificant except as token separators.
- **Newlines** are significant: they terminate statements (see §4).
- **Comments:** `// line` and `/* block */` (non-nesting). Comments are skipped.
- **Identifiers:** `[A-Za-z_][A-Za-z0-9_]*`.
- **Keywords:** `let var const fun return struct enum trait impl typealias if
  else while for in match break continue as import from pub self true false`
  and the concurrency keywords `async await actor spawn go chan select`.

### Literals

- **Integers:** decimal, `0x` hex, `0b` binary, `0o` octal, with `_` separators
  and an optional sized suffix `i8 i16 i32 i64 u8 u16 u32 u64`. Unsuffixed
  integer literals default to `int` (= `int32`).
- **Floats:** `3.14`, `1e9`, `2.0f32`, `6.022e23f64`. Unsuffixed floats default
  to `float64`. A float requires either a fractional part (`3.0`) or an
  exponent (`1e9`); `3..5` is a range, not a float.
- **Strings:** `"..."` with escapes `\n \t \r \\ \" \' \0 \u{XXXX}`.
- **Interpolated strings:** `f"x = {expr}, y = {y}"`. Use `{{`/`}}` for literal
  braces.
- **Chars:** `'a'`, `'\n'`, `'\u{1F600}'`.
- **Booleans:** `true`, `false`.

## 2. Types

| Category | Types |
| --- | --- |
| Integers | `int` (alias for `int32`), `int8/16/32/64`, `uint8/16/32/64` |
| Floats | `float` (alias for `float64`), `float32`, `float64` |
| Other scalars | `bool`, `char`, `str` |
| Aggregates | tuples `(A, B)`, lists `[T]`, maps `[K: V]` |
| Nominal | `struct`, `enum`, `actor` |
| Functions | `(A, B) -> C` |
| Channels | `chan<T>` |
| Generic | `Name<T, U>` |

Sized integers use two's-complement wrapping arithmetic. There are no implicit
numeric conversions; use `as` (§6).

## 3. Declarations

```myla
const PI: float = 3.14159

typealias Id = int

struct Point { x: int, y: int }

enum Shape { Circle(float), Rect(float, float) }

trait Area { fun area(self) -> float }

impl Area for Shape {
    fun area(self) -> float {
        match self {
            Shape.Circle(r) => 3.14159 * r * r,
            Shape.Rect(w, h) => w * h,
        }
    }
}

fun add<T>(a: T, b: T) -> T { return a + b }   // generics by erasure
```

Top-level items: `fun`, `struct`, `enum`, `trait`, `impl`, `actor`,
`typealias`, `const`, and `import`. Any item may be prefixed with `pub`.
Attributes are written `#name(args)[outputs]` before a declaration (see §8).

## 4. Statements and optional semicolons

A **statement is terminated by a newline or `;`**. This replaces the original's
strict one-statement-per-line rule. The soft rules (JS/Go/Swift-style):

- A newline inside `(...)` or `[...]` does **not** terminate a statement.
- A newline **after** a binary operator continues the expression:
  ```myla
  let x = 1 +
          2
  ```
- A newline **before** a leading `.`, `|>`, or `?` continues a chain:
  ```myla
  let n = xs
          |> len
  ```
- `;` is always an explicit terminator, so several statements may share a line:
  ```myla
  var i = 0; var total = 0
  ```

Statement forms: `let`/`var` bindings, assignment (`=`), `return`, `break`,
`continue`, `while`, `for ... in ...`, `select`, and expression statements.
`let` is immutable; `var` is mutable. Assigning to a `let` binding is a
compile-time error.

## 5. Expressions

`if`, `match`, and `{ ... }` blocks are **expressions** (a block's value is its
trailing expression). Other forms: literals, names, `self`, unary `- ! ~`,
binary operators, calls, method calls, field access, indexing, struct literals,
list/map/tuple literals, lambdas `(x) => e`, ranges `a..b`, casts `e as T`,
pipelines `x |> f`, the try operator `e?`, and the concurrency forms
`spawn e` / `await e`.

### Operator precedence (high → low)

```
unary  - ! ~  and postfix  as
* / %
+ -
<< >>
&
^
|
< <= > >=
== !=
&&
||
..
|>
```

`<<` / `>>` are formed from two adjacent `<` / `>` tokens, so generic types like
`Map<str, List<int>>` parse unambiguously. `&&` and `||` short-circuit.

### Pattern matching

```myla
match value {
    0 => "zero",
    1 | 2 | 3 => "small",
    n if n < 0 => "negative",
    Shape.Rect(w, h) => f"rect {w}x{h}",
    Point { x: 0, y } => f"on y axis at {y}",
    _ => "other",
}
```

Patterns: wildcard `_`, bindings, literals, tuples, enum variants (`Enum.Var(..)`
or `.Var(..)`), struct patterns, and or-patterns (`a | b`), with optional `if`
guards.

## 6. Casts

`e as T` performs explicit numeric/char conversions: int↔int (wrapping),
int↔float, float→int (truncating), int↔char. There are no implicit conversions.

## 7. Functions, closures, pipelines

- Functions are values; a top-level `fun` name evaluates to a callable.
- Lambdas: `(x: int, y: int) => x + y`, capturing the environment by value.
- **Partial application** with `_`: `add(_, 10)` yields a function of one arg.
- **Pipelines:** `x |> f` calls `f(x)`; `x |> f(a)` splices `x` as the first
  argument, i.e. `f(x, a)`.

## 8. Attributes and inline tests

- `#main` marks the entry point (otherwise a function named `main` is used).
- `#test(args)[expected]` declares an inline test: calling the function with
  `args` must equal `expected`. Run them with `myla test file.my`.

```myla
#test(10)[55]
fun fib(n: int) -> int {
    if n < 2 { return n }
    return fib(n - 1) + fib(n - 2)
}
```

## 9. Errors

Diagnostics are classified by stage — `lex`, `parse`, `type`, `runtime` — and
rendered with a source caret. The negative corpus in `examples/errors/` uses
`//~ <stage> error: <substring>` directives that the test suite asserts.

See also: [grammar.md](grammar.md), [stdlib.md](stdlib.md),
[concurrency.md](concurrency.md), [changes-from-original.md](changes-from-original.md).
