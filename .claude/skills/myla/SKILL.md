---
name: myla
description: Write, read, review and debug code in the Myla programming language (.my files) and work on its compilers. Myla looks like Rust and Swift but differs from both in many details, so use this before writing or changing any .my file (examples/, selfhost/, src/myla/std/, tests), before answering questions about Myla syntax or semantics, and when changing the Myla toolchains in src/myla/ or selfhost/.
---

# Myla

Myla is a small, statically typed language with sized integers, value semantics, enums with `match`, traits and closures. It compiles to x86-64 Linux binaries without libc and is self-hosted. **It is not Rust and not Swift**: code that looks right in either usually fails here. The full reference is the wiki: `docs/Language.md` and its subpages; the grammar is `docs/Language/Grammar.md`.

Which implementation defines the language: the Python toolchain in `src/myla/` (the interpreter is the semantics). The self-hosted compiler in `selfhost/` follows it. A Rust prototype with a different dialect (semicolons, no type checking, its own actors) existed until October 2026 and was removed; its syntax is not Myla, so don't copy it from git history. Myla's own concurrency (`async`, `await`, `async let`, actors) is described below. The grammar is `grammar/myla.ebnf`; the tree-sitter grammar in `editor/` is generated from it.

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
        total = total + area(s)
    }
    let label = match total > 10 {
        true => "big"
        false => "small"
    }
    println(f"total {total} is {label}")
}
```

## Rust and Swift habits that are wrong in Myla

| Don't write | Write | Why |
| --- | --- | --- |
| `fn f()`, `func f()` | `fun f()` | The keyword is `fun` |
| `let x = 1;` at the end of every line | `let x = 1` | A newline ends a statement. `;` is optional and only separates statements or declarations on one line (`let a = 1; let b = 2`); never inside `( )`, `[ ]`, struct fields or match arms |
| `let mut x`, `var x` (Swift ok) | `var x = 1` | `let` is immutable (deeply), `var` mutable |
| `fun f() -> int { x + 1 }` | `{ return x + 1 }` | Function bodies need `return`; there is no implicit tail value |
| `let v = if c { 1 } else { 2 }` | `let v = match c { true => 1, false => 2 }` | `if` is a statement, `match` is an expression |
| `x += 1`, `x++` | `x = x + 1` | No compound assignment, no `++` |
| `E::A`, `.a` (Swift) to construct | `E.A`, `E.B(1)` | Variants are built with a dot; only `Some`/`None`/`Ok`/`Err` work bare |
| `Point::new()`, `static func` | a free function `fun new_point() -> Point` | No associated/static functions: every method takes `self` |
| `&self`, `&mut self`, `&x`, lifetimes | `self`, `var self`, plain values | No references or borrowing; everything is a value (copy-on-write under the hood) |
| `xs.push(v)`, `xs.len()`, `s.len()` | `push(xs, v)`, `len(xs)`, `len(s)` | Collection operations are built-in functions; `push`/`pop`/`remove`/`append` need a `var` place |
| `opt.unwrap()`, `.map(…)`, `.unwrap_or(…)` | `match opt { Some(v) => v, None => 0 }` or `?` | `Option`/`Result` have no methods |
| `\|x\| x + 1`, `{ x in x + 1 }` | `(x: int) => x + 1`, `(x) => { return x }` | Lambda syntax; parameter types can be omitted only when a function type is expected |
| `Fn(i32) -> i32`, `(Int) -> Int` | `(int) -> int` | Function types |
| `println!("{}", x)`, `print("\(x)")` | `print(x)`, `print(f"x = {x}")`, `format("x = {}", x)` | `print` takes exactly one int/float/char/bool/str |
| `0..=n`, `loop { }`, labelled breaks | `0..n + 1`, `while true { }` | Ranges are half-open and only exist in `for` heads; no `loop`, no labels |
| `255_u8` | `255u8` | `_` only between digits |
| `i32`, `u8`, `f64`, `Int`, `Double` as types | `int32`, `uint8`, `float64`, `int` | Type names are spelled out; suffixes are short (`5i64`, `2f64`) |
| `#[derive(PartialEq)]`, `#[test]` | `#derive(Eq)`, `#test(args)[expected]` | Attributes |
| `mod x;`, `use a::b;`, `import Foundation` | `from .x import f`, `import a.b as b`, `from std.io import println` | Python-like imports, `pub` exports |
| `impl Add for P { type Output … fn add(self, o: P) -> P }` | `impl Add for P { fun add(self, other: P) -> P { … } }` | Operator traits have no associated types; `Ord` is `cmp(self, other: Self) -> int` |
| trait default method bodies | signatures only | `trait T { fun m(self) -> int }` |
| `f::<int>(x)` | annotate: `let y: Box<int> = …` | No turbofish; type arguments only in type positions |
| `x as f64` from `bool`/`str` | only numeric ↔ numeric and `char` ↔ integer | `as` |
| a binary expression continued on the next line | keep it on one line, or split into `let`s | Newlines inside parentheses and after operators end the statement; only call arguments and literals may span lines |
| `f(a, b,)` | `f(a, b)` | No trailing comma in calls or parameter lists (fine in struct/enum bodies and literals) |

