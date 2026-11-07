---
id: MYLA-303
title: "Decision: unit and integration tests beyond #test (test functions, teardown, fixtures, test programs)"
type: chore
status: done
priority: high
labels: [decision, testing, language, project-tool]
---
`#test(args)[expected]` is Myla's one testing construct: one line per case beside the function, checked at compile time, run by `myla test` in the interpreter, enforced on every value-returning function of the examples (D10, D116, D109, [[Language/Attributes-and-testing]]). It is excellent for pure functions and useless for the rest: a test that has to make a directory, write files, start a child process, read them back and clean up can't be a line, so the repository falls back to helper functions (the harvested factories `checker_on`, `parser_on`, `expr_of` in `selfhost/`, `test_func` in [[selfhost/ir.my]]), and every test that needs a process or a file system lives in Python (`tests/burn/`, 23,000 lines). This task designs the rest of the system, for the owner's decision, in the shape the reactor's design took ([[MYLA-258]]).

[TOC]

## What holds today (measured on master `0054e34`)

A probe (`scratchpad/own/design/probe2.my` of the review session; the same shapes are in the examples below) shows how far `#test` already reaches:

| Need | Today | How |
| --- | --- | --- |
| A test that is a body, not a line | **works** | `#test()[()]` on a function without parameters and without a result (D138): the case passes when the function returns, fails on a runtime error (`assert`, `panic`) |
| A fixture built for a case | **works** | a call in the case's arguments: `#test(db_with(3))[3]`; the factories of `selfhost/` do this on 145 cases of `checker.my` |
| A test that reports why it failed with `?` | **works** | `#test()[Ok(())]` on `fun t() -> Result<(), str>`: `Err("why")` is `FAIL  t #1: expected Ok(()), got Err('why')` |
| Teardown | **works when the case passes** | `defer { fs.remove_dir_all(d) }` (D135) |
| Teardown when the case fails | **doesn't run**: the scratch directory stays | a failure runs no deferred block (D141); `myla test` catches the failure at the case and goes on, so nothing ever unwinds the case's frames |
| A case on an `async fun` or an actor | refused | `'#test' can't run an async function` (D116) |
| A case that expects a panic | impossible | a runtime error always fails the case |
| A test of a built program (output, exit status, stdin) | Python only | `tests/burn/test_stdio.py` and the rest |
| Tests run natively, on another target | Python only | `myla test` interprets; `myla build` drops every case |
| Choosing which cases run | no | `myla test file.my` runs all of a file |
| A message that shows the values | `assert(c, "msg")` only | no `expect_eq`; `Format` (D139) and bounds that admit trait methods ([[MYLA-291]]) now make a generic one possible |

So the system is three quarters there: what is missing is a name for the test function, the unwinding of a failed case, async cases, expected failures, a place and a runner for integration tests, and native runs.

## Principles

