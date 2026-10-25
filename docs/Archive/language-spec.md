# Myla Language Specification — v0.0

This document defines the concrete syntax and semantics of Myla v0.0. It is the
source of truth for what the lexer, parser, interpreter, and compiler must
implement. It is intentionally small: v0.0 covers variables, expressions,
flow-control, loops, functions, and structs — nothing more.

> Design philosophy (from the README): *focus on simplicity, not safety*.
> Where a choice is between "simple" and "clever", v0.0 picks simple.

---

## 1. Source files

- A Myla program is a UTF-8 text file with the extension `.my`.
- Source is a sequence of *declarations*. The top-level declarations are
  `struct` declarations, `fun` (function) declarations, and `typealias`
  declarations. Any declaration may be preceded by one or more *attributes*
  (see [§8](#8-attributes-main-test)).
- Execution starts at the function named `main`. A runnable program must define
  exactly one `fun main()`.

```my
fun main() {
    print("Hello from Myla!")
}
```

---

## 2. Lexical structure

### 2.1 Whitespace and line endings

Spaces, tabs, and newlines separate tokens but are otherwise insignificant.
Myla is **not** indentation-sensitive; blocks are delimited by `{ }`.
Statements are separated by newlines (see [§5](#5-statements)); semicolons are
not used.

### 2.2 Comments

```my
// line comment — runs to end of line

/* block comment
   may span multiple lines */
```

Block comments do **not** nest in v0.0 (the first `*/` closes the comment).

### 2.3 Identifiers

```
identifier ::= (letter | "_") (letter | digit | "_")*
letter     ::= "a".."z" | "A".."Z"
digit      ::= "0".."9"
```

Identifiers are case-sensitive. By convention, types use `PascalCase` and
values/functions use `snake_case`, but this is not enforced.

### 2.4 Keywords (reserved)

```
let  var  fun  return  struct  typealias
if   else  while  for   in
true false  bool  str
int8 int16 int32 int64  uint8 uint16 uint32 uint64
```

`int` is a built-in type alias for `int32` (see [§3](#3-types)), not a keyword,
so it can technically be shadowed — but doing so is strongly discouraged.

Keywords cannot be used as identifiers.

### 2.5 Literals

| Kind   | Examples            | Default type        |
|--------|---------------------|---------------------|
| int    | `0`, `42`, `1000`   | `int` (= `int32`)   |
| bool   | `true`, `false`     | `bool`              |
| string | `"hello"`, `""`     | `str`               |

- **int** literals are base-10 only in v0.0 (no hex/binary, no underscores, no
  sign — a leading `-` is the unary minus operator, not part of the literal).
- An integer literal's type defaults to `int` (i.e. `int32`). In a context that
  expects another integer type (annotation, parameter, return), the literal
  takes that type instead, as long as the value fits; otherwise it is a
  compile-time error. There is no implicit widening/narrowing between sized
  integer types at runtime.
- **Type suffixes** disambiguate explicitly. A literal may carry a suffix naming
  its type with the short form `i8/i16/i32/i64` or `u8/u16/u32/u64`:

  ```my
  let mask = 255u8     // a uint8 with value 0xFF
  let big  = 123i64    // an int64
  let n    = 42        // defaults to int (= int32)
  ```

  The value must fit the suffixed type or it is a compile-time error. (Floating
  suffixes `f32`/`f64` are reserved for when floats land — see
  [future-features.md](future-features.md).)
- **string** literals are double-quoted and support these escapes:
  `\n` (newline), `\t` (tab), `\\` (backslash), `\"` (double quote).
  No string interpolation in v0.0.

### 2.6 Operators and punctuation

```
+  -  *  /  %            arithmetic
==  !=  <  <=  >  >=     comparison
&&  ||  !                logical
=                        assignment
( )  { }                 grouping / blocks
,  :  .                  separators / field access
->                       function return type
..                       half-open range (for loops)
#                        attribute marker (see §8)
[ ]                      attribute output list (see §8)
```

---

## 3. Types

v0.0 is **statically typed**. Every expression has a type known at compile time.
There is no implicit coercion between types.

### 3.1 Built-in types

Myla uses **explicitly sized** primitive types. This is a deliberate choice over
a Python-style arbitrary-precision/dynamic numeric model: fixed widths map
directly onto machine registers and memory layout, which keeps the native
compiler simple and makes self-hosting far more predictable.

**Integer types**

| Type     | Width   | Signedness | Range                                  |
|----------|---------|------------|----------------------------------------|
| `int8`   | 8-bit   | signed     | -128 .. 127                            |
| `int16`  | 16-bit  | signed     | -32768 .. 32767                        |
| `int32`  | 32-bit  | signed     | -2^31 .. 2^31-1                        |
| `int64`  | 64-bit  | signed     | -2^63 .. 2^63-1                        |
| `uint8`  | 8-bit   | unsigned   | 0 .. 255                               |
| `uint16` | 16-bit  | unsigned   | 0 .. 65535                             |
| `uint32` | 32-bit  | unsigned   | 0 .. 2^32-1                            |
| `uint64` | 64-bit  | unsigned   | 0 .. 2^64-1                            |

All integer types **wrap** on overflow within their width (two's complement for
signed; modular for unsigned) — see [§7.4](#74-evaluation-and-arithmetic).

**Other primitives**

| Type   | Description                                 |
|--------|---------------------------------------------|
| `bool` | `true` or `false`; only valid in conditions |
| `str`  | immutable sequence of bytes (UTF-8)         |

> Floating-point types (`float32`, `float64`) are intentionally **not** in v0.0;
> see [future-features.md](future-features.md).

### 3.2 `int` and built-in aliases

`int` is a **built-in type alias** for `int32`:

```my
typealias int = int32   // provided by the language (conceptually)
```

It is the default type of integer literals and the recommended "I just want an
integer" type. Because it is a true alias, `int` and `int32` are the *same* type
and are freely interchangeable.

### 3.3 Type aliases (`typealias`)

Users may define their own aliases. An alias introduces a new name for an
existing type; it is **not** a distinct type (no new-type semantics in v0.0).

```my
typealias Byte = uint8
typealias Id   = int64

fun first_byte(b: Byte) -> Byte {
    return b
}
```

Aliases are top-level declarations and are visible throughout the file
regardless of order. They may refer to any type (primitive or struct), but
cycles (`typealias A = B; typealias B = A`) are a compile-time error.

### 3.4 Struct types

User-defined aggregate types (see [§6](#6-structs)). A struct type is referred
to by its name.

### 3.5 Type annotations and inference

A variable's type may be written explicitly or inferred from its initializer:

```my
let a: int = 5      // explicit
let b = 5           // inferred as int
let name = "Ann"    // inferred as str
let ok = true       // inferred as bool
```

Function parameters and return types are **always** annotated explicitly.
There is no `void`/unit syntax: a function with no `-> T` returns nothing and
its call cannot be used as a value.

---

## 4. Variables and mutability

```my
let x = 10     // immutable binding — reassignment is an error
var y = 0      // mutable binding
y = y + 1      // ok
```

- `let` introduces an **immutable** binding; assigning to it after declaration
  is a compile-time error.
- `var` introduces a **mutable** binding.
- A binding must be initialized at declaration (no uninitialized variables).
- Bindings are block-scoped (see [§7.1](#71-scoping)).

Assignment is a statement, not an expression; `a = b = c` is not allowed.

---

## 5. Statements

A *block* is `{` followed by zero or more statements followed by `}`.
Statements are separated by newlines. The statement forms are:

| Statement            | Example                              |
|----------------------|--------------------------------------|
| variable declaration | `let x = 1`                          |
| assignment           | `x = x + 1`                          |
| expression statement | `print("hi")` (a call)               |
| `if` / `else`        | see §5.1                             |
| `while`              | see §5.2                             |
| `for ... in`         | see §5.3                             |
| `return`             | `return x` or bare `return`          |

Myla v0.0 is **statement-oriented**: blocks do not evaluate to a value, and
`if`/loops are not expressions.

### 5.1 If / else

```my
if score >= 60 {
    print("pass")
} else {
    print("fail")
}
```

- The condition must be of type `bool`. There is no truthiness; `if 1 { }` is an
  error.
- `else` is optional. `else if` chains by nesting an `if` as the else-block:

```my
if n < 0 {
    print("neg")
} else if n == 0 {
    print("zero")
} else {
    print("pos")
}
```

### 5.2 While

```my
var i = 0
while i < 5 {
    print(i)
    i = i + 1
}
```

The condition must be `bool`.

### 5.3 For ... in (range)

```my
for i in 0..5 {
    print(i)   // prints 0,1,2,3,4
}
```

- The only iterable form in v0.0 is an integer range `start..end`.
- The range is **half-open**: it includes `start` and excludes `end`.
- `start` and `end` are `int` expressions; the loop variable is an immutable
  `int` scoped to the loop body.

### 5.4 Return

```my
fun square(n: int) -> int {
    return n * n
}
```

- In a function declaring `-> T`, every path must `return` a value of type `T`.
- In a function with no return type, `return` (bare) exits early; falling off
  the end of the body is also allowed.

---

## 6. Structs

### 6.1 Declaration

```my
struct Point {
    x: int,
    y: int,
}
```

- Fields are name/type pairs. A trailing comma is allowed.
- Field types may be built-in or other struct types declared anywhere in the
  file (declaration order does not matter).

### 6.2 Construction

```my
let p = Point { x: 3, y: 4 }
```

All fields must be provided exactly once, in any order.

### 6.3 Field access

```my
print(p.x)        // read
```

Field assignment is allowed only through a `var` binding:

```my
var q = Point { x: 0, y: 0 }
q.x = 10
```

Structs have **value semantics** in v0.0: assigning a struct copies it.

---

## 7. Expressions and semantics

### 7.1 Scoping

- Lexical, block scoped. A name is visible from its declaration to the end of
  the enclosing block.
- Inner blocks may shadow names from outer blocks.
- Functions, structs, and type aliases share a single top-level (global)
  namespace and are visible throughout the file regardless of order.

### 7.2 Operator precedence

From highest (binds tightest) to lowest:

| Level | Operators                     | Associativity |
|-------|-------------------------------|---------------|
| 1     | `()` call, `.` field access   | left          |
| 2     | unary `-`, unary `!`          | right         |
| 3     | `*`, `/`, `%`                 | left          |
| 4     | `+`, `-`                      | left          |
| 5     | `<`, `<=`, `>`, `>=`          | left          |
| 6     | `==`, `!=`                    | left          |
| 7     | `&&`                          | left          |
| 8     | `||`                          | left          |

Parentheses `(...)` override precedence.

### 7.3 Type rules for operators

- Arithmetic (`+ - * / %`): `T op T -> T`, where `T` is any integer type. **Both
  operands must be the same integer type**; there is no implicit mixing (e.g.
  `int32 + int64` is an error — convert explicitly).
- Comparison (`< <= > >=`): `T op T -> bool` for the same integer type `T`.
- Equality (`== !=`): both operands the same type (any integer type, `bool`, or
  `str`) `-> bool`.
- Logical (`&& || !`): operate on `bool` only, produce `bool`.
- `&&` and `||` short-circuit.
- String concatenation is **not** in v0.0 (`+` on `str` is an error).

### 7.4 Evaluation and arithmetic

- Subexpressions evaluate left-to-right.
- Integer division `/` truncates toward zero; `%` is the remainder with the sign
  of the dividend (signed types). For unsigned types both are the usual unsigned
  operations.
- Division or modulo by zero is a runtime error (the interpreter aborts with a
  diagnostic; the compiled program traps).
- Integer overflow **wraps** within the operand type's width (two's-complement
  for signed, modular for unsigned). Chosen for simplicity: no overflow checks
  in generated code. Each sized type wraps at its own width (e.g. `int8`
  arithmetic wraps modulo 256).

### 7.5 Function calls

```my
fun add(a: int, b: int) -> int {
    return a + b
}

fun main() {
    let s = add(2, 3)
    print(s)
}
```

- Arguments are passed by value (structs are copied).
- Argument count and types must match the declaration.
- Recursion is allowed.

### 7.6 The `print` builtin

`print(x)` writes a textual representation of `x` followed by a newline to
standard output. It accepts a single argument of any integer type, `bool`, or
`str`. Representations: integers as base-10 (unsigned types print no sign),
`bool` as `true`/`false`, `str` as its raw characters. `print` is the only
builtin in v0.0 and is not a user-callable first-class function.

---

## 8. Attributes (`#main`, `#test`)

Declarations may be annotated with **attributes**: compile-time metadata written
on the lines directly above the declaration. An attribute is `#name`, optionally
followed by a parenthesized argument list and (for `#test`) a bracketed expected
result. Multiple attributes stack.

```
attribute ::= "#" name ( "(" args? ")" )? ( "[" args? "]" )?
```

v0.0 supports a **fixed, built-in set** of attributes (this is not a general
user-macro system — see [future-features.md](future-features.md) for that).
Unknown attributes are a compile-time error.

### 8.1 `#main` — entry point

Marks the program's entry function, removing the "must be named `main`"
convention:

```my
#main
fun run(args: [str]) {
    print("starting")
}
```

- A program has exactly one entry point. It is the `#main`-annotated function if
  present; otherwise the function named `main`. Having both a `#main` function
  and a separate `main`, or more than one `#main`, is a compile-time error.
- (The `[str]` argument list shown is illustrative; list types arrive
  post-v0.0. In v0.0 the entry function takes no parameters.)

### 8.2 `#test` — inline test cases

Attaches example-based tests to a function. Each `#test(inputs)[expected]`
declares one case: call the function with `inputs` and assert the result equals
`expected`.

```my
#test(1, 2)[3]
#test(4, 2)[6]
fun add(a: int, b: int) -> int {
    return a + b
}
```

- Multiple `#test` lines = multiple cases.
- `inputs` must match the function's parameter list; `expected` must match its
  return type. These are checked at compile time.
- The test runner (`myla test`) executes every `#test` case and reports
  pass/fail. Tests do not affect `run`/`build` output.

---

## 9. Errors

Errors fall into two categories:

- **Compile-time** (detected by lexer/parser/type checker): syntax errors,
  unknown names, type mismatches, assigning to a `let`, missing `return`,
  wrong argument counts. These prevent interpretation/compilation.
- **Runtime**: division/modulo by zero. Reported with a message; the program
  exits with a non-zero status.

All diagnostics should include a line and column (see `architecture.md`).

---

## 10. Complete sample program

```my
struct Point {
    x: int,
    y: int,
}

fun manhattan(a: Point, b: Point) -> int {
    var dx = a.x - b.x
    var dy = a.y - b.y
    if dx < 0 { dx = -dx }
    if dy < 0 { dy = -dy }
    return dx + dy
}

fun main() {
    let origin = Point { x: 0, y: 0 }
    let here = Point { x: 3, y: 4 }

    print(manhattan(origin, here))   // 7

    var total = 0
    for i in 0..5 {
        total = total + i
    }
    print(total)                     // 10

    var n = total
    while n > 0 {
        n = n - 1
    }
    print(n == 0)                    // true
}
```

This program exercises every v0.0 feature: structs, functions, `let`/`var`,
arithmetic, `if`, `for`/range, `while`, comparison/equality, and `print`.
