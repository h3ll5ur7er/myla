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

- Parameter and result types are always written; a function without `-> T` returns the unit value `()`, the same as one declared `-> ()` (D140): its type is `(…) -> ()`, and `return ()` may end it.
- Parameters are immutable inside the body, and arguments are passed by value.
- Functions may be declared in any order and may recurse.
- Calls give the declared arguments, each of the parameter's type; trailing parameters with a default value may be left out ("Default values" below).
- A top-level name can't reuse a built-in function's name (`print`, `len`, `push`, …).
- Every path must return a value ([[Language/Statements]]).


### Default values

A function's or method's trailing parameters may have default values (`port: int = 80`), and a call may leave out a suffix of them (D136, [[MYLA-255]]). The caller evaluates each default it leaves out, at each call, so a default may be any expression of the parameter's type that doesn't name another parameter: a constant, a call, a literal. There are no named arguments: only the last parameters can be left out.

```myla
fun connect(host: str, port: int = 80, retries: int = 3) -> str {
    return f"{host}:{port}, {retries} tries"
}

fun main() {
    print(connect("example.org"))
    print(connect("example.org", 8080))
    print(connect("example.org", 8080, 5))
    let f = connect
    print(f("x", 1, 1))
}
// output:
// example.org:80, 3 tries
// example.org:8080, 3 tries
// example.org:8080, 5 tries
// x:1, 1 tries
```

- **Defaults belong to the declaration,** not to the function's type: a function value of `connect` is a `(str, int, int) -> str` and takes every argument, and a partial application lists every position (`connect(_, 8080, 3)`).
- **Errors:** a parameter without a default after one with a default; a default of another type; one that names another parameter; a default on a parameter whose type mentions a type parameter, which the caller couldn't evaluate; defaults on a trait's methods, as a call through a bound can't know an implementation's. Too few or too many arguments say how many the function takes (`expects 1 to 3 argument(s)`).
- **`#test`** cases give every argument.
- **Implementation:** once the program is checked, every call that leaves arguments out gets its defaults (the checker's `fill_defaults`), so the interpreter and every backend see each call whole; `become`'s word rule counts them (D131).

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
