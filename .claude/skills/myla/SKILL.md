---
name: myla
description: Write, read, review and debug code in the Myla programming language (.my files) and work on its compilers. Myla looks like Rust and Swift but differs from both in many details, so use this before writing or changing any .my file (examples/, selfhost/, tools/, lib/std/, tests), before answering questions about Myla syntax or semantics, and when changing the Myla toolchain in selfhost/ or tools/.
---

# Myla

Myla is a small, statically typed language with sized integers, value semantics, enums with `match`, traits and closures. It compiles to static x86-64 and aarch64 Linux binaries without libc and to WebAssembly modules for WASI (`--target`), and is self-hosted. **It is not Rust and not Swift**: code that looks right in either usually fails here. The full reference is the wiki: `docs/Language.md` and its subpages; the grammar is `docs/Language/Grammar.md`.

What defines the language: the reference documentation, `docs/Language.md` and its subpages, and the decisions on `docs/Project/Decisions.md`. The implementation is the self-hosted toolchain in `selfhost/` (compiler, interpreter, CLI), bootstrapped from `bootstrap/seed.s`; its interpreter and its native code must agree. The Python toolchain that used to be the reference (`src/myla/`, `myla.py`) was removed in November 2026 (D101), so ignore old instructions that use `python3 myla.py`. A Rust prototype with a different dialect (semicolons, no type checking, its own actors) existed until October 2026 and was removed; its syntax is not Myla, so don't copy it from git history. Myla's own concurrency (`async`, `await`, `async let`, actors) is described below. The grammar is `grammar/myla.ebnf`; the tree-sitter grammar in `editor/` is generated from it.

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
| `c ? 1 : 2`, `let v = if c { 1 }` | `let v = if c { 1 } else { 2 }` | `if` is an expression when used as a value, with a required `else` (D104); no `?:` |
| `x++`, `x--` | `x += 1`, `x -= 1` | Compound assignment exists (`+=` … `>>=`, D104), `++` doesn't |
| `E::A`, `.a` (Swift) to construct | `E.A`, `E.B(1)` | Variants are built with a dot; only `Some`/`None`/`Ok`/`Err` work bare |
| `Point::new()`, `static func` in an `impl P` | a free function `fun new_point() -> Point`, or a trait's function: `trait Zero { fun zero() -> Self }`, `impl Zero for int { fun zero() -> int { return 0 } }`, called `int.zero()`, `Money.zero()`, `T.zero()` | A type has no static methods of its own; a trait may declare functions without `self` (D172), called on a type or a type parameter bounded by the trait, not on a value. A generic type's is `Box.zero()` (its arguments from the expected type), not `Box<int>.zero()`; a type keyword works, `int64.zero()` |
| `&self`, `&mut self`, `&x`, lifetimes | `self`, `var self`, plain values | No references or borrowing; everything is a value (copy-on-write under the hood) |
| `opt.unwrap()` | `opt.unwrap_or(0)`, `opt.expect("why")`, `match opt { Some(v) => v, None => 0 }`, `if let Some(v) = opt { … }` or `?` | no `unwrap`: `std.option` (implicit, D164) has `map`, `and_then`, `unwrap_or`, `expect`, …; `if let`/`while let` (D104) are sugar over `match` |
| `\|x\| x + 1`, `{ x in x + 1 }` | `(x: int) => x + 1`, `(x) => { return x }` | Lambda syntax; parameter types can be omitted only when a function type is expected |
| `Fn(i32) -> i32`, `(Int) -> Int` | `(int) -> int` | Function types |
| `println!("{}", x)`, `print("\(x)")` | `print(x)`, `print(f"x = {x}")`, `format("x = {}", x)` | `print` takes exactly one int/float/char/bool/str; holes take Rust's specs, `{x:>8.2}`, `{n:#06x}` (D139), and a type with `impl Format` (`fun format(self, spec: str) -> str`) can stand in one |
| `0..=n`, `loop { }`, labelled breaks | `0..n + 1`, `while true { }` | Ranges are half-open and only exist in `for` heads; no `loop`, no labels |
| `255_u8` | `255u8` | `_` only between digits |
| `i32`, `u8`, `f64`, `Int`, `Double` as types | `int32`, `uint8`, `float64` (or `float`), `int` | Type names are spelled out; suffixes are short (`5i64`, `2f64`) |
| `#[derive(PartialEq, Hash)]`, `#[test]` | `#derive(Eq, Hash)`, `#test(args)[expected]` | Attributes |
| `mod x;`, `use a::b;`, `import Foundation` | `from .x import f`, `import a.b as b`, `from std.io import println` | Python-like imports, `pub` exports |
| `args::Spec`, a second `from std.args import Spec` just for a type | `import std.args as args`, then `fun cli() -> args.Spec`, `[deque.Deque<int>]` | In a type, `m.T` is the module's exported type (D170); in an expression `m.f(x)`, but not `m.T { … }` (struct literals and patterns need `from … import`) |
| `impl Add for P { type Output … fn add(self, o: P) -> P }` | `impl Add for P { fun add(self, other: P) -> P { … } }` | Operator traits have no associated types; `Ord` is `cmp(self, other: Self) -> int` |
| trait default method bodies | signatures only | `trait T { fun m(self) -> int }` |
| `impl Iterator for C { type Item = int; fn next(&mut self) -> Option<i32> }`, `I: Iterator<Item = T>` | `impl Iterator<int> for C { fun next(var self) -> Option<int> { … } }`, `I: Iterator<T>` | The prelude's `Iterator<T>` is a generic trait (D171); a bound names it with its arguments, and the type's one impl fixes `T` (D55) |
| `f::<int>(x)` | `f<int>(x)`, `deque.new<str>()`, `xs.mapped<str>(g)`, or annotate: `let y: Box<int> = …` | No turbofish: type arguments go right after the name (D169); a method's name only its own type parameters. A `<` after a name is a call's only if the `>` is followed by `(`, so `f(a < b, c > (d))` is one generic call: write `f(a < b, c > d)` |
| `x as f64` from `bool`/`str` | only numeric ↔ numeric and `char` ↔ integer | `as` |
| a line that starts with an operator (`\n    + b`) | end the line with the operator (`a +`), or wrap the expression in `( )` | A statement goes on after a binary operator that ends a line and inside `( )`/`[ ]` (D104); a line that starts with an operator is a new statement |

