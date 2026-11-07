# Attributes and testing

[TOC]

## Attributes

An attribute is written on the lines above a declaration: `#name`, optionally followed by `(arguments)` and `[outputs]`. The set is fixed; any other name is a type error. An `impl` block takes `#allow` only; imports take none.

| Attribute | On | Meaning |
| --- | --- | --- |
| `#main` | a non-generic function without parameters | The entry point, instead of the function named `main` |
| `#test(args)[expected]` | a non-generic function or method with a result | One test case; several may be stacked. On a method the receiver is the first argument (D116) |
| `#derive(Eq)` | a non-generic struct or enum | Structural equality ([[Language/Methods-and-traits]]); `Eq` is the only trait that can be derived (`cannot derive 'Ord': only 'Eq' is derivable`) |
| `#allow(name, …)` | a function, a method or an `impl` block | Silences the warnings of that name inside it (D161, below) |

## Warnings and #allow

A warning doesn't stop the program: `myla check` reports it and succeeds, `myla run` and `myla build` report it and go on. Each has a name, shown in its output (`warning[primitive]: …`) and given as the diagnostic's code in the editor (D161):

| Name | Warns about |
| --- | --- |
| `primitive` | a call of one of the standard library's I/O primitives (`__poll`, `__spawn`, …) outside it (D100); the raw-memory ones are errors instead (D152) |
| `reentrancy` | an actor's async method changing a field after an `await` on the strength of what it read before (D95, [[Language/Concurrency]]) |

`#allow(name)` on a function, a method or an `impl` block silences the warnings of that name in its body (the impl's: in all its methods). `#allow(primitive(__poll, __spawn))` silences only those primitives. Several names go in one `#allow`, `#allow(primitive, reentrancy)`. A struct or an actor has no code of its own: its methods are in its `impl`, which takes the `#allow`.

```myla
// the interpreter of a small language runs its I/O itself
#allow(primitive(__getcwd))
fun where() -> str {
    return __getcwd()
}

fun main() {
    print(where().len() > 0)
}
// output:
// true
```

An error can't be allowed: `#allow(primitive(__load64))` is the error "'__load64' reads or writes raw memory, which is an error outside the standard library: '#allow' silences warnings only". A name no warning has (`#allow(unused)`) is a warning itself, so a misspelt `#allow` doesn't go unnoticed. The interpreter's `impl` block in [[selfhost/interp.my]] carries `#allow(primitive)`: it runs a program's I/O through the primitives (MYLA-285).

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
// output:
// 3
```

- The arguments must match the parameters and the single expected value the result type; both are checked at compile time. They may use literals, constants, struct literals, enum constructors and other expressions without local variables.
- `myla test file.my` runs the cases declared in `file.my` itself, not those of the modules it imports, the standard library's included ([[MYLA-187]]); test a module by naming it. It calls the function for each case in the interpreter and compares the result with the expected value structurally (maps whatever their order). A runtime error (`panic`, a failed `assert` included) fails the case, and so does `exit(n)`; the other cases still run. Once all have run, it prints `PASS  add #1` or `FAIL  add #2: expected 101, got 100` for each (values as the Python interpreter's repr shows them: `True`, `'text'`, chars as code points, `P { x: 1 }`, `E.B(2)`), `FAIL  f #1: runtime error: <message>` or `FAIL  f #1: exited with status 3`, and a summary; the exit status is 1 if anything failed. This is what the Python CLI printed, and `build/myla test` prints the same ([[MYLA-81]]); output from the tests themselves comes before the report.
- `#test` never affects `run` or `build`.
- **Named cases** ([[MYLA-239]]): a `//` comment after a `#test` attribute on its line names the case, and the report shows the name after the number: `#test(-1, -2)[-3] // sums negatives` reports `PASS  add #2 (sums negatives)`, and a failure `FAIL  add #3 (wrong on purpose): expected 5, got 4`. A case without one is reported as before.
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
| An integer `as char` that isn't a Unicode scalar value (a surrogate, above U+10FFFF) | `invalid char: 55296 is not a Unicode scalar value` | `invalid char` |
| Running out of the stack | `stack overflow` (no position) | the same (no position; on every target, [[Language/Targets]], [[MYLA-261]]) |
| A slice's step of 0 | `slice step is zero` | the same |
| A `str` slice cutting a character | `a slice bound inside a character` | the same |
| Heap arena exhausted | — | `out of memory` (no position) |
