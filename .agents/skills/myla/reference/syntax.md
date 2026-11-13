# Myla syntax reference

Checked against the front end: `selfhost/tokens.my`, `selfhost/lexer.my`, `selfhost/parser.my`, `selfhost/ast.my`, `grammar/myla.ebnf` (and the checker where it decides what the parser lets through). When in doubt, the code wins; re-verify with `build/myla check`.

## Lexical

**Keywords** (39, `keywords()` / `keyword_kind` in `tokens.my`): `let var fun return become actor async await struct enum impl trait self match typealias as pub import from const break continue if else while for in true false bool str int8 int16 int32 int64 uint8 uint16 uint32 uint64`.

- **Contextual**: `defer` (a keyword only at a statement's start before `{`); `_` (an identifier token: wildcard pattern, discard in `let`, partial-application hole as a whole call argument).
- **Not keywords** (ordinary names): `int float float32 float64 char Self type loop mut where Some None Ok Err print format panic`. So `let int = 1` is legal, `let str = 1` is a parse error, and `type` works as a field name. A keyword can't be a field, variable, parameter or alias name.
- **Identifiers**: `_` or XID_Start, then XID_Continue (Unicode 15.1, not normalized): `größe`, `π`. No `$`, no `@`, no `'` in names.
- Whitespace: space, tab, `\r` (CRLF files work); a leading UTF-8 BOM is skipped.
- **Comments**: `// …` and `/* … */`. Block comments **don't nest**. There are no doc comments: `///` and `//!` are plain comments. A `//` comment after a `#test(…)[…]` on its line names that case.

**Operator and punctuation tokens** (`scan_operator`, `one_char_kind`):

| Tokens | Use |
| --- | --- |
| `->` `=>` `\|>` `..` | return/function type, match arm and lambda, pipe, `for` range |
| `==` `!=` `<=` `>=` `&&` `\|\|` | comparison, logic |
| `+ - * / % & \| ^ ~ ! < > =` | arithmetic, bitwise, unary, comparison, assignment |
| `( ) { } [ ] , : . # ? ;` | brackets, separators, attribute, try, statement separator |

There are no `<<`, `>>`, `+=`, `<<=`… tokens: the parser joins **touching** tokens (`<` `<`, `+` `=`, `<` `<=`). `1 < < 2` and `x + = 1` are errors. Not in the language: `++ -- ** :: ?. ?? @ $ ... ..= ->>` and `?:`.

### Literals

| Form | Examples | Notes |
| --- | --- | --- |
| Decimal int | `42`, `1_000_000` | `_` only between digits: not leading, trailing, doubled, or right after `0x` (`0x_FF`, `255_u8` are errors) |
| Hex / binary / octal | `0xFF`, `0XAB`, `0b1010_1010`, `0o17` | prefix letter either case; no `0` legacy octal |
| Int suffix | `255u8`, `3i64`, `0xFFu8` | `i8 i16 i32 i64 u8 u16 u32 u64`, glued to the digits; up to 2^64-1 (`18446744073709551615u64`) |
| Float | `1.5`, `1e10`, `1E-2`, `1.5e-3`, `1_000.000_5` | a digit is needed on both sides of `.`: `1.` is `1` then `.`, `.5` is an error; no hex floats, no `inf`/`nan` literals |
| Float suffix | `2f32`, `1.5f64` | only `f32`/`f64`; an int with an `f` suffix is a float |
| Char | `'a'`, `'\n'`, `'\''`, `'"'`, `'\u{1F600}'` | exactly one Unicode scalar; it's a `char` (an integer-like literal in the AST: fits `uint8` where one is expected) |
| String | `"a\tb \"q\" \u{e9}"` | one line only (a raw newline is "unterminated string literal"); **no raw strings, no multi-line strings, no `\x`**; build long text with `+` or a `StringBuilder` |
| f-string | `f"x = {x}, {y:>8.2}"` | see below |
| Bool, unit | `true`, `false`, `()` | |

**Escapes** (same in chars, strings, f-strings; `scan_escape`): `\n \t \r \0 \\ \" \'` and `\u{H…}` (1 to 6 hex digits, a scalar: not a surrogate, ≤ 0x10FFFF). Anything else (`\x41`, `\a`, `\{`, `\$`) is a lex error.

**f-strings** (`scan_fstring`): `f"…"` (the `f` touching the quote) is lowered by the lexer to `format("…", e1, e2, …)`.

- A hole `{expr}` or `{expr:spec}`: any single expression, strings and brackets inside included (`{m["a"]}`, `{if x > 3 { "big" } else { "small" }}`, `{p.x + 1}`); its brackets must balance within the hole.
- The spec starts at the hole's first `:` outside brackets and quotes (`{x::>6}` is fill `:`); it may not contain `{`/`}` (no `{x:>{w}}`).
- `{{` and `}}` are literal braces; a lone `}` is an error. Single-line, like strings.
- **Spec** (`std.fmt.parse_spec`, Rust's subset): `[[fill]align][+][#][0][width][.precision][kind]`, align `<` `>` `^`, kind `x X b o`. `.precision` needs a float; `x X b o` need an integer; `+`/`0` need a number; `#` needs a kind. No `-`, `e`, `?`, `{:?}`, `{0}`, `{name}`. Width counts scalars.
- What a hole can render: integers, floats, `char`, `bool`, `str`, and types with `impl Format`. **Not** lists, tuples, `Option`, `Result`, or structs/enums without `impl Format` (type error "format() cannot render…").
- `format("{} and {:>4}", a, b)` takes the same holes (`{}` only, positional by order).

```myla
fun main() {
    let x = 255
    let f = 3.14159
    print(f"{x:>6}|{x:*^9}|{x:#06x}|{x:b}|{f:.2}|{f:+08.2}|{{lit}}")
}
// output:
//    255|***255***|0x00ff|11111111|3.14|+0003.14|{lit}
```

## Statements end at newlines (`emit_newline`, `continues_line` in `lexer.my`)

- A line break ends a statement or declaration, except: (1) inside `( )` or `[ ]` (but again inside a `{ }` nested in them); (2) after a line-final binary operator: `+ - * / % == != < <= >= && || & | ^ |>`.
- It does **not** continue after `>` (it may close a generic type), `=`, `->`, `=>`, `,` outside brackets, `.`, `as`, `?`, or a keyword. `let x =⏎ 5`, `return a,⏎ b`, `1 =>⏎ 5` and `from m import a,⏎ b` are errors.
- A line **starting** with an operator is a new statement: `.len()` or `+ b` on the next line is a parse error, and a leading `- 2` is **silently** a separate expression statement (`let x = 1⏎ - 2` leaves `x == 1`). Put the operator at the line's end or wrap in `( )`; for method chains, wrap the whole chain in parentheses.
- `{` must be on the same line as `fun …`, `if cond`, `while`, `for`, `match x`, `impl …`, `struct …` (no Allman style). `else` may start the next line (statement and expression `if`).
- `;` = a line break: between statements, declarations, methods. Trailing `;` is harmless. Not allowed inside `( )`, `[ ]`, struct fields, match arms (`1 => 2; _ => 0` is an error).

## Precedence (`selfhost/parser.my`: `pipe` → `logic_or` → … → `cast` → `unary` → `postfix` → `primary`)

Loosest first; every binary level is left-associative.

| Level | Operators | Notes |
| --- | --- | --- |
| 1 | `\|>` | lowest, below `\|\|`: `a \|\| b \|> f` is `f(a \|\| b)` |
| 2 | `\|\|` | short-circuit |
| 3 | `&&` | short-circuit |
| 4 | `==` `!=` | |
| 5 | `<` `<=` `>` `>=` | chains parse (`a < b < c`) but then fail to type-check |
| 6 | `\|` | bitwise binds tighter than comparison (not C): `a & m == 0` is `(a & m) == 0` |
| 7 | `^` | |
| 8 | `&` | |
| 9 | `<<` `>>` | two touching tokens; `f >> g` on functions is composition (`g(f(x))`) |
| 10 | `+` `-` | `+` concatenates `str` |
| 11 | `*` `/` `%` | |
| 12 | `as` | `a * b as int64` is `a * (b as int64)`; `-x as T` is `(-x) as T`; chains `x as uint8 as int64` |
| 13 | prefix `-` `!` `~` `await` | right-assoc; `await f() + 1` is `(await f()) + 1`; `^` is not a unary operator outside an index |
| 14 | postfix `f(…)` `f<T>(…)` `x[i]` `x[a:b]` `x.f` `t.0` `x?` | |

Assignment (`=`, `op=`) is a statement, not an expression.

## Declarations (`declaration` in `parser.my`)

Top level only (no nested `fun`, `struct` … inside blocks). `pub` may precede `fun`, `async fun`, `struct`, `actor`, `enum`, `trait`, `typealias`, `const`, `import`, `from`; it is an error on `impl` and on methods (visibility follows the type).

```myla fragment
pub struct Point { x: int, y: int }          // commas between fields are REQUIRED (newline alone is an error); trailing comma ok
struct Pair<A, B> { a: A, b: B }             // type params, no bounds on struct/enum/trait/actor
actor Counter { n: int }                     // like a struct; methods in an impl
enum Shape {                                  // variant commas optional (newline is enough)
    Circle(Point, int)                        // tuple-like payloads only, no named fields
    Empty
}
trait Area { fun area(self) -> int }         // signatures only, no default bodies; no attributes in a trait
trait Zero { fun zero() -> Self }            // no `self`: a type's function, `int.zero()`
impl Area for Shape { fun area(self) -> int { return 0 } }
impl<T: Eq + Hash> Show for [T] { … }        // impl targets: named types, [T], [K: V], int…
impl<I: Iterator<T>, T> Iterator<T> for Wrap<I> { … }
typealias Grid = [[int]]                     // `typealias`, not `type`; no type parameters
const MAX: int = 10                          // the type is required
async fun work(c: Counter, k: int) -> int { … }
fun greet(name: str, greeting: str = "hi") -> str { … }   // defaults (D136); no named arguments at the call
fun big<T: Ord + Eq, U>(a: T, b: U,) -> T { … }           // bounds on fun/impl/method only; no `where`
fun f<T: json.ToJson>(x: T) { … }                         // a module's trait in a bound
```

- Parameters: `name: Type [= default]`; no `var x` parameters, no patterns. Methods: first is `self`, `var self`, or (trait functions) an ordinary parameter. Return type after `->`; none means `()`.
- Function types: `(int, str) -> bool`, `() -> ()`, `async (int) -> int`. Types: `int32`, `[T]`, `[K: V]`, `(A, B)`, `(A,)`, `()`, `Name<Args>`, `m.Type<Args>` (a module's type).

### Imports (`import_decl`)

| Form | Binds |
| --- | --- |
| `import std.task as task` | `task.f()`, `task.Channel<int>` |
| `import std.task` | only the full path `std.task.f()` (**not** `task`) |
| `from std.io import println, eprintln as ep,` | the names; trailing comma ok; all on one line, no `( … )` |
| `from .util import f` / `from ..lib.x import g` | relative to the file (`.` this directory, `..` its parent) |
| `pub import std.fmt as fmt`, `pub from .x import f` | re-exports; a `pub import` needs `as` |

A path segment may be a type keyword (`std.str`), an alias may not (`as str` is an error). Attributes can't stand on an import.

### Attributes (parser: `attributes`; checker: `check_attributes`, `check_method_attributes`, `validate_derive_attr`, `warning_names`)

Syntax `#name`, `#name(args)`, `#name[outputs]`, `#name(args)[outputs]`, one or more lines above the item (may also share its line). The parser takes any name; the checker accepts exactly:

| Attribute | On | Meaning |
| --- | --- | --- |
| `#test(args)[expected]` | non-generic functions; methods in an `impl` (receiver first) | a test case; `[panic("msg")]`, `[exit(n)]` expected failures; trailing `// name` labels it |
| `#test` (bare) | a function without parameters | a test function |
| `#main` | a non-generic function without parameters | the entry point (any name; `fun main()` needs none, `async fun main()` works without it too) |
| `#derive(Eq, Hash, Json, Toml)` | struct, enum (generic too) | only these four |
| `#allow(primitive, reentrancy)` | function, method, `impl` block | silence warnings (`primitive(__a, …)` for some primitives) |

Anything else (`#inline`, `#[test]`, `#deprecated`) is "unknown attribute".

## Statements (`statement` in `parser.my`)

| Form | Notes |
| --- | --- |
| `let x = e`, `var x: T = e` | `let` immutable, `var` mutable |
| `let (a, (b, _)) = e`, `var (x, y): (int, int) = e`, `let () = f()` | names, `_` and nested tuples only; `(x,)` for a 1-tuple; no struct destructuring (`let P { x } = p` is an error: `match`) |
| `let Some(v) = e else { return 0 }` | let-else (D137): `let` + a variant pattern (`V(…)`, `E.V…`, `.V…`, with `\|` alternatives); the else block must leave |
| `async let x = e`, `async let x: T = e` | child task; one name only |
| `if c { } else if c { } else { }` | no parentheses needed; `{ }` required |
| `if let P = e { } else { }` | |
| `while c { }`, `while let P = e { }` | no `loop`, no `do`, no labels |
| `for x in e { }`, `for (k, v) in e { }`, `for i in a..b { }` | `..` (half-open) only here, not in parentheses (`for i in (0..n)` errors) and not as a value; `a..b + 1` is `a..(b + 1)` |
| `return`, `return e`, `return a, b` | `return a, b` returns the tuple `(a, b)` |
| `become f(args)` | guaranteed tail call |
| `break`, `continue` | no labels, no value |
| `defer { … }` | `defer` stays an ordinary name elsewhere |
| `place = e`, `place op= e` | `op` ∈ `+ - * / % & \| ^ << >>`; place = a name or `self` followed by `.field` / `[index]`; **not** `t.0` (`t.0 = 5` is "invalid assignment target") |
| expression | calls, `match`, `if let` used for effect |

A block `{ … }` is not an expression (`let v = { 1 }` is an error).

## Expressions (`primary`, `postfix`)

| Form | Example | Notes |
| --- | --- | --- |
| Names, `self` | `x`, `self.n` | `int.zero()`, `int64.zero()`: a type's function |
| Call | `f(a, b,)` | trailing comma ok; no named args, no spread |
| Explicit type args | `f<int>(x)`, `m.f<str>()`, `xs.conv<str>(g)` | after a name or `.name` only, see below |
| Partial application | `f(_, 2)`, `f(1, _, _)` | `_` must be a whole argument, one per open position |
| Field, tuple index | `p.x`, `t.0` | `t.0.1` is a lex error (`0.1` is a float): write `(t.0).1` |
| Index, from end | `xs[i]`, `xs[^1]` | `^` only inside `[ ]` |
| Slice | `xs[1:3]`, `xs[:2]`, `xs[2:]`, `xs[::-1]`, `s[^2:]` | `a:b:step`; new values, clamped |
| Try | `opt?`, `res?` | postfix |
| Cast | `x as int64`, `c as uint8`, `97 as char` | **`x as int < 5` fails** (`int<` opens type arguments, `int` is a name); write `(x as int) < 5`; keyword types (`int32`) are fine |
| Unary | `-x`, `!b`, `~bits`, `await f()` | |
| Struct literal | `Point { x: 1, y: 2 }` | every field; no shorthand `P { x }`, no `..base`; the name must be a bare identifier: no `m.T { … }`, no `Box<int> { … }` (annotate the `let`) |
| Tuple, unit | `(1, "a")`, `(1,)`, `()` | |
| List, map | `[1, 2]`, `[]`, `["a": 1, "b": 2]`, `[:]` | |
| Lambda | `(x: int) => x + 1`, `(a, b) => { return a + b }`, `() => 7`, `async () => await g()` | parentheses always; no return-type annotation; a block body needs `return` |
| `if` value | `if c { 1 } else if d { 2 } else { 3 }` | `else` required; the block's last expression is the value |
| `match` | `match x { 1 \| 2 => "a", n if n > 9 => "b", _ => "c" }` | see below |
| Pipe | `x \|> f`, `x \|> f(y)`, `x \|> m.f(y)`, `x \|> xs.contains()` | inserts `x` as the first argument; it does **not** fill `_` (`10 \|> sub(_, 3)` is a type error) |
| Composition | `inc >> dbl` | |
| f-string | `f"{x}"` | |

```myla
fun sub(a: int, b: int) -> int { return a - b }

fun inc(x: int) -> int { return x + 1 }

fun main() {
    let t = ((1, 2), 3)
    let xs = [10, 20, 30, 40]
    let later = sub(_, 1)
    let h = inc >> inc
    print((t.0).1 + xs[^1] + xs[1:3].len() + later(5) + h(0) + (10 |> sub(4)))
    let v = if xs.len() > 3 { "long" } else { "short" }
    print(v)
}
// output:
// 56
// long
```

### Generic `<` (`postfix`, `explicit_type_args`, `type_args_then`)

After an identifier callee (`f`, `m.f`, `x.method`), `<` starts type arguments only if the tokens up to the matching `>` are type-like (names, type keywords, `, . : -> async ( ) [ ]`, nested `< >`), all on one line, within 128 tokens, and the `>` is immediately followed by `(`. Otherwise `<` is less-than. So `a < b > c` compares, `f(a < b, c > (d))` is ONE generic call `a<b, c>(d)` (write `c > d`), and in list/map/tuple elements and f-string holes a top-level comma ends the scan (`[a < b, c > (d)]` is two comparisons, so `[pair<int, str>(1, "a")]` doesn't parse: bind it with `let` first). `Box<int>.zero()` is an error: `Box.zero()`. In a type, `<` always opens arguments; `Option<int>= x` is fine (`>=` is split).

### `match` (`match_expr`, `match_arm`)

- `match scrutinee { arm, arm }`; arms separated by `,` or newline; after a `{ block }` arm nothing is needed. `;` is not a separator. At least one arm.
- Arm: `pattern [if guard] => expression` or `=> { statements }`. In a value `match`, the block's last expression (or trailing `if … else …`) is its value; in a statement `match` it isn't.
- Scrutinee and guard are parsed without struct literals: parenthesize them (`match (P { x: 1 })`).
- A guard **ending** in a parenthesized expression is read as a lambda: `n if (n > 1) =>` and `n if a && (b) =>` are parse errors; write `n if n > 1 =>`.

### Patterns (`pattern`, `base_pattern`)

| Pattern | Example |
| --- | --- |
| wildcard, binding | `_`, `n` |
| literal | `3`, `-1`, `'a'`, `"text"`, `true` (no floats, no ranges `1..5`, no `x @ p`) |
| variant | `E.V(a, b)`, `.V(a)`, `V(a)`, `E.Unit`, `.Unit`, `Unit` (no module path `m.E.V`) |
| tuple, unit | `(a, _)`, `(p,)`, `()` |
| struct | `Point { x, y: 0 }` (fields may be left out; no `..`) |
| or | `1 \| 2 \| 3`, `Some(0) \| None` |

A bare name that is a unit variant of the scrutinee's enum matches that variant; any other bare name binds, so a **misspelled unit variant becomes a catch-all** binding (the checker then usually reports the following arms unreachable).

## Things Rust and Swift programmers get wrong (front end)

- `fn`/`func`, `let mut`, `::`, `&`, `'a`, `loop`, labels, `..=`, `where`, `type X = …`, `impl` blocks with `pub fun`, `#[attr]`, `r"…"`, `"""…"""`, `\x41`, `///` docs, Allman braces, leading-dot method chains, `.V` to construct (patterns only), struct shorthand `P { x }`, named arguments, `import a.b` expecting `b` to be bound, nested functions, block expressions, `x++`.
- `str` and `bool` are keywords, `int`, `float` and `char` are not.
- Struct fields need commas; enum variants don't.
- `t.0.1` doesn't lex; `t.0 = v` isn't assignable.
- `x as int < y` needs parentheses.