1. **One construct.** `#test` stays the only test attribute; the rest is its forms and a library. No `test` keyword, no `#before`/`#after`, no test registry (there are no globals to register in, D28).
2. **Fixtures are values.** A fixture is a function's result (`fun fresh_db() -> Db`), copied into each case (value semantics): nothing is shared between cases unless an actor is, so cases can't leak into each other.
3. **A failure is a runtime error.** No exceptions, no catch: a case fails the way a program fails, and `myla test` is the one place that goes on after a failure. What it owes the failed case is to run its deferred blocks, as a `return` would (D141 leaves that stop to "a decision of its own": this is it).
4. **Sugar and library, not runtime.** Everything below is parser sugar, a checker rule or Myla code in `std.test`; nothing costs a backend anything (the reflection's "prefer what costs nothing per target").
5. **Every runner.** A case that passes in the interpreter passes natively on every target, and `myla test` can prove it.

## Questions

1. The test function: how a body-shaped test is written and reported.
2. What happens when a case fails: deferred blocks, scratch directories.
3. Assertions and expected failures: `std.test`, a case that expects a panic.
4. Async cases and actors.
5. Integration tests: test programs in a project, the built program under test.
6. Native runs and the other targets.
7. Selection and reporting.

## Options and recommendations

### 1. The test function

- **A. `#test` with nothing after it**, on a function without parameters, is sugar for `#test()[()]`: the function is a test, named by its name, reported as `PASS  writes_and_reads`. A result type of `Result<(), E>` is allowed too: `Ok(())` passes, `Err(e)` fails with `e` rendered (`E` must be `str` or `Format`). Any other signature is the existing error.
- **B. A `test` declaration** (`test "writes and reads" { … }`): a new declaration kind, a string name, a parser rule, a grammar rule, tree-sitter, the skill. Reads well, costs a keyword and teaches a second way to write a function.
- **C. A second attribute** (`#test_fn`, Rust's `#[test]`): one more name for the same idea.

**Recommendation: A.** It is what works today without the `()[()]` noise, it keeps "a test is a function" (fixtures, `defer`, `?`, methods all apply unchanged), and `myla test` already reports by function name. The checked name is the test's name; snake_case reads as a sentence (`parses_empty_input`). The function keeps `fun`'s rules: it may be called by other code (a test is an ordinary function), and `build` drops it with the cases.

```myla
import std.fs as fs
import std.test as test

#test
fun writes_and_reads() {
    let d = test.temp_dir()
    let w = fs.write_to_file(d + "/a.txt", "hello")
    test.expect_eq(fs.read_to_string(d + "/a.txt"), Ok("hello"))
}

#test
fun rejects_a_bad_port() -> Result<(), str> {
    let p = parse_port("80x")?        // an Err fails the test with its message
    return Err(f"accepted {p}")
}
```

### 2. When a case fails

- **A. The runner unwinds the case.** A failure inside a case (a runtime error, `exit`, a failed `expect`) ends the case as a `return` would have: the deferred blocks of every frame between the failure and the case's function run, innermost first, then the case is reported as failed. D141 is extended: "a failure ends the program at once, except under `myla test`, where it ends the case, running its deferred blocks". A deferred block that fails itself is reported with the case and the unwinding goes on.
- **B. `#after` / `#before` functions** per file, run around every case, with the state passed as a value. Two more attributes and a protocol for the state; cleanup that doesn't see what the case made.
- **C. Nothing**: tests clean up by not failing, or leave their files.

**Recommendation: A**, plus `test.temp_dir()` in `std.test`: a directory of its own per call under the system's temporary directory (`$TMPDIR`, `/tmp`; on wasm32 a directory under the working one), registered with the runner, removed when the case ends however it ends, so the common teardown needs no `defer` at all. In the interpreter this is a loop over the case's frames; natively (question 6) the harness unwinds the same way. The ordinary program is untouched: a failure outside `myla test` ends it at once as D97 and D141 say.

### 3. Assertions and expected failures

- `std.test`: `expect(cond: bool, msg: str = "expectation failed")`, `expect_eq<T: Eq + Format>(got: T, want: T)` ("expected 3, got 4" with the values in their `Format`), `expect_ne`, `fail(msg: str)`, `temp_dir()`, and later `expect_err`/`expect_some` as `match` sugar shows a need. `assert` stays what it is: a program's own check, which a case may also use. Written in Myla; a failed expectation is a runtime error whose message the report shows (`FAIL  count_rows: expected 3, got 4`), with the position of the `expect` call as every runtime error has.
- **Expected failures.** A case whose function must fail:
  - **A. `[panic("message")]` as the expected value**: `#test(1, 0)[panic("division by zero")]` passes when the call ends in a runtime error with exactly that message (interpreter and native messages differ in values, [[MYLA-17]]: compare the native one by prefix, or require the interpreter's); `[exit(3)]` likewise. Reads as what it is, needs the checker to know two more forms in the `[…]`.
  - **B. A `#test` form `#test_fails(args)["message"]`**: a second attribute.
  - **C. `Result` only**: a function that may fail returns `Result`, and a case checks `Err`. True for library code; useless for `assert`, index errors and `panic`.

**Recommendation: A**, with the message compared exactly in the interpreter and by the native message's prefix natively (the same rule the error corpus uses, `//~ native:`).

### 4. Async cases and actors

- **A. `#test` on an `async fun` test function** (no parameters): `myla test` runs it as the entry task of a program of its own (`#main async fun`), every task it starts joined before the case ends, on the interpreter's one-worker order (deterministic, D110); natively on `MYLA_THREADS` workers. `#test(args)[expected]` on an async function with parameters is allowed by the same rule. An actor's method stays out (its receiver is a running actor); an actor is tested through an async test function that makes it.
- **B. Stay as D116 is**: async code tested only by programs.

**Recommendation: A.** The reactor made async tests cheap: the runner is the interpreter's existing task loop, one case one program.

```myla
#test
async fun counts_in_parallel() {
    let c = Counter { n: 0 }
    async let a = bump(c, 100)
    async let b = bump(c, 100)
    await a
    await b
    test.expect_eq(await c.get(), 200)
}
```

### 5. Integration tests

The burn suite's Python tests do three things Myla can't do about itself today: run a built program with stdin and compare its output and exit status; drive the CLI and the project tool; compare the interpreter with native code on a corpus. Two forms, both under `tests/` in a project, both run by `myla test` after `src/`:

- **Test programs with their expected output:** `tests/greets.my` is a program whose trailing comment block says what it prints and how it ends, the convention the docs' code blocks already use (D114, `test_doc_blocks.py`) and the error corpus's `//~` directives extend:

  ```myla
  from std.io import stdin
  fun main() {
      var r = stdin()
      match r.read_line() { Ok(Some(l)) => print("hello " + l), _ => print("nobody") }
  }
  // input:
  // world
  // output:
  // hello world
  // exit: 0
  ```

  `myla test` runs it in the interpreter and, with `--native`, as a built binary, and compares. A `// output:` block without `// exit:` means 0; `// stderr:` holds what a runtime error prints. This is the examples' own convention (`test_examples_run.py`'s pinned output) brought into the language, and it is what most parity tests in `tests/burn/` are.
- **Test functions that drive the built program:** `tests/cli.my` is a file of `#test` functions; `std.test.program()` gives the path of the project's program, built by `myla test` before the tests run (`build/<name>`), so a test can run it with `std.process.command(test.program()).stdin("…").run()` and expect on its output, in a `temp_dir()`. The project's library is imported as from `src/main.my`.

**Recommendation: both**, the first as the step that pays first (it replaces the pinned outputs and the parity corpora), the second for the CLI and the project tool. `tests/` is a convention of the project layout (D73 (2)); a single file has no integration tests.

### 6. Native runs

Today `myla test` interprets, and the interpreter is the oracle; nothing in the language runs a case natively. The burn suite does it from Python by building programs and comparing.

- **A. `myla test --native` (and `--target t`)**: for each file, the compiler builds a harness program: a `main` that runs every case in source order, compares the result with the expected value (derived `Eq` and `Format` give the comparison and the report's values), unwinds a failed case's deferred blocks (question 2: a case's frames are the harness's own, so the unwinding is a `return` from the case with the error recorded), prints the same report as the interpreter and exits 1 on a failure. Test programs (question 5) are built and run with their expected output. The interpreter's and the native report must agree, which is the parity check the Python suites do, now in `myla` itself.
- **B. Interpreter only**, as today, with the Python suite keeping native parity.

**Recommendation: A, as the third step** (after 1–4 and 5). It is the piece that lets the parity tests of `tests/burn/` move into Myla, one file at a time, and run on aarch64 and wasm32 through the same flag ([[MYLA-297]]).

### 7. Selection and reporting

- `myla test [file] --only <text>` runs the cases whose function name (or test program path) contains the text; `--list` prints the names without running. The report stays as it is (`PASS  name #n (label)`, the summary line), with a test function reported without `#n` and test programs as `PASS  tests/greets.my`. Nothing else: no skips, no expected-failure marks, no random order (a case that must not run is removed; D110's order is the interpreter's).
- Each case's standard output is shown only when the case fails (today it interleaves with the report).

## What is left out, on purpose

- Mocking and dependency injection: a fixture is a value and a function is a function; a seam is a parameter.
- Property-based or generated tests: [[MYLA-184]]'s harvester generated cases from recordings; a generator attribute would be a decision of its own.
- Running cases in parallel: cases run in source order, one at a time; an async case may use every worker inside.
- Cases on generic functions, actor methods and `#test` on an `impl` block: unchanged (D116).
- A `tests/` directory for a single file: the file's own cases are its tests.

## Steps, if decided

1. **Test functions and failures** (parser sugar for a bare `#test`; `Result<(), E>` cases; `[panic(…)]`/`[exit(n)]` expected values; the runner unwinds a failed case's deferred blocks; `std.test` with `expect`, `expect_eq`, `expect_ne`, `fail`, `temp_dir`; `--only`, `--list`; output shown on failure only). Interpreter only. The error corpus and `test_examples_tests.py` extended; the Language page and the skill updated.
2. **Async cases** (D116 amended): the case as the entry task; actors through them.
3. **Test programs and `tests/`** in projects: the output-comment convention from `test_doc_blocks.py`, `std.test.program()`, `myla test` building the program first.
4. **`myla test --native` and `--target`**: the harness; the interpreter's report equal to the native one on every corpus file; then the Python parity tests move file by file ([[MYLA-288]]'s direction), the burn suite shrinking to what only Python can do (the recordings, CI glue).

Each step keeps the examples' rule (every value-returning function has cases) and adds its own: every `std` module with I/O gets test functions (`fs`, `io`, `process`, `time`, [[MYLA-295]]).

## Decisions asked of the owner

- [x] 1. A bare `#test` on a parameterless function as the test function (A), with `Result<(), E>` results
- [x] 2. A failed case unwinds its deferred blocks under `myla test` (A, D141 amended); `test.temp_dir()` removed by the runner
- [x] 3. `std.test`'s first functions; `[panic("…")]` and `[exit(n)]` as expected values (A)
- [x] 4. `#test` on async functions as the entry task (A, D116 amended)
- [x] 5. `tests/` in a project with test programs (`// input:`, `// output:`, `// exit:`) and `test.program()`
- [x] 6. `myla test --native` / `--target` with a generated harness, as step 4
- [x] 7. `--only`, `--list`, output on failure only; no skips

## Decided (2026-11-07)

The owner took all seven recommendations; D162 records them. The steps are the children below.

## Children

- [[MYLA-304]] step 1: test functions, failures that unwind, `std.test`, `[panic]`/`[exit]`, `--only`/`--list`, output on failure
- [[MYLA-305]] step 2: async cases
- [[MYLA-306]] step 3: `tests/` in a project, test programs, `test.program()`
- [[MYLA-307]] step 4: `myla test --native` and `--target`
