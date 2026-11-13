---
name: myla
description: Write, read, review and debug code in the Myla programming language (.my files) and work on its compilers. Myla looks like Rust and Swift but differs from both in many details, so use this before writing or changing any .my file (examples/, selfhost/, tools/, lib/std/, tests), before answering questions about Myla syntax or semantics, when looking up the standard library's API or the myla CLI, and when changing the Myla toolchain in selfhost/ or tools/ (adding a language feature, a builtin, a runtime primitive).
---

# Myla

Myla is a small, statically typed language with sized integers, value semantics, enums with `match`, traits and closures. It compiles to static x86-64 and aarch64 Linux binaries without libc and to WebAssembly modules for WASI (`--target`), and is self-hosted. **It is not Rust and not Swift**: code that looks right in either usually fails here.

What defines the language: the reference documentation, `docs/Language.md` and its subpages, and the decisions on `docs/Project/Decisions.md`. The implementation is the self-hosted toolchain in `selfhost/` (compiler, interpreter, CLI), bootstrapped from `bootstrap/seed.s`; its interpreter and its native code must agree. The grammar is `grammar/myla.ebnf` (mirrored in `docs/Language/Grammar.md`; the tree-sitter grammar in `editor/` is generated from it). The Python toolchain (`src/myla/`, `myla.py`) was removed in November 2026 (D101): ignore instructions that use `python3 myla.py`. A Rust prototype with another dialect existed until October 2026; its syntax is not Myla, so don't copy it from git history.

## Reference files

This page is the core. The files in `reference/` beside it were read from the code (November 2026, at 706eaec) and cite the functions to re-check:

| File | Look there for |
| --- | --- |
| [reference/syntax.md](reference/syntax.md) | keywords, tokens, literals, f-string specs, line continuation, the precedence table, every declaration, statement, expression and pattern form, attributes |
| [reference/builtins.md](reference/builtins.md) | builtin functions and methods, the prelude's traits, `#derive`, the type rules (literals, `as`, operators, map keys, generics, impls, closures, `?`, return paths, `match`), the module system, the checker's messages with their fixes |
| [reference/stdlib.md](reference/stdlib.md) | every module of `lib/std/`: its types, error types and signatures, what is `async`, gotchas |
| [reference/toolchain.md](reference/toolchain.md) | every `myla` command and flag, targets, exit codes and diagnostics, the test system, `myla.toml`, the REPL, environment variables, runtime error texts, scripts, CI, `tools/`, the repository's test conventions |
| [reference/compiler.md](reference/compiler.md) | the pipeline, each `selfhost/` file's role, the AST, checker and IR data structures, the runtime layers, bootstrap and seeds, and **the checklist for adding a language feature** (which files and functions, in which order, which tests) |

## A complete program

```myla
from std.io import println

struct Point {
    x: int,
    y: int,
}

enum Shape {
    Circle(Point, int),
    Rect(Point, Point),
}

impl Point {
    fun shifted(self, dx: int) -> Point {
        return Point { x: self.x + dx, y: self.y }
    }

    fun move_by(var self, dx: int) {
        self.x = self.x + dx
    }
}

#test(Shape.Rect(Point { x: 0, y: 0 }, Point { x: 2, y: 3 }))[6]
fun area(s: Shape) -> int {
    return match s {
        Circle(_, r) => 3 * r * r
        Rect(a, b) => (b.x - a.x) * (b.y - a.y)
    }
}

fun main() {
    var p = Point { x: 1, y: 2 }
    p.move_by(4)
    let shapes = [Shape.Circle(p, 2), Shape.Rect(p, p.shifted(3))]
    var total = 0
    for s in shapes {
        total += area(s)
    }
    let label = if total > 10 { "big" } else { "small" }
    println(f"total {total} is {label}")
}
// output:
// total 12 is big
```

## Rust and Swift habits that are wrong in Myla

