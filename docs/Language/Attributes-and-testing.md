# Attributes and testing

[TOC]

## Attributes

An attribute is written on the lines above a declaration: `#name`, optionally followed by `(arguments)` and `[outputs]`. The set is fixed; any other name is a type error. Attributes aren't allowed on `impl` blocks or imports.

| Attribute | On | Meaning |
| --- | --- | --- |
| `#main` | a non-generic function without parameters | The entry point, instead of the function named `main` |
| `#test(args)[expected]` | a non-generic function or method with a result | One test case; several may be stacked. On a method the receiver is the first argument (D116) |
| `#derive(Eq)` | a non-generic struct or enum | Structural equality ([[Language/Methods-and-traits]]); `Eq` is the only trait that can be derived (`cannot derive 'Ord': only 'Eq' is derivable`) |

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
- `myla test file.my` runs the cases declared in `file.my` itself, not those of the modules it imports, the standard library's included ([[MYLA-187]]); test a module by naming it. It calls the function for each case in the interpreter and compares the result with the expected value structurally (maps whatever their order). A runtime error (`panic`, a failed `assert` included) fails the case, and so does `exit(n)`; the other cases still run. Once all have run, it prints `PASS  add #1` or `FAIL  add #2: expected 101, got 100` for each (values as the Python interpreter's repr shows them: `True`, `'text'`, chars as code points, `P { x: 1 }`, `E.B(2)`), `FAIL  f #1: runtime error: <message>` or `FAIL  f #1: exited with status 3`, and a summary; the exit status is 1 if anything failed. This is what the Python CLI printed, and `build/myla test` prints the same ([[MYLA-81]]); output from the tests themselves comes before the report.
- `#test` never affects `run` or `build`.
- **Methods** (D116) take cases too, written above the method inside its `impl`; the receiver is the first argument, and the report names the case `Type.method` (`PASS  Counter.get #1`, `int32.double #1` for a method on `int`):

  ```myla
  struct Counter {
      n: int,
  }

  impl Counter {
      #test(Counter { n: 2 }, 3)[5]
      fun plus(self, k: int) -> int {
          return self.n + k
      }
  }
  ```

  For a `var self` method only the result is compared, not the changed receiver. A method of a generic `impl` or with type parameters of its own, an actor's method (its receiver is a running actor, not a value) and an `async` method can't have cases; `#test` is the only attribute a method takes.

Every value-returning function in `examples/` carries tests, and the burn tests enforce that ([[Development/Conventions]]); in `selfhost/` some do ([[MYLA-184]]). A `#test` in an imported module can use that module's own declarations ([[MYLA-11]]).

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

Both report on stderr and exit 1. The interpreter gives the message with its values, the source position, the source line and a caret; a native binary prints the first two lines, `runtime error: <message>` without the values, then the same position ([[MYLA-17]], [[MYLA-65]]):

```
$ myla run examples/errors/runtime_list_index_oob.my
runtime error: list index 3 out of bounds (len 3)
  --> examples/errors/runtime_list_index_oob.my:8:13
  |
8 |     print(xs[3])
  |             ^
$ myla build examples/errors/runtime_list_index_oob.my -o oob && ./oob
wrote oob
runtime error: index out of bounds
  --> examples/errors/runtime_list_index_oob.my:8:13
```

The position is that of the expression that fails: an index's `[`, a call's `(` (`pop`, `append`, `assert`, `panic`, `unreachable`), a division's operator. A binary names the file as `myla build` named it when it was compiled: the entry file as given on the command line, an imported module relative to the working directory (D75).

| Error | Interpreter | Native |
| --- | --- | --- |
| Division or remainder by zero | `division by zero` / `modulo by zero` | the same |
| List or string index out of bounds | `list index 5 out of bounds (len 2)` | `index out of bounds` |
| Missing map key (`m[k]`) | `map key 'b' not found` | `map key not found` |
| `pop` on an empty list | `pop from an empty list` | the same |
| `assert`, `panic`, `unreachable` | the message | the same |
| Heap arena exhausted | — | `out of memory` (no position) |