## Types and conversions

- `int` = `int32`, `float` = `float64`, and unsuffixed float literals default to `float64` (D102); for single precision write `0.1f32` or annotate `let x: float32 = 0.1`.
- Integers: `int8`…`int64`, `uint8`…`uint64`, wrapping arithmetic. Also `bool`, `char` (Unicode scalar), `str` (immutable UTF-8 bytes), `StringBuilder`, tuples `(int, str)` (1-tuple `(int,)`), the unit type `()` with its one value `()` (D138), lists `[T]`, maps `[K: V]` (keys: any `Eq + Hash` type, D163: integers, `char`, `bool`, `str`, tuples and lists of such, `#derive(Eq, Hash)` structs and enums; not floats), function types, structs, enums, generics.
- **No implicit conversion at all.** A literal adapts to its context (`let b: uint8 = 200`, `x + 1` with `x: int64`), but a *variable* has a fixed type: `let n = 2` is an `int32`, so `big + n` with `big: int64` fails. Annotate (`let n: int64 = 2`) or cast (`n as int64`).
- `s[i]` is a byte (`uint8`); `s.len()` counts bytes; `s.chars()` gives `[char]`, and `for c in s` visits the same `char`s without making the list (D165); `'a'` is a `char` but fits a `uint8` when one is expected (`s[i] == 'a'`, `s[i] - 'a'` work). `+` concatenates strings; `<` `<=` `>` `>=` order them byte-wise, and `str` is `Ord` (`xs.sort()` on `[str]`). Slices: `xs[1:3]`, `xs[:2]`, `xs[::-1]`, `s[7:]` (new values, bounds clamped); `xs[^1]` is the last element, `^` counts from the end (D142); a negative index is an error.
- Escapes are the same in chars, strings and f-strings: `\n \t \r \0 \\ \" \'` and `\u{1F600}` (so `"\r\n"` works). Identifiers may use letters of any script (`größe`, `π`): Unicode XID, not normalized (D72).
- `==` works on integers, floats, `char`, `bool`, `str`, structs/enums with `Eq` (`#derive(Eq)` or `impl Eq`), and tuples and lists of `Eq` elements (D163). Maps are not comparable.
- `char` arithmetic (D165): `c - d` is an `int32` (`'p' - 'a' == 15`); `c + n` and `c - n` with `n: int32` are a `char` (a runtime error if not a Unicode scalar); the char goes on the left, another integer type needs `as int32`, two chars don't add.
- `Hash` (D163) is the prelude's `trait Hash { fun hash(self, h: Hasher) -> Hasher }`: `#derive(Eq, Hash)` on a struct or enum, or `impl Hash for P { fun hash(self, h: Hasher) -> Hasher { return h.add(self.x).add(self.name) } }` (std.hash, implicit, has `h.add(x)` for any `Hash` value and `add_u64`, `add_str`, …, `finish()`). Floats aren't `Hash`. A generic map key needs `K: Eq + Hash`.

