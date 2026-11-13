---
id: MYLA-435
title: "A failing expect points at its caller"
type: improvement
status: review
priority: low
labels: [std, diagnostics]
---
[[MYLA-324]]'s follow-up from [[Project/Review-2026-11-09]]: `opt.expect("…")` failing reports a position inside `lib/std/option.my`, not the call.

Reproducer (checked 2026-11-13, [[MYLA-554]]):

```myla fragment
fun find(xs: [int], v: int) -> Option<int> {
    for i in 0..xs.len() {
        if xs[i] == v {
            return Some(i)
        }
    }
    return None
}

fun main() {
    let at = find([1, 2, 3], 7).expect("7 is in the list")
    print(at)
}
```

`myla run`, and the binaries of `myla build`, `myla build -g` and `myla build --checked`, all print the `panic` inside `Option.expect` and exit with status 1:

```
runtime error: 7 is in the list
  --> <myla>/std/option.my:79:26
```

where the caller's position is `expect.my:11:33`. `Result.expect` fails the same way, at `option.my:153`.

There is no `unwrap` in Myla (the skill says to write `expect`, `unwrap_or` or a `match`; [[Language/Standard-library/Option]] has no `unwrap` either); the functions of std.option that end in a `panic` of their own are `Option.expect` and `Result.expect`.

- [x] A way for a library function to report its caller's position (as Rust's `#[track_caller]`), on every runner
- [x] `Option.expect` and `Result.expect` use it, and the error-corpus or parity tests pin the caller's position for both, interpreted and natively

