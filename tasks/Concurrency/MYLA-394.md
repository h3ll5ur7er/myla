---
id: MYLA-394
title: "D95's reentrancy warning misses a builtin mutator inside an expression"
type: bug
status: todo
priority: low
labels: [checker, concurrency, warnings]
---
Found by the generic-actors lane ([[MYLA-386]]). The D95 warning (a field read before an `await` and changed after it) sees a builtin mutator on a `self` field only as a whole statement (`StmtKind.ExprStmt`): `call_changes` in the checker's `Reentrancy` walk doesn't look inside expressions.

```myla fragment
async fun sell(var self, p: Pay) -> int {
    if self.items.len() == 0 { return 0 }
    let paid = await p.charge()
    let x = self.items.pop()      // no warning; `self.items.pop()` as a statement warns
    return x
}
```

`return Some(self.items.pop())` is missed the same way.

- [x] Count builtin mutators (`push`, `pop`, `remove`, `insert`, `append`, a `var self` method) on a `self` field wherever they appear in an expression; the program above and its variants in the checker's cases and `test_selfhost_checker`

## Evidence

- The `Reentrancy` walk's `call_changes` now takes, besides the calls of `self`'s methods, every call of a mutator on a field of `self` inside the expression (`self_calls` returns those too): the builtin `push`, `pop`, `remove`, `append` (`mutating_builtin`), and a `var self` method of the field's type, which the checker records by call id while it checks an actor's methods (`mutating_calls`, set in `mark_call`). The statement form and the synchronous methods' `Effects` take the `var self` methods the same way.
- Before (master `0eeea06`), `build/myla check` gave no warning for `let x = self.items.pop()`, `return Some(self.items.pop())…`, `self.items.insert(0, 5)` or `self.items.sort()` after an `await` (each with `self.items` checked before it); after, each gets "'self.items' was checked before an 'await' and is changed after it …".
- `tests/burn/test_selfhost_checker.py`: `FIELD_MUTATOR_WARNINGS` and `test_warnings_of_field_mutators` (`pop` in a `let`, in a `return`, a struct's `var self` method as a statement and inside an expression; quiet when checked again after the `await` or changed before it). Before the change the four warning cases failed (no warnings), after it all pass; the module's 7 tests pass. Checker cases: `warnings_of` (4; the fourth, `self.items.push(self.c.bump())`, warns for both fields: a statement mutator's arguments are walked too).
- [[Language/Concurrency]] says what changes a field.

Suites at the batch's tip: the bootstrap's fixed point; `scripts/test.sh fast` 714 OK (with the embedded library regenerated); `tests.burn.test_compiler_parity`, `test_selfhost_cases`, `test_error_corpus`, `test_selfhost_checker`, `test_lsp`: 673 OK.

## Review 2026-11-09

Not ready ([[Project/Review-2026-11-09]]): D95 misses a mutator in the head of `if`, `while` and `match`. The fix is in [[MYLA-417]].

- [ ] The review's blocker, fixed with [[MYLA-417]]
