# Statements

Statement checking is `Checker.check_stmt` in [[selfhost/checker.my]].

Statements are separated by line breaks, or by `;` to put several on one line: `let t = a; let u = b` (D61, [[Language/Lexical-structure]]).

[TOC]

## Bindings

```myla
fun main() {
    let x = 10              // immutable
    var y: int64 = 0        // mutable, annotated
    y = y + 1
    let (a, (b, _)) = (1, (2, 3))   // destructuring a tuple
    print(x + a + b)
    print(y)
}
// output:
// 13
// 1
```

- Every binding is initialised. `let` can't be reassigned, and nothing inside it can be changed (deep immutability, D14): no `p.x = …`, no `push`, no `var self` method calls on a `let`.
- With an annotation, the value must have exactly that type (literals adopt it).
- Bindings are block-scoped. A block nested in another (the body of an `if`, a loop, a match arm or a lambda; there is no bare block statement) may shadow an outer name; declaring a name twice in the same block is an error.
- Destructuring requires a tuple and matching arity; `_` skips an element. A 1-tuple needs the comma: `let (x,) = t`.

## Assignment

`target = value`, where the target is a variable, a field chain or an index chain rooted at a `var`: `p.x = 1`, `grid[i][j] = 0`, `m["k"] = v`, `self.items[0].name = n`. A tuple element (`t.0 = …`) can't be assigned. Assignment is a statement, so `a = b = c` doesn't parse. `self` itself can't be reassigned in a struct's method; in a `var self` method of a builtin type `self = v` writes the receiver (D144).

Compound assignment (D104 (2), [[MYLA-223]]): `+=`, `-=`, `*=`, `/=`, `%=`, `&=`, `|=`, `^=`, `<<=` and `>>=` mean `place = place op value`. The place is a `var`, a field or an element of one, as for `=`, and it is evaluated once: in `xs[next()] += 1` `next()` runs once. The operator is the binary one, so a struct's `+=` uses its `Add` impl and `f >>= g` composes two functions. It is checked as `place = place op value` is: an index computed once still expects the place's key type, so `r[Ok("a")] += 1` with `r: [Result<str, int>: int]` and `w[2 * n] += 1` with `w: [int64: int]` check ([[MYLA-448]]), and an operator the place's type lacks is the error (`xs += ys` on lists: `operator '+' requires numeric or string operands`).

```myla
fun main() {
    var total = 10
    total += 5
    total *= 2
    var words = ["a", "b"]
    words[1] += "c"
    print(total)
    print(words[1])
}
// output:
// 30
// bc
```

## if / else

```myla
fun sign(n: int) -> str {
    if n < 0 {
        return "negative"
    } else if n == 0 {
        return "zero"
    }
    return "positive"
}

fun main() {
    print(sign(-3))
}
// output:
// negative
```

The condition must be `bool`. Used as a value (D104 (1), [[MYLA-222]]), `if c { a } else { b }` is an expression: each branch block ends in an expression, its value; the `else` is required, an `else if` chains, and the branches have one type, as a `match`'s arms do. There is no `?:` operator.

```myla
fun sign(n: int) -> str {
    return if n < 0 { "negative" } else if n == 0 { "zero" } else { "positive" }
}

fun main() {
    let n = 7
    let half = if n % 2 == 0 {
        n / 2
    } else {
        let up = n + 1
        up / 2
    }
    print(sign(n))
    print(half)
}
// output:
// positive
// 4
```

A block that gives a value (an `if` branch, a `match` arm) may end with an `if` statement whose every level has an `else`: it reads as the `if` expression. In the condition of `if`, `while`, `for` and `match`, a struct literal must be parenthesised, because its `{` would otherwise start the body.

## if let / while let

`if let P = e { … } else { … }` runs its block when `e` matches the pattern `P`, with `P`'s bindings in scope there only; `while let P = e { … }` runs its body while `e` (evaluated before each round) matches (D104 (5), [[MYLA-226]]). They are sugar over `match`: `match e { P => { … }, _ => { … } }`, and `while true { match e { P => { … }, _ => { break } } }`. An `if let` chains with `else if`, and gives a value as an `if` does. A pattern that always matches (a name, a tuple of names) is an error: write `let`.

```myla
fun find(xs: [int], want: int) -> Option<int> {
    for i in 0..xs.len() {
        if xs[i] == want {
            return Some(i)
        }
    }
    return None
}

fun main() {
    if let Some(i) = find([4, 7, 9], 7) {
        print(i)
    }
    let at = if let Some(i) = find([4, 7, 9], 5) { i } else { -1 }
    print(at)
    var n = 3
    while let Some(_) = find([1, 2, 3], n) {
        n -= 1
    }
    print(n)
}
// output:
// 1
// -1
// 0
```


## let-else