| Don't write | Write | Why |
| --- | --- | --- |
| `fn f()`, `func f()` | `fun f()` | The keyword is `fun` |
| `let x = 1;` on every line | `let x = 1` | A newline ends a statement. `;` is optional (a trailing one is harmless) and separates statements or declarations on one line (`let a = 1; let b = 2`); never inside `( )`, `[ ]`, struct fields or match arms |
| `let mut x` | `var x = 1` | `let` is immutable (deeply), `var` mutable. Parameters are immutable and there are no `var` parameters: copy into a `var` first |
| `fun f() -> int { x + 1 }` | `{ return x + 1 }` | Function bodies need `return`; there is no implicit tail value. `return a, b` returns the tuple `(a, b)` |
| `c ? 1 : 2`, `let v = if c { 1 }`, `let v = { … }` | `let v = if c { 1 } else { 2 }` | `if` is an expression when used as a value, with a required `else` (D104); there are no block expressions and no `?:` |
| `x++`, `x--` | `x += 1`, `x -= 1` | Compound assignment exists (`+=` … `>>=`, D104), `++` doesn't |
| `E::A`, `.a` (Swift) to construct | `E.A`, `E.B(1)` | Variants are built with a dot; only `Some`/`None`/`Ok`/`Err` work bare. In patterns `B(x)`, `E.B(x)` and `.B(x)` all work, and a **misspelt unit variant in a pattern silently binds everything** |
| `Point::new()`, `static func` in an `impl P` | a free function `fun new_point() -> Point`, or a trait's function: `trait Zero { fun zero() -> Self }`, `impl Zero for int { fun zero() -> int { return 0 } }`, called `int.zero()`, `Money.zero()`, `T.zero()` | A type has no static methods of its own; a trait may declare functions without `self` (D172), called on a type or a type parameter bounded by the trait, not on a value. A generic type's is `Box.zero()` (its arguments from the expected type), not `Box<int>.zero()`. `Self` is valid only inside a `trait`: in an impl, name the type |
| `&self`, `&mut self`, `&x`, lifetimes | `self`, `var self`, plain values | No references or borrowing; everything is a value (copy-on-write under the hood) |
| `m.get(&k)`, `get(m, k)`, `m[k]` for a key that may be missing | `m.get(k)` (an `Option<V>`), `m.get_or(k, 0)`, `m.contains(k)` | `get`/`get_or` are `std.map`'s methods (implicit), `contains`/`keys`/`remove`/`len` the compiler's; `m[k]` of a missing key is a runtime error. The free `get(m, k)` went (MYLA-393) |
| `opt.unwrap()` | `opt.unwrap_or(0)`, `opt.expect("why")`, `match opt { Some(v) => v, None => 0 }`, `if let Some(v) = opt { … }`, `let Some(v) = opt else { return }` or `?` | no `unwrap`: `std.option` (implicit, D164) has `map`, `and_then`, `unwrap_or`, `expect`, …; `if let`/`while let` (D104) and let-else (D137) are sugar over `match` |
| `while let Some(x) = xs.pop()` | `while xs.len() > 0 { let x = xs.pop() … }` | `xs.pop()` returns the element (a `T`, not an `Option`) and an empty list is the runtime error `pop from an empty list` |
| `\|x\| x + 1`, `{ x in x + 1 }`, `x => x + 1` | `(x: int) => x + 1`, `(x) => { return x }`, `async () => await f(x)` | Lambda syntax: the parentheses are always needed, there is no return-type annotation; parameter types can be omitted only when a function type is expected |
| `Fn(i32) -> i32`, `(Int) -> Int` | `(int) -> int`, `async () -> int` | Function types |
| `println!("{}", x)`, `print("\(x)")`, `print(xs)` | `print(x)`, `print(f"x = {x}")`, `format("x = {}", x)` | `print` takes one integer, float, `char`, `bool`, `str` or a type with `impl Format` (`fun format(self, spec: str) -> str`); **lists, tuples, maps, `Option` and `Result` can't be printed or put in a hole**: build the text. A spec is `[[fill]align][+][#][0][width][.prec][x\|X\|b\|o]` (`{x:>8.2}`, `{n:#06x}`, D139): no `{:?}`, `{0}`, `{name}`, `e` |
| `0..=n`, `let r = 0..n`, `loop { }`, labelled breaks | `0..n + 1` in a `for` head, `while true { }` | Ranges are half-open and only exist in `for` heads; no `loop`, no labels |
| `255_u8` | `255u8` | `_` only between digits |
| `i32`, `u8`, `f64`, `Int`, `Double` as types | `int32`, `uint8`, `float64` (or `float`), `int` | Type names are spelled out; suffixes are short (`5i64`, `2f64`) |
| `#[derive(PartialEq, Hash)]`, `#[test]`, `#[derive(PartialOrd)]` | `#derive(Eq, Hash)`, `#test(args)[expected]`; `impl Ord for P { fun cmp(self, other: P) -> int { … } }` | The only attributes are `#test`, `#main`, `#derive(Eq\|Hash\|Json\|Toml)` and `#allow(primitive\|reentrancy)`; `Ord` is never derived |
| `#[derive(Serialize, Deserialize)]`, `serde_json::from_str::<P>(s)`, `Codable` | `#derive(Json)` with `import std.json as json`, then `json.encode(p)`, `json.decode<P>(s)` (a `Result<P, json.JsonError>`); `#derive(Toml)` with `import std.toml as toml`, `toml.encode(p)` (a `Result`), `toml.decode<P>(s)` | std.json's `ToJson`/`FromJson` (D172), std.toml's `ToToml`/`FromToml`; no field attributes or renames; `Option` fields absent when `None`; enums `"Red"`, `{"Dot": x}`, `{"Line": [a, b]}`; no tuple fields; maps need `str` keys |
| `mod x;`, `use a::b;`, `import Foundation`, `from m import (a, b)` | `from .x import f`, `import a.b as b`, `from std.io import println, eprintln` | Python-like imports on one line, `pub` exports. **`import std.task` without `as` binds only the full path** `std.task.f()`, not `task` |
| `args::Spec`, a second `from std.args import Spec` just for a type | `import std.args as args`, then `fun cli() -> args.Spec`, `[deque.Deque<int>]` | In a type, `m.T` is the module's exported type (D170), and in a bound `T: m.Trait` its trait (MYLA-398); in an expression `m.f(x)` and `m.E.V`, but not `m.T { … }` (struct literals and struct patterns need `from … import`; an enum pattern takes the bare variant) |
| `impl Add for P { type Output … fn add(self, o: P) -> P }`, `impl Mul<f32> for V { type Output = V; … }` | `impl Add for P { fun add(self, other: P) -> P { … } }`, `impl Mul<float> for V { fun mul(self, k: float) -> V { … } }`, `impl Mul<V, float> for V` (result `float`), `impl Mul<V, V> for float64` (`2.0 * v`) | Operator traits take the right operand's and the result's types as arguments, `Mul<R, O>` (D198): a bare `Mul` is `Mul<Self, Self>`, `Mul<R>` is `Mul<R, Self>`; one impl per right operand's type. `Neg` gives unary `-`, `Index<I, O>` `x[i]`, `IndexSet<I, V>` `x[i] = v`. `v * 2` with only `Mul<float>` is an error (write `2.0`). `Eq`/`Ord` stay same-type (`Ord` is `cmp(self, other: Self) -> int`). They give operators, not methods: `a.eq(b)` on a `T: Eq` is an error, write `a == b`, and a method beside others of its trait is named by its right operand (`mul$float64`), so `v.mul(2.0)` doesn't exist |
| trait default method bodies, `where` clauses | signatures only; bounds inline (`fun f<T: Ord + Eq>`) | `trait T { fun m(self) -> int }`. A trait has no default bodies, defaults or async methods |
| `impl Iterator for C { type Item = int; fn next(&mut self) -> Option<i32> }`, `I: Iterator<Item = T>` | `impl Iterator<int> for C { fun next(var self) -> Option<int> { … } }`, `I: Iterator<T>` | The prelude's `Iterator<T>` is a generic trait (D171); a bound names it with its arguments, and the type's one impl fixes `T` (D55) |
| `f::<int>(x)` | `f<int>(x)`, `deque.new<str>()`, `xs.mapped<str>(g)`, or annotate: `let y: Box<int> = …` | No turbofish: type arguments go right after the name (D169); a method's name only its own type parameters. A `<` after a name is a call's only if the `>` is followed by `(`, so `f(a < b, c > (d))` is one generic call: write `f(a < b, c > d)`. In a list, map or tuple literal and an f-string's holes a comma ends the type arguments (D186): `[a < b, c > (d)]` is two comparisons, and `[pair<int, str>(1, "a")]` needs a `let`. `x as int < 5` is a parse error: `(x as int) < 5` |
| `x as f64` from `bool`/`str` | only numeric ↔ numeric and `char` ↔ integer | `as` |
| `1.5 * 2`, `let x: float = 2` | `1.5 * 2.0`, `let x: float = 2.0` | An integer literal never becomes a float |
| `s.is_empty()`, `xs.min()`, `x.sqrt()` on a `bool` | `s.len() == 0`, `xs.iter() \|> iter.min()`, `xs.min_by(less)` | there is no `is_empty`, `first`, `min` or `max` on lists, and `bool` has no methods. Floats do (D197, implicit `std.float`): `x.sqrt()`, `x.abs()`, `x.floor()`, `y.atan2(x)`, `x.powi(3)`, `a.lerp(b, t)`, `x.total_cmp(y)`; constants and `float.nan()` after `import std.float as float` |
| a line that starts with an operator (`\n    + b`, `\n    .map(f)`) | end the line with the operator (`a +`), or wrap the expression in `( )` | A statement goes on after a binary operator that ends a line and inside `( )`/`[ ]` (D104), not after `=`, `,`, `=>`, `->`, `.` or `as`. A line that starts with an operator is a new statement: **`let x = 1⏎ - 2` silently leaves `x == 1`** |
| `fun f()⏎{` (Allman), nested `fun`, `type X = …` | `{` on the same line; functions at the top level; `typealias X = …` | `else` may start the next line. `typealias` takes no type parameters |
| `struct P { x: int⏎ y: int }` | `struct P { x: int, y: int }` | Struct fields need commas (a trailing one is fine); enum variants don't |
| `for (k, v) in m` | `for (k, v) in m.items()` | A loop over a map visits its keys |