## Types and conversions

- `int` = `int32`, **`float` = `float32`**, and unsuffixed float literals default to `float32`: write `0.1f64` or annotate `let x: float64 = 0.1`.
- Integers: `int8`…`int64`, `uint8`…`uint64`, wrapping arithmetic. Also `bool`, `char` (Unicode scalar), `str` (immutable UTF-8 bytes), `StringBuilder`, tuples `(int, str)` (1-tuple `(int,)`), lists `[T]`, maps `[K: V]` (keys: integers, `char`, `bool`, `str`), function types, structs, enums, generics.
- **No implicit conversion at all.** A literal adapts to its context (`let b: uint8 = 200`, `x + 1` with `x: int64`), but a *variable* has a fixed type: `let n = 2` is an `int32`, so `big + n` with `big: int64` fails. Annotate (`let n: int64 = 2`) or cast (`n as int64`).
- `s[i]` is a byte (`uint8`); `len(s)` counts bytes; `chars(s)` gives `[char]`; `'a'` is a `char` but fits a `uint8` when one is expected (`s[i] == 'a'` works). `+` concatenates strings; no slicing.
- Escapes are the same in chars, strings and f-strings: `\n \t \r \0 \\ \" \'` and `\u{1F600}` (so `"\r\n"` works). Identifiers may use letters of any script (`größe`, `π`): Unicode XID, not normalized (D72).
- `==` works on integers, floats, `char`, `bool`, `str`, and structs/enums with `Eq` (`#derive(Eq)` or `impl Eq`). Tuples, lists and maps are not comparable.

## Syntax notes

