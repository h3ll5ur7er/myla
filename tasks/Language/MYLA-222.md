---
id: MYLA-222
title: "`if` as an expression"
type: feature
status: done
priority: medium
labels: [language, ergonomics]
---
D104 (1) ([[MYLA-215]]): `let x = if c { a } else { b }`. Each branch block ends in an expression (its value), `else` is required in expression position, the branches' types must agree as `match` arms' do; no ternary operator.

- [x] Parser and grammar ([[grammar/myla.ebnf]], the tree-sitter grammar); checker; lowering (or a desugaring to `match` on `bool`)
- [x] Diagnostics: a missing `else`, branches of different types, a branch block that ends in a statement; error-corpus files
- [x] [[Language]] pages and the skill

Order: after [[MYLA-219]] this touches only the self-hosted toolchain (checker, interpreter, lowering) and the grammar; done before it, the Python checker and interpreter need it too. Using it in `selfhost/` itself needs a seed that knows it ([[MYLA-218]]).

## Evidence

- **How.** The parser desugars an `if` used as a value to a `match` on the condition ([[selfhost/parser.my]]: `if_expr`, `if_match`). `true => { then }`, and an `else` arm binding the name `%else`, which no source can spell. `else if` nests a match.
  - A block that gives a value (an `if` branch, the arm of a `match` used as a value) may end with an `if` statement whose every level has an `else`; it is that `if`'s value (`valued`).
  - A `match` that starts a statement keeps its arms as they are (`stmt_match`), so existing code parses to the same tree.
  - The checker words the match's errors for an `if` when it sees the `%else` arm (`if_worded`). The interpreter and the lowering need nothing new.
- **Grammar.** [[grammar/myla.ebnf]] and [[Language/Grammar]]: `if_expr` in `primary`, its conflict with `if_stmt` declared (the old one-rule conflict, now redundant, is gone). The tree-sitter grammar is regenerated.
- **Test first.** `tests/burn/test_if_expression.py`:
  - an `else if` chain returned from a function;
  - a nested `if` as a branch's value;
  - a branch with statements before its value;
  - a struct value;
  - `if` as an operand of `+` and on the right of `+=`;
  - the statement form unchanged.

  The output is the same in the interpreter and natively. Errors: no `else` ("an 'if' used as a value needs an 'else'"), branches of different types ("the branches of an 'if' have incompatible types …"), a branch without a value ("this 'if' is used as a value, so every branch must produce one"), and a non-`bool` condition. Before the change the program didn't parse ("expected an expression, found 'if'").
- **Error corpus.** `parse_if_expression_needs_else.my` and `type_if_branches_differ.my`.
- **Docs.** [[Language/Statements]] (with a tested example) and the myla skill. The burn suite passes, and the bootstrap reaches its fixed point with the new seed.

