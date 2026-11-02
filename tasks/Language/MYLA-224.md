---
id: MYLA-224
title: "Line continuation inside brackets and after a trailing operator"
type: feature
status: todo
priority: medium
labels: [language, ergonomics, parser]
---
D104 (3) ([[MYLA-215]]): a newline inside `()` or `[]`, inside the braces of a struct or map literal, or after a binary operator that ends a line does not end the statement; a line that starts with an operator still starts a new statement (so `|>` and `>>` chains put the operator at the end of the line).

- [ ] The lexer's newline handling (a bracket depth; the last token's kind) and the grammar
- [ ] Tests for each case, including that a leading `-` still starts a statement; the language server's tokens and ranges unchanged
- [ ] [[Language]] pages and the skill

Order: after [[MYLA-219]] this touches only the self-hosted toolchain (checker, interpreter, lowering) and the grammar; done before it, the Python checker and interpreter need it too. Using it in `selfhost/` itself needs a seed that knows it ([[MYLA-218]]).
