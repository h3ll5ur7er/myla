---
id: MYLA-222
title: "`if` as an expression"
type: feature
status: todo
priority: medium
labels: [language, ergonomics]
---
D104 (1) ([[MYLA-215]]): `let x = if c { a } else { b }`. Each branch block ends in an expression (its value), `else` is required in expression position, the branches' types must agree as `match` arms' do; no ternary operator.

- [ ] Parser and grammar ([[grammar/myla.ebnf]], the tree-sitter grammar); checker; lowering (or a desugaring to `match` on `bool`)
- [ ] Diagnostics: a missing `else`, branches of different types, a branch block that ends in a statement; error-corpus files
- [ ] [[Language]] pages and the skill

Order: after [[MYLA-219]] this touches only the self-hosted toolchain (checker, interpreter, lowering) and the grammar; done before it, the Python checker and interpreter need it too. Using it in `selfhost/` itself needs a seed that knows it ([[MYLA-218]]).
