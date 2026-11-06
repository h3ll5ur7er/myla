---
id: MYLA-226
title: "`if let` and `while let`"
type: feature
status: done
priority: medium
labels: [language, ergonomics]
---
D104 (5) ([[MYLA-215]]): `if let Some(x) = e { … } else { … }` and `while let Some(x) = next(it) { … }`, as sugar over `match`.

- [x] Parser and grammar; desugaring (or checking and lowering) with the pattern's bindings scoped to the block; refutable patterns only (an irrefutable one is a warning or an error, decided here)
- [x] Tests and error-corpus files; [[Language]] pages and the skill

Order: after [[MYLA-219]] this touches only the self-hosted toolchain (checker, interpreter, lowering) and the grammar; done before it, the Python checker and interpreter need it too. Using it in `selfhost/` itself needs a seed that knows it ([[MYLA-218]]).

## Evidence

- **How.** The parser desugars both forms ([[selfhost/parser.my]]: `let_pattern`, `let_match`, `if_let_stmt`, `if_let_expr`, `while_let_stmt`):
  - `if let P = e { A } else { B }` is `match e { P => { A }, %iflet => { B } }`, an empty block without `else`, and an `else if` nests.
  - `while let P = e { body }` is `while true { match e { P => { body }, %whilelet => { break } } }`.

  The pattern's bindings are scoped to the arm, so to the block. An `if let` used as a value follows the `if` expression's rules ([[MYLA-222]]).
- **Irrefutable patterns, decided here: an error.** The checker's redundancy check already rejects the second arm when `P` always matches; `if_worded` turns that into "the pattern of this 'if let' always matches: use 'let' instead" (for `while let`: "use 'while true' and 'let'"), pointing at the pattern.
- **Grammar.** [[grammar/myla.ebnf]] and [[Language/Grammar]]: `let_cond = "let" pattern "=" cond` in `if_stmt`, `while_stmt` and `if_expr`. The tree-sitter grammar is regenerated.
- **Test first.** `tests/burn/test_if_let.py`:
  - `if let` with and without `else`;
  - an `else if let` chain returned as a value;
  - a `while let` with `continue`, and one over list elements stopping at the first non-matching one;
  - an `if let` value with a fallback;
  - a tuple pattern with a nested `Some`.

  The output is the same in the interpreter and natively. Errors: an always-matching pattern (in both forms), a binding used after its block ("unknown name"), a type mismatch, and a missing `=`. Before the change nothing parsed ("expected an expression, found 'let'").
- **Error corpus.** `type_if_let_irrefutable.my` and `parse_if_let_needs_equals.my`.
- **Docs.** [[Language/Statements]] (a section with a tested example) and the myla skill. The burn suite passes, and the bootstrap reaches its fixed point with the new seed.