`let P = e else { … }` matches `e` against a pattern `P` that can fail, such as a variant (`Some(x)`, `Ok(v)`, `Shape.Rect(w, h)`), optionally with alternatives (`|`). When it matches, `P`'s bindings are in scope for the rest of the block. When it doesn't, the `else` block runs, and that block must leave: end it with `return`, `become`, `break`, `continue` or a call that never returns (`panic`, `unreachable`, `exit`). One that can fall through is an error, and so is a pattern that always matches (D137, [[MYLA-256]]). The pattern is one variant pattern: a tuple of patterns, `let (Some(a), b) = t else { … }`, is a parse error (a `let (…)` binds names), so write that as a `match` or an `if let`. It is sugar over `match`: `match e { P => { the rest of the block }, _ => { … } }`, so a function may also end in a `match` whose every arm returns. It keeps the expected case unindented where `if let` would nest it:

```myla
fun parse_port(s: str) -> Result<int, str> {
    if s == "80" { return Ok(80) }
    if s == "443" { return Ok(443) }
    return Err("not a port")
}

fun ports(args: [str]) -> [int] {
    var out: [int] = []
    for a in args {
        let Ok(p) = parse_port(a) else {
            continue
        }
        out.push(p)
    }
    return out
}

fun head(xs: [int]) -> Option<int> {
    if xs.len() == 0 { return None }
    return Some(xs[0])
}

fun first(xs: [int]) -> str {
    let Some(x) = head(xs) else {
        return "none"
    }
    return f"first {x}"
}

fun main() {
    let ps = ports(["80", "x", "443"])
    print(ps.len())
    print(first(ps))
    print(first([]))
}
// output:
// 2
// first 80
// none
```

## Loops

```myla
fun main() {
    var i = 0
    while i < 3 {
        i = i + 1
    }
    for k in 0..5 {          // half-open: 0, 1, 2, 3, 4
        if k == 1 { continue }
        if k == 4 { break }
        print(k)
    }
    for name in ["a", "b"] { print(name) }
    let ages = ["ann": 31]
    for key in ages { print(key) }      // keys of a map
    for c in "hé" { print(c) }          // characters of a string
    for (name, age) in ages.items() { print(f"{name} {age}") }
    for ((x, y), _) in [((1, 2), "p")] { print(x + y) }
}
// output:
// 0
// 2
// 3
// a
// b
// ann
// h
// é
// ann 31
// 3
```

- A range's bounds are integers of one type (literals adopt), and the loop variable has that type.
- Iterating a list visits its elements; iterating a map visits its keys in the order they were first inserted (D105); iterating a string visits its characters, each a `char`, as `s.chars()` gives them (U+FFFD for a byte that isn't part of a well-formed UTF-8 sequence), without making that list (D165, [[MYLA-318]]). A string's bytes are `s[i]` for `i` in `0..s.len()`.
- Iterating a value whose type implements the prelude's `Iterator<T>` calls its `next` until it gives `None`: `for x in e` is `var it = e; while let Some(x) = it.next() { … }`, so it loops over a copy of `e`, and the loop variable is a `T` (D171, [[Language/Methods-and-traits#iterators]]). A type parameter loops so with the bound `I: Iterator<T>`. Any other type is an error (`` `for ... in` requires a list, a map, a string, a range or an Iterator ``).
- In place of the loop variable, a tuple of names binds the parts of each element, as `let` destructures (`for (k, v) in m.items()`, nested tuples, `_` for a part it drops; [[MYLA-390]]): `for (k, v) in e { … }` is `for kv in e { let (k, v) = kv; … }`, so the elements must be tuples of that shape (`cannot destructure non-tuple value`). Other patterns, which can fail (`Some(x)`), don't go in a `for` head: write `while let` or a `match` in the body.
- The loop variable is immutable. The loop works on a snapshot: changing the list inside the loop doesn't change what is visited.
- `break` and `continue` apply to the innermost loop; outside a loop they are a type error.

## return

`return` ends the function; `return value` in a function with `-> T`; `return a, b` returns the tuple `(a, b)`.

A function with a result type must return on every path. The check is deliberately simple (`block_returns` in [[selfhost/checker.my]]): a block returns if it contains a `return`, a call to `panic`/`unreachable`/`std.process.exit`, or an `if` whose every branch (including a final `else`) returns. Loops never count, and neither does a `match` statement. End such functions with `unreachable()` or return the `match` as a value:

```myla
fun first_even(xs: [int]) -> int {
    for x in xs {
        if x % 2 == 0 { return x }
    }
    unreachable()
}

fun main() {
    print(first_even([1, 4]))
}
// output:
// 4
```

## become

`become f(args)` ends the function like `return f(args)`, but the call runs in place of the function: its frame is gone by the time the call starts. However long a chain of `become`s runs (a recursion, functions calling each other, a state machine), the stack doesn't grow. Every implementation guarantees it, also with `-g` (D87, [[MYLA-128]]). A `return` of a call stays an ordinary return. The self-hosted compiler still turns it into a jump when it can ([[MYLA-126]]), but nothing guarantees it.

```myla
fun gcd(a: int, b: int) -> int {
    if b == 0 { return a }
    become gcd(b, a % b)
}

fun is_even(n: int) -> bool {
    if n == 0 { return true }
    become is_odd(n - 1)
}

fun is_odd(n: int) -> bool {
    if n == 0 { return false }
    become is_even(n - 1)
}

fun main() {
    print(gcd(1071, 462))      // 21
    print(is_even(1000000))    // true, without a million frames
}
// output:
// 21
// true
```

The checker accepts a `become` that can run without the function's frame (`Checker.check_become` in [[selfhost/checker.my]]):

- It stands where a `return` could, in a function's body; a lambda's body can't use it.
- It calls a function, a method (`become self.step(n)`) or a function value, not a builtin, an enum variant or a partial application. No `?` follows the call.
- The callee returns the function's result type, without a conversion, or both return nothing.
- A function value it calls must be a parameter or a part of one: `become g(x)`, `become m.next(m, n)`.
- Scalars pass freely. A function or a method takes what else `become` passes as a value of its own: a string, list, map or builder owned (the compiler passes such a parameter owned, D86), a struct, tuple or enum (or a value of a type parameter) by value, copied into its argument words (D88). A function value passed must be a parameter or a part of one.
- A function value only borrows its arguments: the address of a struct, tuple or enum, a heap value. So when `become` calls one, these must be (parts of) parameters, which live in the caller's storage. A parameter that a `become` hands a value over to can't be passed on to a function value, not even a part of it.
- A method that changes its receiver (`var self`) can only be called on `self`.
- It passes no more argument words on the stack than the function received there (D119; on every target, D131). Each argument is a word (a struct, tuple or enum handed over by value as many as it has fields, a nested recursive enum counting one, D88), and so is an aggregate result's address; the first six words travel in registers, so a `become` passing six or fewer is always accepted. Past six, the callee's words go where the function's own came, as its caller pops them (`check_become_words`). A value of a type parameter takes the words of the type it is in each instance, which the checker can't know: a generic function's `become` is counted again for each instance where it is built, and one that passes too many is the same type error, at the `become`, with a note naming the type arguments (`myla build`; `myla run` and `myla check` don't build instances, [[MYLA-272]]).

