# Statements

Statement checking is `Checker._check_stmt` ([[src/myla/types.py#L1733-L1863]]).

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
- Bindings are block-scoped. An inner block may shadow an outer name; declaring a name twice in the same block is an error.
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

A function with a result type must return on every path. The check is deliberately simple ([[src/myla/types.py#L3997-L4027]]): a block returns if it contains a `return`, a call to `panic`/`unreachable`/`std.process.exit`, or an `if` whose every branch (including a final `else`) returns. Loops never count, and neither does a `match` statement. End such functions with `unreachable()` or return the `match` as a value:

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

## Expression statements

Any expression can stand alone; usually it's a call. A `match` used as a statement may have arms without a value.

## The entry point

A runnable program has one entry function: the function marked `#main`, or else the one named `main`. Having both, or two `#main`s, is an error. The entry takes no parameters and returns nothing; read arguments with `std.process.args()` and set the exit status with `std.process.exit(code)` ([[Language/Standard-library]]). A program without an entry type-checks, but can't run.
