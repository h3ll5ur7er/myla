# Statements

Statement checking is `Checker._check_stmt` in [[src/myla/types.py]].

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
```

- Every binding is initialised. `let` can't be reassigned, and nothing inside it can be changed (deep immutability, D14): no `p.x = …`, no `push`, no `var self` method calls on a `let`.
- With an annotation, the value must have exactly that type (literals adopt it).
- Bindings are block-scoped. A block nested in another (the body of an `if`, a loop, a match arm or a lambda; there is no bare block statement) may shadow an outer name; declaring a name twice in the same block is an error.
- Destructuring requires a tuple and matching arity; `_` skips an element. A 1-tuple needs the comma: `let (x,) = t`.

## Assignment

`target = value`, where the target is a variable, a field chain or an index chain rooted at a `var`: `p.x = 1`, `grid[i][j] = 0`, `m["k"] = v`, `self.items[0].name = n`. A tuple element (`t.0 = …`) can't be assigned. Assignment is a statement, so `a = b = c` doesn't parse. `self` itself can't be reassigned.

There is no compound assignment (`+=`) yet.

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
```

The condition must be `bool`. `if` is a statement: it has no value (use `match` on a `bool` for a value). In the condition of `if`, `while`, `for` and `match`, a struct literal must be parenthesised, because its `{` would otherwise start the body.

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
}
```

- A range's bounds are integers of one type (literals adopt), and the loop variable has that type.
- Iterating a list visits its elements; iterating a map visits its keys, in no defined order (the interpreter uses insertion order, native code hash order).
- The loop variable is immutable. The loop works on a snapshot: changing the list inside the loop doesn't change what is visited.
- `break` and `continue` apply to the innermost loop; outside a loop they are a type error.

## return

`return` ends the function; `return value` in a function with `-> T`; `return a, b` returns the tuple `(a, b)`.

A function with a result type must return on every path. The check is deliberately simple (`_block_returns` in [[src/myla/types.py]]): a block returns if it contains a `return`, a call to `panic`/`unreachable`/`std.process.exit`, or an `if` whose every branch (including a final `else`) returns. Loops never count, and neither does a `match` statement. End such functions with `unreachable()` or return the `match` as a value:

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
```

The checker accepts a `become` that can run without the function's frame (`Checker._check_become` in [[src/myla/types.py]]):

- It stands where a `return` could, in a function's body; a lambda's body can't use it.
- It calls a function, a method (`become self.step(n)`) or a function value, not a builtin, an enum variant or a partial application. No `?` follows the call.
- The callee returns the function's result type, without a conversion, or both return nothing.
- A function value it calls must be a parameter or a part of one: `become g(x)`, `become m.next(m, n)`.
- Scalars pass freely. A function or a method takes what else `become` passes as a value of its own: a string, list, map or builder owned (the compiler passes such a parameter owned, D86), a struct, tuple or enum (or a value of a type parameter) by value, copied into its argument words (D88). A function value passed must be a parameter or a part of one.
- A function value only borrows its arguments: the address of a struct, tuple or enum, a heap value. So when `become` calls one, these must be (parts of) parameters, which live in the caller's storage. A parameter that a `become` hands a value over to can't be passed on to a function value, not even a part of it.
- A method that changes its receiver (`var self`) can only be called on `self`.

The guarantee is the `become`'s own: a function value's code runs as written, so a lambda whose body calls a function, or a partial application, makes an ordinary call there.

## Expression statements

Any expression can stand alone; usually it's a call. A `match` used as a statement may have arms without a value.

## The entry point

A runnable program has one entry function: the function marked `#main`, or else the one named `main`. Having both, or two `#main`s, is an error. The entry takes no parameters and returns nothing; read arguments with `std.process.args()` and set the exit status with `std.process.exit(code)` ([[Language/Standard-library]]). A program without an entry type-checks, but can't run.
