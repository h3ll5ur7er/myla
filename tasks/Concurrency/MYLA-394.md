---
id: MYLA-394
title: "D95's reentrancy warning misses a builtin mutator inside an expression"
type: bug
status: backlog
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

- [ ] Count builtin mutators (`push`, `pop`, `remove`, `insert`, `append`, a `var self` method) on a `self` field wherever they appear in an expression; the program above and its variants in the checker's cases and `test_selfhost_checker`
