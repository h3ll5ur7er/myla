---
id: MYLA-256
title: "A `guard` statement, as Swift has"
type: feature
status: backlog
priority: low
labels: [language, ergonomics, design]
---
The owner's idea (2026-11-03), for after the runtime's port ([[MYLA-162]]): an early exit that keeps the happy path unindented, with what it binds in scope for the rest of the block.

```myla
fun area(s: Option<Shape>) -> Result<int, str> {
    guard let Some(shape) = s else {
        return Err("no shape")
    }
    guard shape.width > 0 else {
        return Err("empty")
    }
    return Ok(shape.width * shape.height)    // `shape` is in scope here
}
```

Questions for the design round (a decision before the implementation):
- **The forms:** `guard cond else { … }` and `guard let P = e else { … }`, mirroring `if let` (D104 (5), [[MYLA-226]]), with any refutable pattern (`guard let Ok(v) = r else { … }`, `guard let Circle(c, r) = s else { … }`). Several conditions at once (`guard let a = x, b > 0 else`), as Swift allows?
- **The `else` block must leave:** `return`, `become`, `break`, `continue`, `panic`/`unreachable` or a call that never returns; the checker rejects one that falls through, as Swift does. That needs the checker's "every path ends" analysis ([[Language/Statements]]) on the block.
- **Spelling:** Swift's `guard … else`, or Rust's `let P = e else { … }` (let-else), which needs no new keyword and reads as the `let` it is. `guard` would be a new keyword (breaking any program using it as a name; the corpus can tell how often).
- **Against what exists:** `?` already covers `Option`/`Result` when the function returns the same kind; `guard` is for everything else (a different error, a message, a loop's `continue`) and for plain conditions.
- **Lowering:** sugar over `match` (as `if let` is): `match e { P => { rest of the block }, _ => { else block } }`, so the bindings' ownership and drops follow the existing rules; the interpreter and the IR need nothing new.

- [x] Design round and a decision (D137) on the spelling and forms; the examples and errors on [[Language/Statements]] come with the implementation
- [ ] Parser, checker (the else block must leave), lowering, interpreter; error-corpus examples; the tree-sitter grammar and the editor

## Decided (2026-11-05): D137

Rust's let-else: `let P = e else { … }`, whose `else` block must leave the block. No `guard` keyword, and no plain-condition form.