The guarantee is the `become`'s own: a function value's code runs as written, so a lambda whose body calls a function, or a partial application, makes an ordinary call there.

## defer

`defer { … }` runs its block when the block it stands in ends (D135, D141, [[MYLA-229]]): at its end, and at each way out of it that runs: `return` (after the returned value is computed), `?`, `break`, `continue`, and a `become` (after its arguments, before its call). Several run the last one met first. A `defer` that wasn't reached doesn't run.

```myla
fun copy(lines: [str]) -> int {
    var done = 0
    defer {
        print(f"copied {done}")
    }
    for l in lines {
        if l == "" {
            return done
        }
        done += 1
    }
    return done
}

fun main() {
    print(copy(["a", "b", "", "c"]))
}
// output:
// copied 2
// 2
```

- The block reads the variables as they are when it runs (`done` above), and sees the names declared before the `defer`: one declared later, or by a block it is left from, isn't the one it means.
- It may not `return`, `become`, use `?`, `await`, or start a task with `async let`: it runs on the way out, without suspending. `break` and `continue` only reach a loop inside it. A lambda in it is a function of its own.
- In an async function a block's children end first (the block waits for them as it ends), then its deferred blocks run.
- A failure (a runtime error, `exit`) ends the program and runs none (D97, D141), except inside a `#test` case under `myla test`, which it ends instead: the case unwinds through its deferred blocks, innermost first, as a `return` would (D162, [[Language/Attributes-and-testing#when-a-case-fails]]).
- A failure (a panic, a runtime error, `exit`) runs none: it ends the program at once (D97). They run on every way out the program survives (D141); a cancellation only asks a task to stop (D96), so it stops nothing itself.
- `defer` is a keyword only at the start of a statement before `{`; elsewhere it is an ordinary name.
- At the top of the REPL the session's scope never ends, so a `defer` typed there doesn't run.

## Expression statements

Any expression can stand alone; usually it's a call. A `match` used as a statement may have arms without a value.

## The entry point

A runnable program has one entry function: the function marked `#main`, or else the one named `main`. Having both, or two `#main`s, is an error. The entry takes no parameters and returns nothing; read arguments with `std.process.args()` and set the exit status with `std.process.exit(code)` ([[Language/Standard-library]]). A program without an entry type-checks, but can't run: `myla run` says `runtime error: no entry point: define '#main' or a function named 'main'`, and `myla build` refuses it as an error of its own kind, `error: no entry point: define '#main' or a function named 'main'`, on every target, writing nothing ([[MYLA-415]], D188). Once Myla has a foreign function interface, such a file will build into a library instead ([[MYLA-505]]).
