---
id: MYLA-229
title: "`defer`"
type: feature
status: review
priority: low
labels: [concurrency, language]
---
D107 ([[MYLA-212]]): a way to run cleanup when a scope ends, also on failure and when a task is stopped (D97); the file handles of the standard library ([[MYLA-211]]) want it too. Its semantics need a decision of their own, proposed to the owner first:

- [ ] A proposal: scope (block or function), order (last in, first out), what ends a scope (`return`, `?`, `break`, a failure, a stop at a suspension point), what a deferred block may contain (`await`? `return`?), and its interaction with `become` (D87)
- [x] The owner's decision recorded (D135); then the implementation in every runner, with tests for each way a scope ends

## Decided (2026-11-05): D135

The owner chose the recommendation, Swift's model:
- **Scope:** `defer { … }` is block-scoped, and the blocks run last registered first.
- **When it runs:** at the block's end, `return`, `?`, `break` and `continue`, and when the task is stopped at a suspension point. Not on a failure, which ends the program.
- **What the block may contain:** no `await`, `return`, `break` or `continue`.
- **With `become`:** a `become` runs the pending blocks before its call.

- [x] A proposal

## Built (2026-11-05)

- `defer { … }` parses as a statement (`StmtKind.DeferS`); `defer` is a keyword only there, before `{`, so it stays a name elsewhere (the interpreter has a field of that name).
- The checker checks the block where it stands, with the names declared before it, and rejects `return`, `become`, `?`, `await`, `async let`, and a `break` or `continue` that would leave it (`Checker.defer_at`); a lambda inside is a function of its own. Every walker over statements (defaults, the actor analyses, captures, writes, the loader's renaming, the LSP) goes into the block.
- The interpreter keeps a scope's deferred blocks on its `RtFrame` and runs them, the last first, when the scope ends (`run_defers`, from `exec_block`, `eval_block_value` and, in async code, `close_scope` once the scope's children have ended), unless the program is failing; each runs with its scope cut back to the names it saw.
- The lowering emits them wherever a scope is left (`drop_owners`): at a block's end, `return` after its value, `?`, `break`, `continue`, a `become` after its arguments; each with the scopes cut back the same way (`emit_defers`). Every backend gets them from the IR.
- [[tests/burn/test_defer.py]]: each way a scope ends, the order, variables read at the end, the names it sees, nesting, loops, `become` 100000 deep, a block in an async function after its child, an async loop, a lambda, a `match` arm, and none on `exit` or a panic; the same program on aarch64 and wasm32 (`PROGRAMS["defer"]`); the errors; two corpus entries.

For the owner: D135 also says a deferred block runs "when its task is stopped at a suspension point (D96)". Under D96 nothing is stopped, and the only stop at a suspension point is D97's, when a failure elsewhere ends the program, which D135 excludes ("not on a failure"). So today the case can't arise and nothing runs for it; it needs a decision only if a stopping cancellation comes.

## Decided (2026-11-05): D141

The owner chose the recommendation for the question above: a deferred block runs on every way its block ends that the program survives; D135's "stopped at a suspension point" is dropped; a stopping cancellation, if one comes, runs them as a `return` does, as part of that decision. Nothing to build: it is what runs.
