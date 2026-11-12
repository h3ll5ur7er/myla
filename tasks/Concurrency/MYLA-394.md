---
id: MYLA-394
title: "D95's reentrancy warning misses a builtin mutator inside an expression"
type: bug
status: review
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

- [x] The review's blocker, fixed with [[MYLA-417]]: a mutator in the head of an `if` or a `while`, a match's scrutinee or a guard changes its field before the head is examined (`Reentrancy.head`, `value_changes`); six new `warnings_of` cases

## Review 2026-11-12

Reopened ([[Project/Review-2026-11-12]]): the warning got weaker with [[MYLA-417]]'s rewrite of the head.

- [x] **An `await` and a mutator of the checked field in one `if` or `while` head are no longer reported**: `while await p.charge() > 0 && self.items.pop() > 0 { }` after `if self.items.len() == 0 { return 0 }` warned before round 5 and doesn't now (5 warnings then, 1 now, on `repro-r5/checker/bug2_d95_await_in_head.my`), because `Reentrancy.head` makes a head's changes before its awaits. Walk the head in evaluation order
- [x] The new false positive of `repro-r5/checker/h2.my`

### Round 6 (checker lane)

`Reentrancy.ordered` walks every statement's expression in the order it runs (D193's order for a call: the receiver, then the arguments, then the call): an `await` starts its epoch once its operand has run; a mutator of a field of `self` (the builtin `push`, `pop`, `remove`, `append`, a `var self` method) or a method of `self` that changes fields changes them once its receiver and arguments have; and in a condition each field of `self` it reads, directly or through a local read from it, is examined where it is read (a mutator's field after its change, as before). The head of an `if` or a `while`, a match's scrutinee and guards, and now the left side of `&&` and `||` are conditions. It replaces `value`, `head`, `value_changes`, `call_changes`, `check` and `self_calls`, which made a statement's changes before or after all its awaits.

- `if self.items.len() > 0 && await p.charge() > 0 && self.items.pop() > 0` and `while await p.charge() > 0 && self.items.pop() > 0 { }` (after a check) warn again, and so does the same in a `let`.
- h2's false positive, `if self.items.len() > 0 && self.items.pop() > 0` after an `await` (the head checks again before it changes), is quiet; so is the older one of the same in a `let`, and `let x = self.items.pop() + await p.charge()`, which changes the field before the `await`.

Evidence:

- Tests first, in `selfhost/checker.my` (`warnings_of`, five new cases): the `while` head and the `if` head with the `await` and the mutator (`[]` at `6e699ca`, one warning now), the same in a `let` (one warning), the re-check in a head and in a `let` (two warnings before, `[]` now), the change before the `await` in one value (one warning before, `[]` now). The ten D95 cases of rounds 4 and 5 pass unchanged, and `test_selfhost_checker`'s `FIELD_MUTATOR_WARNINGS`.
- Reproducers: `bug2_d95_await_in_head.my`, 1 warning at the base (`as_statements`), 3 now (`in_while` at 10:53, `in_if` at 14:74, `as_statements`). `h2.my`: 2 at the base, both false (`head_rechecks` at 8:50, `let_rechecks` at 14:56); now 3, all true (`await_in_head`, `await_in_let`, `await_in_while`). `h1.my`: its 18 warnings W1 to W18 as before; `head_checks_and_changes`, a false positive at the base, is quiet, and `await_in_head` warns.
- [[Language/Concurrency]] says that a statement is followed in the order it runs. Suites: [[MYLA-544]]'s evidence (one run for the lane).