## Types and conversions

- `int` = `int32`, `float` = `float64`, and unsuffixed float literals default to `float64` (D102); for single precision write `0.1f32` or annotate `let x: float32 = 0.1`.
- Integers: `int8`…`int64`, `uint8`…`uint64`. Overflow (`+ - *`, unary `-`, `MIN / -1`) is the runtime error `integer overflow` under `myla run`, `myla test` and `myla build --checked`, and wraps only in a plain `myla build` (D175); a shift count past the width is `shift amount out of range` there. To wrap on purpose (hashes, RNGs) write `h.wrapping_mul(k)`, `a.wrapping_add(b)`, `wrapping_sub`, `x.wrapping_neg()` (builtin methods, one instruction natively); `std.int` has `checked_*`, `saturating_*`, `overflowing_*`; `x.pow(e)` takes a `uint32` exponent (`2.pow(n as uint32)`), and `-5.abs()` is `-(5.abs())`. Also `bool`, `char` (Unicode scalar), `str` (immutable UTF-8 bytes), `StringBuilder`, tuples `(int, str)` (1-tuple `(int,)`), the unit type `()` with its one value `()` (D138), lists `[T]`, maps `[K: V]` (keys: any `Eq + Hash` type, D163: integers, `char`, `bool`, `str`, tuples, lists, `Option` and `Result` of such, `#derive(Eq, Hash)` structs and enums; floats too, D196: `-0.0` and `0.0` one key, a NaN key the runtime error `cannot hash NaN`), function types, structs, enums, generics, `typealias Name = T`.
- **No implicit conversion at all.** A literal adapts to its context (`let b: uint8 = 200`, `x + 1` and `1 + x` with `x: int64`, `[1, 2, big]` is `[int64]`), but a *variable* has a fixed type: `let n = 2` is an `int32`, so `big + n` with `big: int64` fails. Annotate (`let n: int64 = 2`) or cast (`n as int64`). In a generic call the first argument fixes `T`: `max_of(big, 1)` works, `max_of(1, big)` doesn't (`max_of<int64>(1, big)` does).
- `s[i]` is a byte (`uint8`); `s.len()` counts bytes; `s.chars()` gives `[char]`, and `for c in s` visits the same `char`s without making the list (D165); `'a'` is a `char` but fits an integer type when one is expected (`s[i] == 'a'`, `s[i] - 'a'`, and `'a' + n` with `n: int64` is an `int64`). `+` concatenates strings; `<` `<=` `>` `>=` order them byte-wise, and `str` is `Ord` (`xs.sort()` on `[str]`). Slices: `xs[1:3]`, `xs[:2]`, `xs[::-1]`, `s[7:]` (new values, bounds clamped); `xs[^1]` is the last element, `^` counts from the end (D142); a negative index is an error. Tuple fields: `t.0`; `t.0.1` doesn't lex (write `(t.0).1`) and `t.0 = v` isn't assignable.
- Strings are one line: no raw strings, no multi-line strings, no `\x`. Escapes are the same in chars, strings and f-strings: `\n \t \r \0 \\ \" \'` and `\u{1F600}`. Identifiers may use letters of any script (`größe`, `π`): Unicode XID, not normalized (D72). `str` and `bool` are keywords (`let str = 1` is an error); `int`, `float`, `char` and `type` are ordinary names.
- `==` works on integers, floats, `char`, `bool`, `str`, `()`, structs/enums with `Eq` (`#derive(Eq)` or `impl Eq`), `Option`/`Result` of `Eq` payloads (`m.get(k) == Some(3)`, `opt == None`, MYLA-379; of `Hash` payloads they are map keys too, D182), and tuples and lists of `Eq` elements (D163). Maps and functions are not comparable. Ordering (`<` …) works only on numbers, `char`, `str` and `Ord` types: not `bool`, tuples or lists. `#derive` works on generic types too: `#derive(Eq, Hash) struct Pair<A, B>` gives `impl<A: Eq, B: Eq> Eq for Pair<A, B>`, so `Pair<int, str>` has `==` and is a map key. `#derive(Hash)` needs `Eq` derived too.
- `char` arithmetic (D165): `c - d` is an `int32` (`'p' - 'a' == 15`); `c + n` and `c - n` with `n: int32` are a `char` (a runtime error if not a Unicode scalar); the char goes on the left, a char variable with another integer type needs `as int32`, two chars don't add.
- `Hash` (D163) is the prelude's `trait Hash { fun hash(self, h: Hasher) -> Hasher }`: `#derive(Eq, Hash)` on a struct or enum, or `impl Hash for P { fun hash(self, h: Hasher) -> Hasher { return h.add(self.x).add(self.name) } }` (std.hash, implicit, has `h.add(x)` for any `Hash` value and `add_u64`, `add_str`, …, `finish()`). Floats are `Hash` (D196; a NaN's hash is a runtime error). A generic map key needs `K: Eq + Hash`.
- Constants: `const MAX: int = 10` (the type is required; scalars and `str` only, from literals, other constants and operators); no global variables.

