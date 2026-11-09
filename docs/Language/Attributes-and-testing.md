# Attributes and testing

[TOC]

## Attributes

An attribute is written on the lines above a declaration: `#name`, optionally followed by `(arguments)` and `[outputs]`. The set is fixed; any other name is a type error. An `impl` block takes `#allow` only; imports take none.

| Attribute | On | Meaning |
| --- | --- | --- |
| `#main` | a non-generic function without parameters | The entry point, instead of the function named `main` |
| `#test(args)[expected]` | a non-generic function or method | One test case; several may be stacked. On a method the receiver is the first argument (D116). The expected value may be `panic("message")` or `exit(n)`, the failure the call must end in (D162) |
| `#test` | a non-generic function without parameters, with no result or a `Result<(), E>` | A test function (D162): it passes when it returns, fails on a runtime error, `exit` or `Err(e)` |
| `#derive(Eq)`, `#derive(Hash)`, `#derive(Eq, Hash)`, `#derive(Json)`, `#derive(Toml)` | a struct or enum, generic too (its impl bounded by the trait, [[MYLA-379]]) | Structural equality and hashing ([[Language/Methods-and-traits]], D163), a JSON form (std.json's `ToJson` and `FromJson`, [[Language/Standard-library/Json]], D172), a TOML form (std.toml's `ToToml` and `FromToml`, [[Language/Standard-library/Toml]], [[MYLA-407]]); `Eq`, `Hash`, `Json` and `Toml` are the traits that can be derived (`cannot derive 'Ord': only 'Eq', 'Hash', 'Json' and 'Toml' are derivable`) |
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
- `myla test file.my` runs the cases declared in `file.my` itself, not those of the modules it imports, the standard library's included ([[MYLA-187]]); test a module by naming it. It calls the function for each case in the interpreter and compares the result with the expected value structurally (maps whatever their order). A runtime error (`panic`, a failed `assert` included) fails the case, and so does `exit(n)`; the other cases still run. Once all have run, it prints `PASS  add #1` or `FAIL  add #2: expected 101, got 100` for each (values as the Python interpreter's repr shows them: `True`, `'text'`, chars as code points, `P { x: 1 }`, `E.B(2)`, by their type: a `uint64` unsigned, [[MYLA-361]]), `FAIL  f #1: runtime error: <message>` or `FAIL  f #1: exited with status 3`, and a summary; the exit status is 1 if anything failed. This is what the Python CLI printed, and `build/myla test` prints the same ([[MYLA-81]]); output from the tests themselves comes before the report.
- `#test` never affects `run` or `build`.
- **Selection** (D162): `myla test file.my --only <text>` runs the cases whose function's name contains the text (a method's `Type.method`), `--list` prints the cases' names without running them. There are no skips: a case that must not run is removed.
- **Output**: what a case prints is kept and shown only when the case fails, under its line, each line after `      | `; a passing case's output isn't shown.
- **Named cases** ([[MYLA-239]]): a `//` comment after a `#test` attribute on its line names the case, and the report shows the name after the number: `#test(-1, -2)[-3] // sums negatives` reports `PASS  add #2 (sums negatives)`, and a failure `FAIL  add #3 (wrong on purpose): expected 5, got 4`. A case without one is reported as before.
- **Methods** (D116) take cases too, written above the method inside its `impl`; the receiver is the first argument, and the report names the case `Type.method` (`PASS  Counter.get #1`, `int32.double #1` for a method on `int`, `[str].width #1` for one on `[str]`, [[MYLA-357]]):

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

  For a `var self` method only the result is compared, not the changed receiver. A method of a generic `impl` or with type parameters of its own, an actor's method (its receiver is a running actor, not a value) and an `async` method can't have cases (an async function can, [below](#async-cases)); `#test` is the only attribute a method takes.

Every value-returning function in `examples/` carries tests, and the burn tests enforce that ([[Development/Conventions]]); in `selfhost/` some do ([[MYLA-184]]). A `#test` in an imported module can use that module's own declarations ([[MYLA-11]]).

### Test functions

A test that is a body rather than a line is a function without parameters under a bare `#test` (D162, [[MYLA-303]]): sugar for `#test()[()]`, named by the function's name, reported as `PASS  writes_and_reads`. It passes when it returns and fails on a runtime error (`assert`, `panic`, a failed expectation of `std.test`) or `exit`. Its result is none, or `Result<(), E>`: `Ok(())` passes, `Err(e)` fails the case with `e` shown as `{}` would show it (`FAIL  reads_the_config: not found (NotFound)`, an `IoError`'s message, D173), so `?` is the way to say "and that must work". A test function is an ordinary function in every other way: it may be called, it takes `defer`, and `myla build` drops it with the cases.

```myla
import std.test as test
import std.fs as fs
from std.fs import IoError

#test
fun writes_and_reads() -> Result<(), IoError> {
    let d = test.temp_dir()
    fs.write_to_file(d + "/a.txt", "hello")?
    test.expect_eq(fs.read_to_string(d + "/a.txt")?, "hello")
    return Ok(())
}

#test // a port above 65535 is refused
fun rejects_a_bad_port() {
    match parse_port("70000") {
        Some(p) => { test.fail(f"accepted {p}") },
        None => {},
    }
}

fun parse_port(text: str) -> Option<int> {
    var n = 0
    for c in text.chars() {
        if c < '0' || c > '9' { return None }
        n = n * 10 + (c as int - '0' as int)
    }
    if n > 65535 { return None }
    return Some(n)
}

fun main() {}
```

`std.test` ([[Language/Standard-library/Test]]) has the checks, `expect(cond, msg)`, `expect_eq(got, want)` ("expected 3, got 4"), `expect_ne` and `fail(msg)`, and `temp_dir()`, a fresh empty directory for the case under `$TMPDIR` (else `/tmp`) that the runner removes when the case ends, passed or failed. A fixture is a value: a function's result, built in the case's arguments (`#test(db_with(3))[3]`) or in the test function's body; nothing is shared between cases.

### When a case fails

A failure (a runtime error, `exit`, a failed expectation) ends the case as a `return` would have (D162, D141 amended): the deferred blocks of every block between the failure and the case's function run, innermost first, then the case is reported as failed. A deferred block that fails itself is noted with the case (`FAIL  t: runtime error: boom; deferred block: runtime error: bang`) and the unwinding goes on. Outside `myla test` nothing changes: a failure ends the program at once and runs no deferred block (D97, D141).

### Async cases

`#test` on an `async fun` (D162, D116 amended) runs the case as the entry task of a program of its own: a test function (`#test` above `async fun counts_in_parallel()`) or a case with arguments (`#test(3)[6]` above `async fun doubled(n: int) -> int`). Every task the case starts ends before the case does, as a program's do; a child's failure fails the case (D97); the interpreter runs the tasks one at a time in its one-worker order (D110), so the case is deterministic. An actor is tested through an async test function that makes it; an actor's method and an async method take no cases (their receiver is a running actor, or the method needs a task).

```myla
import std.test as test

actor Counter {
    n: int,
}

impl Counter {
    async fun bump(var self, by: int) {
        self.n = self.n + by
    }

    async fun get(self) -> int {
        return self.n
    }
}

async fun bump_many(c: Counter, times: int) {
    var i = 0
    while i < times {
        await c.bump(1)
        i = i + 1
    }
}

#test
async fun counts_in_parallel() {
    let c = Counter { n: 0 }
    async let a = bump_many(c, 100)
    async let b = bump_many(c, 100)
    await a
    await b
    test.expect_eq(await c.get(), 200)
}

fun main() {}
```

### Integration tests in a project

In a project ([[Architecture/Project-tool]]) `myla test` runs the files of `tests/` after those of `src/` (D162, [[MYLA-306]]). A file whose trailing comment block has `// output:` is a **test program**: a program run with the `// input:` lines on its standard input, whose output must be the `// output:` lines, whose exit status must be `// exit:` (0 without one) and whose standard error must start with the `// stderr:` lines when there are any (a runtime error's first line, say). It is reported as `PASS  tests/greets.my`, or `FAIL  tests/greets.my: output differs` with the expected and the actual lines under it. Any other file under `tests/` is a file of `#test` cases and test functions, run as a file of `src/` is; both import the project's modules as `src/main.my`'s do. `std.test.program()` is the path of the project's program, which `myla test` builds first, so a test function can run it with `std.process.command(test.program()).stdin("…").output()` and expect on what it printed.

```myla fragment
// tests/greets.my
from std.io import stdin
from names import polite

fun main() {
    var r = stdin()
    match r.read_line() {
        Ok(Some(line)) => { print("hi " + polite(line)) },
        _ => { print("nobody") },
    }
}
// input:
// bob
// output:
// hi Bob
```

### Native runs

`myla test file.my --native` runs the file's cases natively (D162, [[MYLA-307]]): the compiler builds a *harness* from the file and its cases ([[selfhost/harness.my]]), a program that calls each case's function with the case's arguments, compares the result with the expected value and prints the interpreter's report, line for line, so `myla test` and `myla test --native` can be held to each other; `myla test --target aarch64-linux` or `wasm32-wasi` builds the harness for that target and runs it under `qemu-aarch64`, or the command `MYLA_EMULATOR` names (`node tools/wasm/run.mjs` for wasm32). The harness runs every case in a child process of itself, so a runtime error or an `exit` ends that case only, and its output and scratch directory are handled as in the interpreter; `--only` and `--list` work the same. In a project, `--native` also builds and runs the test programs of `tests/`. Everything `myla test` builds is built checked (`myla build --checked`): an integer overflow fails the case natively as it does interpreted, `runtime error: integer overflow`, which `[panic("integer overflow")]` expects (D175).

What differs natively, by design: a failed case runs no deferred block (its process ends, D97; a `temp_dir()` is still removed by the harness), a runtime error's message carries no values (an expected `[panic("…")]` passes when the native message and the expected one start the same way), and the cases of one run share a scratch directory on wasm32. A wasm32 module can start no process, so there `myla test` runs the harness itself, `<harness> --from <n>`: the harness runs the cases from `n` on in its own process, each between markers on stdout and stderr, and `myla test` cuts what it printed into the cases'; a case that ends the run (a runtime error, an `exit`, an expected `[panic(…)]` too) is reported as a child's would be, and the next run starts after it ([[MYLA-370]]). That is a run for each case that ends one, and one more; the report is the native one (every standard library module's agrees, 2026-11-09). A harness run by hand where no process can be started runs the cases in itself, in order, and the first runtime error ends that run. A harness that doesn't build (a case's function calling `main`, which the harness replaces) is kept in the scratch directory for a look.

### Expected failures

A case whose call must fail says so in its expected value: `[panic("division by zero")]` passes when the call ends in a runtime error with exactly that message (`assert`'s message, `panic`'s, an index error's as the interpreter words it), `[exit(3)]` when it ends with that exit status. The message and the status are literals. A call that returns instead, or fails differently, fails the case: `FAIL  div #3: expected runtime error 'division by zero', got 2`.

```myla
from std.process import exit

#test(1, 0)[panic("division by zero")]
#test(4, 2)[2]
fun div(a: int, b: int) -> int {
    return a / b
}

#test()[exit(3)]
fun leaves() {
    exit(3)
}

fun main() {}
```

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
| A `str` slice cutting a well-formed character (D174) | `a slice bound inside a character` | the same |
| Heap arena exhausted | — | `out of memory` (no position) |
