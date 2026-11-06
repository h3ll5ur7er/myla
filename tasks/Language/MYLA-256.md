---
id: MYLA-256
title: "A `guard` statement, as Swift has"
type: feature
status: done
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
- [x] Parser, checker (the else block must leave), lowering, interpreter; error-corpus examples; the tree-sitter grammar and the editor

## Decided (2026-11-05): D137

Rust's let-else: `let P = e else { … }`, whose `else` block must leave the block. No `guard` keyword, and no plain-condition form.

## Built (2026-11-05)

- **Parser** ([[selfhost/parser.my]]): `let` followed by a variant pattern (a name with `(` or `.` after it, or `.Variant`) is a let-else, `let_else`. Its `match` gets an empty first arm and a second arm binding `%letelse`. At the end of the block, `fold_let_else` gives that first arm the statements after it, the last let-else first.
- **Checker** ([[selfhost/checker.my]]):
  - the `else` arm must leave its block (`block_leaves`: `return`, `become`, `break`, `continue`, a call that never returns, or an `if` whose every branch leaves);
  - a pattern that always matches gets let-else wording (`if_worded`);
  - a function may end in a `match` whose every arm returns (`match_returns`), which the folded form needs.
- **The rest:** the lowering and the interpreter needed nothing.
- **Grammar:** `let_else` in [[grammar/myla.ebnf]] and [[Language/Grammar]], restricted to variant patterns so tree-sitter tells it from `let x = …`; the tree-sitter grammar is regenerated.
- **Docs:** [[Language/Statements]], "let-else".

Evidence:
- **`tests/burn/test_let_else.py`,** written first, failed at the parser in all 6 cases. Its program covers:
  - early returns over two patterns;
  - `continue` and `break` in loops;
  - a let-else inside an `if` used as a value;
  - the `else` calling `panic`;
  - a let-else in `main`.

  It now prints the same in the interpreter and natively (x86-64, and aarch64 checked by hand), and its five error cases give their messages.
- **Error corpus:** three new files (`type_let_else_must_leave`, `type_let_else_irrefutable`, `parse_let_else_needs_else`).
- **Suites:** test_if_let, test_error_corpus, test_grammar, test_doc_blocks and the parser and checker gates pass.

## Evidence (review 2026-11-06)

- [x] `exit` leaves a block (reopened by [[Project/Review-2026-11]]): `std$process$exit` is a diverging call in [[selfhost/checker.my]], so `let … else { exit(3) }` and a function ending in `process.exit(2)` check, as the page said; `test_let_else.test_exit_leaves_the_block`. The variant-only pattern rule is now stated on [[Language/Statements]]