(The reproducer's caller's position is `expect.my:11:39`, the call's `(`: every runtime error at a call points there, [[Language/Attributes-and-testing#runtime-errors]].)

## What was built

**`#track_caller`** ([[Language/Attributes-and-testing#track_caller]]), an attribute of a function or a method of a type's own `impl`, generic or not. Its `panic`, `assert` and `unreachable` fail at the position of its call; a call from one such function to another passes its own caller's position on, so the error lands in the first function that isn't one. std.option's `Option.expect` and `Result.expect` ([[lib/std/option.my]]) and std.args' declaring methods, their checks and `Args`' accessors ([[lib/std/args.my]], [[MYLA-553]]) carry it.

- **Interpreter** ([[selfhost/interp.my]]): `tracks` (per function), `note_caller` at a direct call, a method call and a type's function call (the call's node, or the running function's own `%caller` when it reports one too), `bind_caller` making it the frame's variable `%caller` as `%env` is, `failure_at` for the three failures. A lambda has frames of its own, so its failures keep their position, natively too.
- **Native, every target** ([[selfhost/lower.my]], [[selfhost/ir.my]], the three back ends): such a function gets a hidden last argument word, `__caller`, the address of a position record (`[file str][line][col]`, [[Architecture/Native-backend#runtime-error-positions]]). `direct_call` passes `caller_position`: the new instruction `%t = position @line:col` (`leaq .L<fn>_p<n>(%rip)`, `adr`, `i32.const`), the record of the call in the caller's file, or in a tracked function its own `__caller`. Its failures end in the new terminator `panic %msg at %pos` (`panic_term`), handing `__panic` that word where `panic %msg @pos` hands it a record of its own. x86-64 never rematerializes a `position` (its record is named for the function's file, known only once the function is emitted).
- **Checker** ([[selfhost/checker.my]]): the attribute takes no arguments; it is a type error on an async function and an actor's method (their calls may start a task or go through the actor), on a method of a trait's impl (called through a bound, `==`, `for`, which pass no position), on the entry point (nothing calls it), and such a function used as a value, partially applied or called by `become` (`'f' reports its caller's position ('#track_caller'): it can only be called`, with `help: call it in a lambda`).

## Proposal (open for the owner): the form

*Accepted by the owner (2026-11-13): as built, decision D203.*

Recommended and built: **an attribute open to every program, `#track_caller`**, with Rust's name and meaning for `panic`, `assert` and `unreachable`. A program's own checking helper (a test's `expect_eq`, a validator) points at its caller as `expect` does, and the cost is one word passed per call of such a function (a `leaq`), nothing elsewhere.

Alternatives:
1. **The same attribute for `std` only**, refused elsewhere as the raw-memory primitives are (D152). The implementation is the same; it would only take the feature from programs.
2. **A value: `caller()` giving a `Location { file, line, col }`, and `panic_at(loc, msg)`** (Rust's `Location::caller()`). More general (a logger could print it), but it needs a prelude type and the same hidden argument to know a caller; it can come later on top of this one.
3. **Implicitly for all of `std`: an error reports the first frame outside the standard library.** Natively that is a walk of the stack with a table of call sites per return address (unwinding information), large and different on wasm32; the interpreter would need a call stack it doesn't keep.
4. **Inline `expect` into its callers.** The inliner keeps to one module so that positions stay right, and the inlined `panic` would still be std's position.

Left out, each a type error today, that could be lifted later: a function value of such a function (it would need an adapter passing the position where the value is made, or none), and its use as a trait's method.

**A decision row for the integrator:** "**`#track_caller`** ([[MYLA-435]]): a function or a method of a type's own `impl` under `#track_caller` reports its caller's position: its `panic`, `assert` and `unreachable` fail at its call, and a call from one such function to another passes its own caller's position on; the other runtime errors in it keep their position. Open to every program. Natively the position travels as a hidden last argument word, the address of the call's position record; so it is refused on an async function, an actor's or a trait impl's method and the entry point, and such a function can only be called (no function value, partial application or `become`). std.option's `expect`s and std.args' spec and name checks use it" | Rationale: "The review's finding on `expect` ([[Project/Review-2026-11-09]], [[MYLA-553]]): a failing `expect` pointed into `lib/std/option.my`. Rust's form, open to programs as Rust's is: a checking helper of a program's own points at its caller too; a std-only attribute would cost the same. Alternatives: a `Location` value (`caller()`, later on top of this), a stack walk to the first frame outside std (unwind tables, large, not on wasm32), inlining (positions stay the callee's)".

Follow-up: [[MYLA-628]], the other library panics that are the caller's mistake (std.list's `insert`, `remove_at`, `chunks`, `windows`; std.test's expectations).

## Evidence

- **Failing first.** At `aef0b21`: the reproducer printed `  --> <myla>/std/option.my:79:26` interpreted and natively, `Result.expect` `option.my:153:28`, a bad std.args spec `<myla>/std/args.my:142:18`; `#track_caller` was `unknown attribute '#track_caller'`. The new parity test `test_track_caller_reports_the_callers_position` ([[tests/burn/test_compiler_parity.py]]) failed in each of its cases then.
- **The tests now.** The error corpus ([[tests/burn/test_error_corpus.py]], 370 tests) passes with its new files: `runtime_option_expect_at_the_caller.my`, `runtime_result_expect_at_the_caller.my`, `runtime_args_spec_at_the_caller.my`, `runtime_track_caller.my` (each with its `.stderr` pinned and the native binary's two lines held to the interpreter's: `  --> …:16:39`, the call's `(`), and the type errors `type_track_caller_as_a_value`, `_partial`, `_become`, `_on_the_entry_point` and `_where_it_cannot_stand` (five errors in one file); with `MYLA_TEST_TARGET=aarch64-linux` and `wasm32-wasi` the nine `caller` files pass too. The parity test's fourteen cases (both `expect`s, `panic`, `unreachable`, through a tracked function, through an untracked one, a generic type's method, a generic function, another module's function, an index's own position, a lambda's own position, an `expect` in a task, a std.args spec, an undeclared name through `get_or`) pass interpreted and natively, three of them in a `--checked` build too, and the whole test with `MYLA_TEST_TARGET=aarch64-linux` (qemu) and `wasm32-wasi` (Node). The corpus files by hand: the same two lines from `myla run`, `myla build`, `myla build -g`, `--target aarch64-linux` and `--target wasm32-wasi`. std.option's 17 and std.args' 58 cases pass interpreted, `--native`, and natively on aarch64 and wasm32.
- **Suites** (a shared machine, load 3 to 5): `scripts/test.sh fast`: `Ran 904 tests in 647 s, OK (skipped=3)` (with `selfhost/embedded_std.my` as the bootstrap regenerated it, left out of the commits). `scripts/test.sh` once: `Ran 1661 tests in 1587 s, FAILED (failures=2)`: `test_selfhost_codegen.test_children_run_in_parallel` (cpu 0.95 s against wall 0.76 s; alone it passes) and `test_std_cache.test_an_error_in_a_body_read_late_is_at_its_place`, whose program failed inside `Option.expect` to have an error in a library body read late; it now fails inside `xs.chunks(0)` (std.list) and passes.
- **Bootstrap**: `byte-identical fixpoint reached` after each step. The cost of the hidden word, the same compiler sources built against std.option and std.args without and with the attribute: 26406078 against 26408927 bytes of stage assembly (+0.011 %, a `leaq` at each call of `expect` and of the std.args methods). The x86-64 seed grew from 12920382 to 12955779 bytes with the compiler's new code.
- **Staging.** The bootstrap can't build the library's `#track_caller` with the seed of `aef0b21` (`unknown attribute '#track_caller'`), so the compiler is its own commit, then a `Stage:` commit with the seeds, then the library's use (D156's exception).
