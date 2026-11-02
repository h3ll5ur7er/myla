# Functions and closures

[TOC]

## Functions

```myla
fun clamp(x: int, lo: int, hi: int) -> int {
    if x < lo { return lo }
    if x > hi { return hi }
    return x
}

fun main() {
    print(clamp(15, 0, 10))
}
// output:
// 10
```

- Parameter and result types are always written; a function without `-> T` returns nothing.
- Parameters are immutable inside the body, and arguments are passed by value.
- Functions may be declared in any order and may recurse.
- Calls must give exactly the declared number of arguments, each of the parameter's type.
- A top-level name can't reuse a built-in function's name (`print`, `len`, `push`, …).
- Every path must return a value ([[Language/Statements]]).

## Function values

```myla
fun twice(f: (int) -> int, x: int) -> int {
    return f(f(x))
}

fun inc(x: int) -> int { return x + 1 }

fun main() {
    let add = (a: int, b: int) => a + b
    let k = 10
    let add_k = (x: int) => x + k          // captures k by value
    let square = (x: int) => {
        let y = x * x
        return y
    }
    print(twice(inc, 1))                   // a fun as a value
    print(twice(add_k, 1))
    print(twice((x) => x * 3, 1))          // parameter type from the expected type
    print(add(2, 3) + square(4))
}
// output:
// 3
// 21
// 9
// 21
```

- A **lambda** is `(params) => expression` or `(params) => { block }`. Parameter types may be left out when the lambda is passed where a function type is expected; otherwise they're required. The result type is inferred from the body (for a block, from its `return`s).
- A non-generic top-level `fun` can be used as a value. Generic functions can't.
- **Captures are by value** (D48): a lambda copies every outer variable it uses when it is created. Captured values are immutable inside the lambda: assigning to one, to a field or element of one, or changing it with `push`, `pop`, `remove`, `append` or a `var self` method is an error (`a lambda can't change 'x', a variable it captures: it holds a copy of its own`, D93). Changing the original afterwards doesn't affect the copy. To share state between functions or tasks, use an actor. By-reference capture (`ref`) is a planned extension (D15).
- A function value is called like a function. Calling through a struct field works too: `handler.on_event(x)`, when `on_event` is a field of function type (and not a method).
- Closures and plain functions have the same type; the representation is a pair of a code pointer and a reference-counted environment (D49, [[Architecture/Native-backend]]).

## Pipelines, composition and partial application

`x |> f(y)`, `f >> g` and `f(_, y)` are described with the operators: [[Language/Expressions-and-operators]]. All three are rewritten into calls and lambdas before running.