## Syntax notes

- Struct literal `Point { x: 1, y: 2 }` (every field); in `if`/`while`/`for`/`match` heads wrap it in parentheses.
- `match`: arms `pattern [if guard] => expr` or `=> { …; last_expression }`, one per line or comma-separated. Patterns: `_`, bindings, literals, `Variant(a, b)`, `E.Variant`, tuples, `Point { x, y: 0 }`, `a | b`. Matches must be exhaustive, nested patterns included: `Some(Ok(v))`, `Some(Err(e))` and `None` cover an `Option<Result<…>>` without a `_` arm.
- A function that returns a value must end every path with `return`, `panic(…)` or `unreachable()`; loops and `match` statements don't count, so put `unreachable()` after a loop that always returns.
- `?` works on `Option`/`Result` when the function returns the same kind (same error type). Inside a lambda it returns from the lambda, so the lambda's result type must be known: pass it where a function type is expected or annotate the variable (`let f: (int) -> Option<int> = (x: int) => …`).
- Built-in types take impls too: `impl int { … }`, `impl [int] { … }`, `impl<T> [T] { … }`, `impl<K, V> [K: V] { … }`. A `var self` method on one writes the caller's place, by `self.push(x)` or by assigning `self = self + 1` (D144; only there may `self` be assigned, a struct's `var self` method changes fields).
- `x |> f(y)` is `f(x, y)`; `f >> g` composes; `f(_, 2)` is partial application.
- Closures capture by value; captured variables can't be changed inside.
- Generic bounds: `fun sum<T: Add>(…)`, `fun total<I: Iterator<int>>(it: I)`, `impl<I: Iterator<T>, T, U> Iterator<U> for Map<I, T, U>`; a bound allows an operator trait's operators, a user trait's (or `Format`'s) methods on `T` and its functions without `self` on `T` itself (`T.zero()`, D172), a generic trait's with its arguments (`it.next()` is an `Option<T>`). A type parameter only a bound names (`fun count<I: Iterator<T>, T>(it: I) -> int`) is fixed by the argument's impl. A generic trait in a bound needs its arguments (`I: Iterator` is an error).
- Iterators (D171): a type with `impl Iterator<T> for It { fun next(var self) -> Option<T> }` (the prelude's trait) can be looped over, `for x in it { … }`, which is `var c = it; while let Some(x) = c.next() { … }`: the loop works on a copy, and a copy of an iterator keeps its own position. A `next` method without the impl isn't enough. Adapters are generic structs holding the inner iterator and a closure, with a bounded impl; there are no trait default bodies, so `it.map(f)` doesn't exist: `std.iter`'s functions take the iterator first and chain with `|>`, `xs.iter() |> iter.map((x) => x * 3) |> iter.filter((x) => x % 2 == 0) |> iter.sum(0)` (`xs.iter()` is `std.list`'s, `m.iter()` `std.map`'s; sources `iter.range(a, b)`, `iter.repeat(v)`, `iter.from_fn(state, step)`; adapters `map`, `filter`, `take`, `skip`, `take_while`, `skip_while`, `enumerate`, `zip`, `chain`, `flat_map`; consumers `to_list`, `count`, `sum(zero)`, `fold`, `any`, `all`, `find`, `min`, `max`). The list methods stay eager.
- Entry point: `fun main()` without parameters; `std.process.args()` and `std.process.exit(code)`.
- Input: `var r = stdin()` (from `std.io`), then `r.read_line()` (`Result<Option<str>, IoError>`, no `"\n"`), `r.read_exact(n)`, `r.read_to_end()`. A reader is a value, so a helper function can't read from one it was passed: keep it in a struct field and read in `var self` methods.
- Files (`std.fs`): `read_to_string(path)`, `write_to_file(path, s)`, `list_dir(path)` (`Result<[str], IoError>`, sorted, without `.`/`..`), `make_dir(path)`, `make_dir_all(path)`, `remove_file(path)`, `remove_dir(path)`, `remove_dir_all(path)`, `rename(from, to)` (these and `write_to_file` give `Result<(), IoError>`: match `Ok(())`), `exists(path)`, `is_dir(path)`, `is_file(path)`, `current_dir()`. Streams: `fs.open(path)`, `fs.create(path)`, `fs.open_append(path)` or `fs.options().write(true).create_new(true).open(path)` give a `File` (`Read`, `Write`, `Seek` of `std.io`; close it yourself, `defer { let c = f.close() }`); `fs.metadata(path)`; `fs.make_temp_dir()`, `fs.make_temp_file()`. Children as streams: `process.command(p).spawn()` gives a `Child` (`take_stdin()`, `take_stdout()`, `wait()`, `kill()`).
- The method modules `std.str`, `std.char`, `std.int`, `std.list`, `std.option` and `std.map`, and `std.hash` (the `Hasher`'s methods, MYLA-313), are in every program without an import (D164, MYLA-320): their methods on the built-in types work anywhere, their `pub` functions need an import (`import std.str as s`; a path segment may be `str`, an alias can't). A program's own method of the same name on the same type is a duplicate. The modules of `std` don't get them: there, import what you use.
- Also in the standard library: `std.json` (`parse`, `to_string`, `field`), `std.toml` (`parse`, `parse_doc`), `std.num` (`parse_int`, `parse_float`, `format_float`), `std.task` (`all`, `cancel`, `cancelled`), `std.text` (`scanner(s)`, `ints(line)`, `wrap`), `std.grid`, `std.graph` (`bfs`, `dijkstra`, `astar` over a neighbour function), `std.set`, `std.deque`, `std.heap`, `std.btree`, `std.bitset`, `std.unionfind`, `std.random` (`seeded(n)`, `r.int_in(lo, hi)`), `std.bigint`, `std.regex`, `std.compress`; the reference is `docs/Language/Standard-library.md`, one page per module below it. Its conventions (D164): operations on built-in types are methods in `std` modules (`s.split(",")`, `xs.sorted()`; `std.str`, `std.char`, `std.int`, `std.list`, `std.option`, `std.map`, `std.hash` are implicit, see above), the rest functions of their module; strings are bytes; a fallible function returns a `Result` with its module's error enum.
- Part of a string: `var sb = StringBuilder()`, `sb.append(s, start, end)` (byte offsets, must lie within `s`), `sb.build()`; or a slice, `s[start:end]` (bytes; a bound inside a character is a runtime error).
- Constants: `const MAX: int = 10`; no global variables.
- `defer { … }` runs its block when the enclosing block ends, the last one met first: at its end, `return` (after the value), `?`, `break`, `continue`, before a `become`'s call; not on a failure (D135). It can't `return`, `?`, `await` or `break` out of itself, and sees the names declared before it.
- `become f(args)` is a guaranteed tail call: it ends the function like `return f(args)`, but the stack doesn't grow (D87). The call must be a function, a method or a function value that's a parameter (not a builtin, a variant or a partial application), and must not be followed by `?`. Past six argument words (a struct handed over counts a word per field), it can't pass more than its function received (D119).

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
- An actor may be generic (MYLA-386): `actor Cell<T> { value: T }` with `impl<T> Cell<T> { … }`, a bound on an impl of its own (`impl<T: Add> Cell<T>`, never on the declaration); made like a generic struct (`Cell { value: 0 }`, or `let c: Cell<str> = …` when the fields don't fix `T`) and named with its arguments (`Cell<int>`, `fun make<T>() -> Cell<T>`).
- Values cross between tasks and actors as deep copies; nothing mutable is shared but an actor. Captures can't be changed (D93).
- `std.task`: `await task.all(fs)` runs a list of `async () -> T` functions as children; `task.cancel(a)` asks the child `a` to stop and `task.cancelled()` is how a task checks (cooperative, D96); `await task.yield()` gives the other tasks a turn (a long loop's way to let a failure elsewhere end the program).
- A failure (panic, runtime error, `exit`) in any task ends the program at once: the others stop at their next `await` (D97).
- Native code runs tasks in parallel on `MYLA_THREADS` workers, one per CPU by default (`build/myla build`, D92); the interpreter (`build/myla run`) runs them one at a time, taking turns at each `await`.

## Working in this repository

- The CLI is `build/myla`; if it is missing, run `scripts/bootstrap.sh` first (it needs only `as` and `ld`, about 8 seconds). Run: `build/myla run file.my`, test: `build/myla test file.my`, compile: `build/myla build file.my -o out` (`-g` for gdb), type-check: `build/myla check file.my`, interactive: `build/myla repl`; in a project with a `myla.toml` also `new`, `build`, `run`, `test`, `check`, `fetch` and `clean` (D73).
- The standard library is in `lib/std/`, and the tools carry it (`selfhost/embedded_std.my`, generated by `scripts/bootstrap.sh`; `MYLA_STDLIB=$PWD/lib` uses your changes before the next bootstrap); the tests are in `tests/burn/` (`scripts/test.sh fast`, or `scripts/test.sh` for all).
- The builtin collection and string functions are methods too (D103): `xs.push(v)`, `xs.pop()`, `xs.len()`, `m.contains(k)`, `m.remove(k)`, `m.keys()`, `s.len()`, `s.chars()`, `sb.append(s)`, `sb.append_byte(b)`, `sb.build()`; they have no function form (`push(xs, v)` is an error naming the method, MYLA-221). A mutating one needs a `var` place.
- `#test` cases go above a function, or above a method inside its `impl` with the receiver as the first argument (`#test(Counter { n: 2 }, 3)[5]`, D116). A trailing comment names a case: `#test(1, 2)[3] // small numbers` reports `PASS  add #1 (small numbers)` (MYLA-239). A bare `#test` on a function without parameters (no result, or `Result<(), E>`) is a test function (D162): it passes when it returns, fails on a runtime error, `exit` or `Err(e)`; `std.test` has `expect`, `expect_eq`, `expect_ne`, `fail` and `temp_dir()` (a scratch directory removed when the case ends). `[panic("message")]` and `[exit(n)]` are expected values. Under `myla test` a failed case runs its deferred blocks; `--only <text>` selects cases, `--list` names them; a case's output is shown only when it fails. `#test` on an `async fun` runs the case as the entry task. In a project `myla test` also runs `tests/`: test programs (a trailing `// input:` / `// output:` / `// exit:` / `// stderr:` block) and test files, with `test.program()` the built program. `--native` or `--target <t>` runs the cases natively through a generated harness (`selfhost/harness.my`); a failed case runs no deferred block there.
- Every value-returning function in `examples/` needs `#test(args)[expected]` cases (a burn test enforces it); add them to new functions in `selfhost/` too: the target there is at least 80 % of value-returning functions (D109).
- New examples must be registered in `tests/burn/test_examples_run.py` and `tests/burn/test_examples_compile.py`; programs that must be rejected go to `examples/errors/` with a first line `//~ <lex|parse|module|type|runtime> error: <message substring>` (more directives, such as `//~ span:`, in `tests/burn/test_error_corpus.py`).
- A ```` ```myla ```` block in `docs/` or the README is a tested program (`tests/burn/test_doc_blocks.py`): it must check and, with a `main`, run; it may end with `// output:` and one `// ` line per printed line. Mark pieces ```` ```myla fragment ```` and deliberately wrong code ```` ```myla error ```` (D114).
- The interpreter and the native backend must print the same output; check both (`run` and `build` + execute) after changing either.
- Changes to `selfhost/` must keep the bootstrap fixed point: `scripts/bootstrap.sh`. A pull request that changes the compiler's output ends with a new seed (D156, one per pull request): `scripts/update-seed.sh`, then commit `bootstrap/seed.s`, `bootstrap/seed-aarch64.s` and `selfhost/embedded_std.my` (CI fails on a stale one at the pull request's tip).
- Before trusting a construct you're unsure of, write a five-line program and run `build/myla check` on it: the checker's messages are precise.