- Struct literal `Point { x: 1, y: 2 }` (every field); in `if`/`while`/`for`/`match` heads wrap it in parentheses.
- `match`: arms `pattern [if guard] => expr` or `=> { …; last_expression }`, one per line or comma-separated. Patterns: `_`, bindings, literals, `Variant(a, b)`, `E.Variant`, tuples, `Point { x, y: 0 }`, `a | b`. Matches must be exhaustive, nested patterns included: `Some(Ok(v))`, `Some(Err(e))` and `None` cover an `Option<Result<…>>` without a `_` arm.
- A function that returns a value must end every path with `return`, `panic(…)` or `unreachable()`; loops and `match` statements don't count, so put `unreachable()` after a loop that always returns.
- `?` works on `Option`/`Result` when the function returns the same kind (same error type). Inside a lambda it returns from the lambda, so the lambda's result type must be known: pass it where a function type is expected or annotate the variable (`let f: (int) -> Option<int> = (x: int) => …`).
- `x |> f(y)` is `f(x, y)`; `f >> g` composes; `f(_, 2)` is partial application.
- Closures capture by value; captured variables can't be changed inside.
- Generic bounds: `fun sum<T: Add>(…)`; a bound allows the operator on `T`, not calling trait methods on it.
- Entry point: `fun main()` without parameters; `std.process.args()` and `std.process.exit(code)`.
- Input: `var r = stdin()` (from `std.io`), then `r.read_line()` (`Result<Option<str>, IoError>`, no `"\n"`), `r.read_exact(n)`, `r.read_to_end()`. A reader is a value, so a helper function can't read from one it was passed: keep it in a struct field and read in `var self` methods.
- Files (`std.fs`): `read_to_string(path)`, `write_to_file(path, s)`, `list_dir(path)` (`Result<[str], IoError>`, sorted, without `.`/`..`), `make_dir(path)`, `make_dir_all(path)`, `remove_file(path)`, `remove_dir(path)`, `remove_dir_all(path)`, `rename(from, to)`, `exists(path)`, `is_dir(path)`, `is_file(path)`, `current_dir()`.
- Also in the standard library: `std.json` (`parse`, `to_string`, `field`), `std.toml` (`parse`, `parse_doc`), `std.num` (`parse_int`, `parse_float`, `format_float`), `std.task` (`all`, `cancel`, `cancelled`); the reference is `docs/Language/Standard-library.md`.
- Part of a string: `var sb = StringBuilder()`, `append(sb, s, start, end)` (byte offsets, must lie within `s`), `build(sb)`; there is no slicing syntax.
- Constants: `const MAX: int = 10`; no global variables.
- `become f(args)` is a guaranteed tail call: it ends the function like `return f(args)`, but the stack doesn't grow (D87). The call must be a function, a method or a function value that's a parameter (not a builtin, a variant or a partial application), and must not be followed by `?`.

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
    print(await a + await b)
}
```

- `async fun` can suspend; a call of it, or of an actor's method from outside, must be awaited (`await f(x)`), and only in async code. The entry point is `#main async fun main()`.
- `async let x = e` starts a child task; read it once with `await x`. A scope waits for its children. Only async functions have them, and a lambda can't `await` or `task.cancel` them.
- An actor's state is reached only through `self` in its own methods; one method runs at a time, but an `await` inside an async method lets other calls in (a warning flags a field checked before an `await` and changed after it, D95).
- Values cross between tasks and actors as deep copies; nothing mutable is shared but an actor. Captures can't be changed (D93).
- `std.task`: `await task.all(fs)` runs a list of `async () -> T` functions as children; `task.cancel(a)` asks the child `a` to stop and `task.cancelled()` is how a task checks (cooperative, D96).
- A failure (panic, runtime error, `exit`) in any task ends the program at once: the others stop at their next `await` (D97).
- Native concurrency is the self-hosted compiler's (`build/myla build`, D92: `MYLA_THREADS` workers); `python3 myla.py build` refuses it (D91), the interpreter runs it.

## Working in this repository

- Run: `python3 myla.py run file.my`, test: `python3 myla.py test file.my`, compile: `python3 myla.py build file.my -o out`, type-check: `python3 myla.py check file.my`.
- The self-hosted CLI, `build/myla` (built by `scripts/bootstrap.sh`), has the same commands plus `repl`, and in a project with a `myla.toml` `new`, `build`, `run`, `test`, `check`, `fetch` and `clean` (D73).
- Every value-returning function in `examples/` needs `#test(args)[expected]` cases (a burn test enforces it); add them to new functions in `selfhost/` too: the target there is at least 80 % of value-returning functions (D109).
- New examples must be registered in `tests/burn/test_examples_run.py` and `tests/burn/test_examples_compile.py`; programs that must be rejected go to `examples/errors/` with a first line `//~ <lex|parse|module|type|runtime> error: <message substring>` (more directives, such as `//~ span:`, in `tests/burn/test_error_corpus.py`).
- The interpreter and the native backend must print the same output; check both (`run` and `build` + execute) after changing either.
- Changes to `selfhost/` must keep the bootstrap fixed point: `scripts/bootstrap.sh`.
- Before trusting a construct you're unsure of, write a five-line program and run `python3 myla.py check` on it: the checker's messages are precise.