## Syntax notes

- Struct literal `Point { x: 1, y: 2 }` (every field, no `P { x }` shorthand, no `..base`, the name a bare identifier: `Box<int> { … }` and `m.T { … }` don't parse); in `if`/`while`/`for`/`match` heads and in match guards wrap it in parentheses.
- `match`: arms `pattern [if guard] => expr` or `=> { …; last_expression }`, one per line or comma-separated. Patterns: `_`, bindings, literals (integers, `-1`, `char`, `str`, `bool`; no floats, ranges or `x @ p`), `Variant(a, b)`, `E.Variant`, `.Variant`, tuples, `()`, `Point { x, y: 0 }` (fields may be left out), `a | b`. Matches must be exhaustive, nested patterns included: `Some(Ok(v))`, `Some(Err(e))` and `None` cover an `Option<Result<…>>` without a `_` arm; integers, `char` and `str` need a `_`. A redundant arm is an error. A guard that ends in a parenthesized expression (`n if (n > 1) =>`) is read as a lambda: drop the parentheses.
- A function that returns a value must end every path with `return`, `become`, `panic(…)`, `unreachable()` or `std.process.exit(n)`, or with an `if … else` or a `match` statement whose every branch does; loops never count, so put `unreachable()` after a loop that always returns.
- `?` works on `Option`/`Result` when the function returns the same kind (same error type: there is no conversion). Inside a lambda it returns from the lambda, so the lambda's result type must be known: pass it where a function type is expected or annotate the variable (`let f: (int) -> Option<int> = (x: int) => …`). Not in a `defer` or an `async let` initializer.
- Default parameter values (D136): `fun greet(name: str, punct: str = "!")`, trailing parameters only, not on a trait's methods nor on a parameter whose type mentions a type parameter; there are no named arguments.
- Built-in types take impls too: `impl int { … }` (`int32` only), `impl [int] { … }`, `impl<T> [T] { … }`, `impl<K: Eq + Hash, V> [K: V] { … }` (a map impl needs the key bound even if it never hashes). All of a list's impls share one method table, and so do a map's: `impl [int] { fun total }` and `impl [str] { fun total }` are duplicates. Tuples and function types take no impls. A `var self` method on one writes the caller's place, by `self.push(x)` or by assigning `self = self + 1` (D144; only there and in an enum's `var self` method, `self = E.B(n)`, may `self` be assigned, a struct's `var self` method changes fields). A program can't define a method that a builtin (`len`, `push`, …) or an implicit module already has on that type, nor a top-level function named like a builtin (`cannot redefine builtin 'build'`).
- A method may share a field's name (MYLA-406): `c.keys` is the field, `c.keys()` the method; not a field that holds a function, which `h.on(x)` calls (a generic field that holds one beside a method of its name: `let g = c.get`, then `g(5)`, D178). There are no method values: `c.keys` without `()` is always the field. Generic functions are no values either.
- `x |> f(y)` is `f(x, y)` (the loosest operator, below `||`; it doesn't fill a `_`); `f >> g` composes; `f(_, 2)` is partial application (not of generic or async functions). Bitwise operators bind tighter than comparisons (`a & m == 0` is `(a & m) == 0`), `as` tighter than `*`. Full table: [reference/syntax.md](reference/syntax.md).
- Closures capture by value; captured variables can't be changed inside.
- `pub` goes on top-level declarations (`fun`, `struct`, `enum`, `trait`, `actor`, `const`, `typealias`, `import … as`, `from … import`), not on methods, fields or `impl`.
- Generic bounds: `fun sum<T: Add>(…)`, `fun lerp<T: Add + Mul<float>>(a: T, b: T, t: float) -> T` (operators with their arguments, D198; a number meets its own operators' bounds, a list its indexing's), `fun total<I: Iterator<int>>(it: I)`, `impl<I: Iterator<T>, T, U> Iterator<U> for Map<I, T, U>`; a bound allows an operator trait's operators, a user trait's (or `Format`'s) methods on `T` and its functions without `self` on `T` itself (`T.zero()`, D172), a generic trait's with its arguments (`it.next()` is an `Option<T>`). A type parameter only a bound names (`fun count<I: Iterator<T>, T>(it: I) -> int`) is fixed by the argument's impl. A generic trait in a bound needs its arguments (`I: Iterator` is an error). Bounds go on functions, methods and impls, never on a struct, enum, trait or actor declaration.
- `for` takes a name or a tuple of names: `for (k, v) in m.items()`, `for (i, x) in xs.iter() |> iter.enumerate()`, `for ((a, b), _) in ps` (each element destructured as `let (k, v) = kv` does, MYLA-390); no other pattern (`for Some(x) in` is an error: use `while let`). `let` destructures tuples only (`let (a, _) = t`); a struct goes through `match`.
- Iterators (D171): a type with `impl Iterator<T> for It { fun next(var self) -> Option<T> }` (the prelude's trait) can be looped over, `for x in it { … }`, which is `var c = it; while let Some(x) = c.next() { … }`: the loop works on a copy, and a copy of an iterator keeps its own position. A `next` method without the impl isn't enough. There are no trait default bodies, so `it.map(f)` doesn't exist: `std.iter`'s functions take the iterator first and chain with `|>`, `xs.iter() |> iter.map((x) => x * 3) |> iter.filter((x) => x % 2 == 0) |> iter.sum(0)` (`xs.iter()` is `std.list`'s, `m.iter()` `std.map`'s; sources `iter.range(a, b)`, `iter.repeat(v)`, `iter.from_fn(state, step)`; adapters `map`, `filter`, `take`, `skip`, `take_while`, `skip_while`, `enumerate`, `zip`, `chain`, `flat_map`; consumers `to_list`, `count`, `sum(zero)`, `fold`, `any`, `all`, `find`, `min`, `max`). The list methods stay eager.
- Entry point: `fun main()` without parameters, or any parameterless non-generic function marked `#main`; `async fun main()` works with or without `#main`. `std.process.args()` and `std.process.exit(code)`.
- Part of a string: `var sb = StringBuilder()` (or `StringBuilder(n)`, room for `n` bytes), `sb.append(s, start, end)` (byte offsets, must lie within `s`), `sb.build()`; or a slice, `s[start:end]` (bytes; a bound strictly inside a well-formed character is a runtime error, one beside bytes that are no character isn't, D174).
- `defer { … }` runs its block when the enclosing block ends, the last one met first: at its end, `return` (after the value), `?`, `break`, `continue`, before a `become`'s call; not on a failure (D135). It can't `return`, `?`, `await` or `break` out of itself, and sees the names declared before it.
- `become f(args)` is a guaranteed tail call: it ends the function like `return f(args)`, but the stack doesn't grow (D87). The call must be a function, a method or a function value that's a parameter (not a builtin, a variant or a partial application), and must not be followed by `?`. Past six argument words (a struct handed over counts a word per field), it can't pass more than its function received (D119). The interpreter stops at 2,500 nested calls (`runtime error: stack overflow`) where native code goes far deeper: deep recursion that must also run under `myla run`/`myla test` needs `become` or a loop.

## The standard library

Full API: [reference/stdlib.md](reference/stdlib.md); prose: `docs/Language/Standard-library.md`, one page per module.

- The method modules `std.str`, `std.char`, `std.int`, `std.float` (D197), `std.list`, `std.option`, `std.map` and `std.hash` are in every program without an import (D164, MYLA-320): their methods on the built-in types work anywhere. They bind **no names**: their `pub` functions and types need an import (`import std.list as list`, then `list.filled(3, 0)`; `from std.list import ListIter`; without it `ListIter<int>` is the misleading `type 'ListIter' is not generic`). A path segment may be `str`, an alias can't. The modules of `std` don't get them: there, import what you use. The compiler's own methods are `len`, `push`, `pop`, `contains`/`keys`/`remove` on maps, `chars`, the `StringBuilder`'s and `wrapping_*` (D103: `push(xs, v)` is an error naming the method, MYLA-221; a mutating one needs a `var` place).
- Its conventions (D164): operations on built-in types are methods (`s.split(",")`, `xs.sorted()`), the rest functions of their module; strings are bytes (positions are byte offsets; `trim`, `words` and the case methods are ASCII only); a fallible function returns a `Result` with its module's error type, a struct with a `kind` enum and a position (`JsonError`, `TomlError`, `RegexError`, `CsvError`, …) or a bare enum (`HttpError`, `ChannelError`, …), all with `e.message()` and `f"{e}"`. Generic constructors need their type from outside: `var s: set.Set<str> = set.new()` or `set.new<str>()`. In a `match` on a module's enum write the bare variant (`Syntax => …`), not `json.JsonErrorKind.Syntax`.
- `IoError` is exported by `std.fs` and `std.ioerror` (not `std.io`) and is **not `Eq`**: `match` it (`Err(NotFound) => …`) instead of comparing; `f"{e}"` is `not found (NotFound)` (`e.message()`, D173).
- Input: `var r = stdin()` (from `std.io`), then `r.read_line()` (`Result<Option<str>, IoError>`, without the `"\n"` but keeping a `"\r"`), `r.read_exact(n)`, `r.read_to_end()`. A reader is a value, so a helper function can't read from one it was passed: keep it in a struct field and read in `var self` methods.
- Files (`std.fs`): `read_to_string(path)`, `read_bytes`, `write_to_file(path, s)`, `write_bytes`, `list_dir(path)` (sorted, without `.`/`..`), `make_dir`, `make_dir_all`, `remove_file`, `remove_dir`, `remove_dir_all`, `rename(from, to)` (these and `write_to_file` give `Result<(), IoError>`: match `Ok(())`), `exists`, `is_dir`, `is_file`, `is_symlink`, `current_dir()`, `metadata`/`symlink_metadata`, `make_temp_dir()`, `make_temp_file()` (a `Result<(str, File), IoError>`: path and open file). Streams: `fs.open(path)`, `fs.create(path)`, `fs.open_append(path)` or `fs.options().write(true).create_new(true).open(path)` give a `File` (`Read`, `Write`, `Seek` of `std.io`; close it yourself, `defer { let c = f.close() }`). `Read`'s `read(n)` and `Write`'s `write(b)` take and give `[uint8]` only (D177): text through `io.buffered(f)` (`read_line()`, `read_to_end()`) and `io.buffered_writer(f)` (`write_str(s)`, then `flush()`: it isn't flushed at exit), `f.write(s.bytes())`, or `bytes.from_str(s)`/`bytes.to_str(b)` from `std.bytes`.
- Processes (`std.process`): `process.command(p).arg(a).output()` gives an `Output` whose `stdout`/`stderr` are `[uint8]` (`bytes.to_str(out.stdout)`; a nonzero exit is still `Ok`); `.spawn()` gives a `Child` (`take_stdin()`, `take_stdout()`, `wait()`, `kill()`; in a task, feed its input with `await w.write_async(b)` and use the `*_async` twins); `.stdout_from(Stdio.Null)`, `.stderr_from(Stdio.Inherit)`, `.stdin_from_stdout(out)` (another child's output, straight).
- Numbers and text: `num.parse_int(s)` is an `Option<int64>`; `num.parse_int32`, `parse_int_radix`, `parse_uint64` give a `Result<_, ParseIntError>`; `num.parse_float`; `num.format_float(1.0)` is `"1.0"` where `print` writes `1`. `text.scanner(s)`, `text.ints(line)` (a `Result<[int], ScanError>`), `text.wrap`. `random.seeded(n: uint64)`, then `var r` and `r.int_in(lo, hi)` (`hi` left out). Float functions are methods (`std.float`, implicit); `std.math` has them as functions. No `time.sleep`: `await task.sleep(ms)`.
- `std.test`: `expect(cond)`, `expect_eq(got, want)` and `expect_ne` (both need `T: Eq + Format`, so not lists, tuples or `Option`s: compare with `==` and `expect`), `fail(msg)`, `temp_dir()`, `temp_file()`, `program()` (a project's built program).
- Also: `std.json` (`parse`, `to_string`, `pretty`, `field`, `at`, `encode`, `decode<T>` with `#derive(Json)`; a bound names its trait by the module, `T: json.ToJson`, or imported), `std.toml` (TOML 1.0: `parse`, `parse_doc`, `to_string`; `encode`, a `Result` as a document must be a table, and `decode<T>` with `#derive(Toml)`, where an `Option` may only be a struct's field), `std.yaml`, `std.xml`, `std.csv`, `std.ini`, `std.http` (plain HTTP/1.1 client and server: `http.get(url)`, `await http.serve(addr, handler)`), `std.net` (TCP, UDP, `net.lookup(name)`), `std.regex`, `std.compress`, `std.archive`, `std.digest`, `std.checksum`, `std.encoding`, `std.url`, `std.uuid`, `std.task`, `std.time`, `std.term`, `std.signal`, `std.log`, `std.args`, `std.glob`, `std.path`, `std.text`, `std.grid`, `std.graph` (`bfs`, `dijkstra`, `astar`, `topo_sort`, … over a neighbour function; weights `int64`), `std.set`, `std.deque`, `std.heap`, `std.btree`, `std.bitset`, `std.unionfind`, `std.cache` (`Lru<K, V>`: `var c`, `c.get(k)`, `c.put(k, v)` giving the evicted entry; `Memo<K, V>`, `cache.recursive(step)` for a recursion: a closure can't call the memo it is in), `std.random`, `std.bigint` (no unary `-`: `.neg()`), `std.bench` (`bench.run(name, () => work()).line()`, `run_n`, `run_for`, `black_box`). `from std.platform import TARGET` names the target; the rest of `std.platform` and `std.rt` is the runtime's.

## Concurrency (D89 to D97, `docs/Language/Concurrency.md`)

```myla
import std.task as task

actor Counter {
    n: int,
}

impl Counter {
    fun add(var self, k: int) -> int {
        self.n = self.n + k
        return self.n
    }
}

async fun work(c: Counter, k: int) -> int {
    return await c.add(k)
}

#main
async fun main() {
    let c = Counter { n: 0 }
    async let a = work(c, 1)
    async let b = work(c, 2)
    let first = await a
    let second = await b
    // `first` and `second` depend on which task ran first; the total doesn't
    print(await c.add(0))
}
// output:
// 3
```

- `async fun` can suspend; a call of it, or of an actor's method from outside, must be awaited (`await f(x)`), and only in async code. The entry point is `async fun main()` (with or without `#main`). Async function values: `async () => await f(x)`, of type `async () -> T` (`task.all`, `pool`, `first`, `timeout` take them; a named `async fun` fits too).
- `async let x = e` starts a child task (one name, no pattern); read it once with `await x`. A scope waits for its children. Only async functions have them, and a lambda can't `await` or `task.cancel` them.
- An actor's state is reached only through `self` in its own methods; one method runs at a time, but an `await` inside an async method lets other calls in (a warning flags a field checked before an `await` and changed after it, D95; `#allow(reentrancy)` silences it). An actor can't implement a trait.
- An actor may be generic (MYLA-386): `actor Cell<T> { value: T }` with `impl<T> Cell<T> { … }`, a bound on an impl of its own (`impl<T: Add> Cell<T>`, never on the declaration); made like a generic struct (`Cell { value: 0 }`, or `let c: Cell<str> = …` when the fields don't fix `T`) and named with its arguments (`Cell<int>`, `fun make<T>() -> Cell<T>`).
- Values cross between tasks and actors as deep copies, and captures can't be changed (D93). What is shared: actors, and handles whose copies reach the same thing (`task.Notifier`, `task.Channel`, sockets such as `net.TcpStream`, `http.Client`).
- `std.task`: `await task.all(fs)` runs a list of `async () -> T` functions as children; `await task.sleep(ms)`; `await task.timeout(ms, f)` (an `Option<T>`); `task.cancel(a)` asks the child `a` to stop and `task.cancelled()` is how a task checks (cooperative, D96); `await task.yield()` gives the other tasks a turn (a long loop's way to let a failure elsewhere end the program).
- Channels (MYLA-351): `let ch: task.Channel<int> = task.channel(4)` (bounded; `0` a rendezvous; `task.unbounded()`; or `task.channel<int>(4)`), any element type; all methods async: `await ch.send(x)` (`Result<(), task.ChannelError>`: `Err(Closed)` after `close`, `Err(Cancelled)`), `await ch.recv()` (`Option<T>`: `None` once closed and drained, or cancelled), `try_send`, `try_recv`, `send_timeout(x, ms)`, `recv_timeout(ms)` (`Err(TimedOut)`), `close()`, `len()`; `ChannelError` is `Closed | Full | Empty | TimedOut | Cancelled`. Waits park (no polling); a sender that gives up takes its value back. `await task.pool(n, jobs, f)` (results in job order), `await task.workers(n, jobs_ch, results_ch, f)` (as they finish; gives the count sent and closes `results_ch`), `await task.first(fs)` (`Option<(int, T)>`, the rest cancelled). No program-declared actor needed.
- Waiting for another task without spinning (MYLA-387): `let n = task.notifier()` (a handle: copies reach the same notifier, an actor may keep them in its fields); `await n.wait()` parks until `n.notify_one()` (wakes the longest waiter, or leaves a counted permit so a wake before the wait isn't lost) or `n.notify_all()` (wakes those waiting now, no permit: take `let l = n.listen()` before looking at the condition, then `await l.wait()`); `await n.wait_timeout(ms)`; each gives `false` when not woken (time passed, the task was cancelled, or the notifier is closed). Wait in a loop that looks again. `n.close()` frees it (D181), waking its waiters with `false`; a wait on a closed notifier returns `false` at once (D195). Every task waiting with nobody to wake one: "every task waits for another one", exit 1.
- A failure (panic, runtime error, `exit`) in any task ends the program at once: the others stop at their next `await` (D97).
- Native code runs tasks in parallel on `MYLA_THREADS` workers (default one per CPU, at most 32; `build/myla build`, D92); the interpreter (`build/myla run`) runs them one at a time: a child starts when its parent suspends, the newest ready task first (`MYLA_SCHED=fifo` or `seed:N` and `MYLA_TIME=virtual` change that under `myla run`, not under `myla test`).

## Working in this repository

Details: [reference/toolchain.md](reference/toolchain.md) (commands, tests, scripts) and [reference/compiler.md](reference/compiler.md) (internals, adding a feature).

- The CLI is `build/myla`; if it is missing, run `scripts/bootstrap.sh` first (it needs only `as` and `ld`, under 20 seconds). Run: `build/myla run file.my`, test: `build/myla test file.my`, compile: `build/myla build file.my -o out` (`-g` for gdb, `--checked` for overflow checks, `--target aarch64-linux|wasm32-wasi`), type-check: `build/myla check file.my` (prints `ok`), interactive: `build/myla repl` (no `:commands`; it can't declare an `actor` or `async fun`). Without a `.my` argument the commands work on the project around the working directory (its `myla.toml`): `build`, `run`, `test`, `check`, and `new`, `fetch`, `clean` (D73).
- Diagnostics are Rust-style, `type error: <message>`, then `  --> file:line:col`, the line and carets; exit status 1 for any error or failed test, 2 for a usage error, `n` for the program's `exit(n)`.
- The standard library is in `lib/std/`, and the tools carry it (`selfhost/embedded_std.my`, the library's text and each std module's parse, regenerated by `scripts/bootstrap.sh`; `--stdlib lib` or `MYLA_STDLIB=$PWD/lib` uses your changes before the next bootstrap). A std function's body is checked only when something calls it (D179): check a module you changed whole with `build/myla test lib/std/<m>.my --stdlib lib`.
- The tests are Python unittests in `tests/burn/` (`python3 -m unittest tests.burn.test_<name>` for one; `scripts/test.sh fast`, or `scripts/test.sh` for all). They build their own tools from the seed into `build/test-tools/` and pass `--stdlib lib`, so they see the working tree without a bootstrap.
- `#test` cases go above a function, or above a method inside its `impl` with the receiver as the first argument (`#test(Counter { n: 2 }, 3)[5]`, D116); the arguments are constants and literals. A trailing comment names a case: `#test(1, 2)[3] // small numbers` reports `PASS  add #1 (small numbers)` (MYLA-239). A bare `#test` on a function without parameters (no result, or `Result<(), E>`) is a test function (D162): it passes when it returns, fails on a runtime error, `exit` or `Err(e)`. `[panic("message")]` (the whole message) and `[exit(n)]` are expected values. No cases on generic functions or on actor and async methods; `#test` on an `async fun` runs the case as the entry task. Under `myla test` a failed case runs its deferred blocks; `--only <text>` selects the cases whose function name contains the text (not the label), `--list` names them; a case's output is shown only when it fails. In a project `myla test` also runs `tests/`: test programs (a file with a trailing `// output:` block, optionally `// input:`, `// exit: n`, `// stderr:` (a prefix)) and test files, with `test.program()` the built program. `--native` or `--target <t>` runs the cases natively through a generated harness (`selfhost/harness.my`); a failed case runs no deferred block there; `--target wasm32-wasi` needs `MYLA_EMULATOR="node tools/wasm/run.mjs"`.
- Every value-returning function in `examples/` needs `#test(args)[expected]` cases (a burn test enforces it); add them to new functions in `selfhost/` too: the target there is at least 80 % of value-returning functions (D109).
- New examples must be registered in `tests/burn/test_examples_run.py` (`EXPECTED`) and `tests/burn/test_examples_compile.py` (`EXAMPLES`); programs that must be rejected go to `examples/errors/` with a line `//~ <lex|parse|module|type|runtime> error: <message substring>`, usually a pinned `<name>.stderr` beside it (`MYLA_PIN_DIAGNOSTICS=1` writes it), and for runtime errors `//~ native: runtime error: …` (more directives in [reference/toolchain.md](reference/toolchain.md)).
- A ```` ```myla ```` block in `docs/`, the README or this skill (both copies) is a tested program (`tests/burn/test_doc_blocks.py`): it must check and, with a `main`, run with exit 0 in an empty directory and print the same natively; it may end with `// output:` and one `// ` line per printed line. Mark pieces ```` ```myla fragment ```` and deliberately wrong code ```` ```myla error ```` (D114). The skill's two copies, `.claude/skills/myla/` and `.agents/skills/myla/`, must be identical, `reference/` included.
- The interpreter and the native backend must print the same output (except D175's overflow, and the interpreter's call depth); check both (`run` and `build` + execute) after changing either.
- Changes to `selfhost/` must keep the bootstrap fixed point: `scripts/bootstrap.sh` (stage 2 and stage 3 must emit the same assembly). A pull request that changes `selfhost/` or `lib/std/` ends with a new seed (D156, one per pull request): `scripts/update-seed.sh`, then commit `bootstrap/seed.s`, `bootstrap/seed-aarch64.s` and `selfhost/embedded_std.my` (CI fails on a stale one at the pull request's tip). The seed compiles the compiler and the std modules it imports, so new syntax, a new builtin method, primitive or runtime variable can't be *used* there until a seed knows it: implement it, stage a seed in a commit of its own, then use it ([reference/compiler.md](reference/compiler.md), "Bootstrap and seeds").
- New keywords must be soft (an identifier the parser recognizes in place, as `defer` is: `@soft` in the EBNF), because `tokens.keywords()` is pinned by `test_grammar`. The compiler's debugging flags (`--emit-ir`, `--ssa`, `--no-inline`) are on `build/stage3 file.my lib`, not on `myla build`.
- Before trusting a construct you're unsure of, write a five-line program and run `build/myla check` on it: the checker's messages are precise.
