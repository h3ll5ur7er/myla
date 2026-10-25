# Attributes and testing

[TOC]

## Attributes

An attribute is written on the lines above a declaration: `#name`, optionally followed by `(arguments)` and `[outputs]`. The set is fixed; any other name is a type error. Attributes aren't allowed on `impl` blocks or imports.

| Attribute | On | Meaning |
| --- | --- | --- |
| `#main` | a non-generic function without parameters | The entry point, instead of the function named `main` |
| `#test(args)[expected]` | a non-generic function with a result | One test case; several may be stacked |
| `#derive(Eq)` | a non-generic struct or enum | Structural equality ([[Language/Methods-and-traits]]) |

## #test

```myla
const LIMIT: int = 100

#test(3, 4)[7]
#test(LIMIT, 1)[101]
#test(-1, 1)[0]
fun add(a: int, b: int) -> int {
    return a + b
}

fun main() {
    print(add(1, 2))
}
```

- The arguments must match the parameters and the single expected value the result type; both are checked at compile time. They may use literals, constants, struct literals, enum constructors and other expressions without local variables.
- `myla test file.my` calls the function for each case in the interpreter and compares the result with the expected value structurally. A runtime error fails the case. Output: `PASS  add #1` / `FAIL  add #2: expected 101, got …` and a summary; the exit status is 1 if anything failed.
- `#test` never affects `run` or `build`.

Every value-returning function in `examples/` and in `selfhost/` carries tests, and the burn tests enforce that ([[Development/Conventions]]). `#test` in an imported module can't refer to that module's own declarations yet ([[MYLA-11]]).

## const

```myla
const WIDTH: int = 80
const MASK: uint32 = 0xFF << 8
const NAME: str = "myla"
const HALF: float64 = 1.0 / 2.0
```

- Module-level, immutable, with a written type (D28).
- The value must be a constant expression: literals, other constants, and arithmetic, bitwise, comparison, logical and cast operations on them. The checker computes it; natively it is inlined.
- A constant defined in terms of itself, a constant division by zero and a non-constant initializer are type errors.

There are no global variables.

## assert, panic, unreachable

| Call | Effect |
| --- | --- |
| `assert(cond)`, `assert(cond, "message")` | Runtime error "assertion failed" (or the message) when `cond` is false |
| `panic("message")` | Runtime error with the message |
| `unreachable()` | Runtime error "reached unreachable code" |

`panic` and `unreachable` never return, so they satisfy the return check and need no value in a `match` arm.

## Runtime errors

| Error | Interpreter | Native |
| --- | --- | --- |
| Division or remainder by zero | message and position, exit 1 | exit 1, no message |
| List or string index out of bounds | message, exit 1 | exit 1, no message |
| Missing map key (`m[k]`) | message, exit 1 | exit 1, no message |
| `pop` on an empty list | message, exit 1 | exit 1, no message |
| `assert`, `panic`, `unreachable` | message, exit 1 | message on stderr, exit 1 |
| Heap arena exhausted (1 GiB) | — | exit 1, no message |

Silent native traps are tracked in [[MYLA-17]].
