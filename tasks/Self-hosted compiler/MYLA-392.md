---
id: MYLA-392
title: "Native: an await in a match nested in a match arm can't be lowered"
type: bug
status: review
priority: medium
labels: [lowering, async, native]
---
Found by the `std.http` lane ([[MYLA-347]]). An `await` inside a `match` nested in another `match`'s arm, matching on that arm's binding, stops `myla build` with "internal error: worker can't be lowered to the IR: a function used as a value" (from `name` in [[selfhost/lower.my]]). The interpreter runs it.

```myla fragment
import std.task as task

enum Cause { Stop, Code(int) }

async fun worker(r: Result<int, Cause>) -> int {
    match r {
        Ok(n) => { return n }
        Err(e) => {
            match e {
                Stop => {}
                Code(code) => {
                    print(code)
                    await task.sleep(1)
                }
            }
        }
    }
    return 0
}

#main
async fun main() { print(await worker(Err(Cause.Code(24)))) }
```

`std.http` decides outside the inner match (`accept_fate`, `answerable`) instead.

- [x] Root cause (the async split's handling of a binding of an outer arm, `anf.my` or the frame lowering), a fix, the program above as a parity program on every target

## Root cause and fix

The async split ([[selfhost/anf.my]]) rewrote a `match` statement with an `await` in an arm by its arms (`match_stmt`), and an arm block's trailing expression went through `arm_value`, which normalized it as an expression (`self.expr`) even when the match's value wasn't wanted. A trailing `match` with an `await` in an arm was therefore taken for a value: for the compiler (`value_matches`) `let %aw1 = match e { … }` with each arm ending in its value, and the void `await task.sleep(1)` became `let %aw2 = await …` with `%aw2` as the arm's value. A void `let` gets no slot, so reading `%aw2` reached `name` in [[selfhost/lower.my]], "a function used as a value". It wasn't the arm's binding: `let ee = e; match ee { … }` failed the same way, and a lone `match` (no outer one) worked, since `stmt` sends an `ExprStmt(match)` to `match_stmt(…, false)`.

`arm_value` now hands a trailing expression whose value isn't wanted to `stmt` as an `ExprStmt`, so a nested `match` is a statement match at every depth (the interpreter's async evaluator takes the same path).

## Evidence

- `await_in_a_nested_match` in [[tests/burn/test_compiler_parity.py]] (the task's program, a three-deep match whose innermost arm awaits, and a value match whose arm holds a nested match statement): before, `myla build` stopped with `internal error: deeper can't be lowered to the IR: a function used as a value` (and `worker` for the task's program); after, native code prints what the interpreter prints, `24 0 0 7 42 0 -1 abc 6 2 0`, on x86-64, aarch64 (`MYLA_TEST_TARGET=aarch64-linux`, qemu) and wasm32 (`MYLA_TEST_TARGET=wasm32-wasi`, Node).
- The bootstrap reaches its fixed point.
- The suites, at the batch's last commit: `scripts/test.sh fast` 714 tests, all pass but `test_embedded_std` (the embedded library isn't committed, by the batch's rules: the seed commit regenerates it) and once `test_time`'s `test_an_async_read_lets_the_other_tasks_run` under the load of the run (it passes alone, three times out of three); `test_compiler_parity`, `test_selfhost_cases`, `test_error_corpus`, `test_selfhost_checker`, `test_lsp`, `test_grammar` (with the tree-sitter CLI), `test_selfhost_codegen`, `test_selfhost_interp`, `test_xml`, `test_http`, `test_aarch64`, `test_wasm`, `test_native_runtime`: 808 tests OK; `scripts/test-target.py aarch64-linux` and `wasm32-wasi`: 21 of 21 suites each.
