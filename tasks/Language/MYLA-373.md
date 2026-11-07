---
id: MYLA-373
title: "Explicit type arguments on a call, parsed speculatively (D169)"
type: feature
status: todo
priority: medium
labels: [language, parser, checker, generics]
---
The owner's choice for [[MYLA-315]]'s open box, recorded as D169: `mk<int>()`, `deque.new<str>()`, `xs.mapped<str>(f)`. After a name or a method's name in an expression, `<` is tried as a type-argument list and kept when it closes with `>` and the next token is `(`; otherwise the parser goes back and reads a comparison. The design notes are in MYLA-315's "Explicit type arguments" section.

- [ ] The parser: the speculative type-argument list on a call and a method call (its errors during the attempt dropped), the AST's call node carrying the types
- [ ] The grammar (`grammar/myla.ebnf`), [[Language/Grammar]], the tree-sitter grammar generated from it (`test_grammar`)
- [ ] The checker: the explicit arguments seed `infer_generic_call`'s and `infer_generic_method`'s substitution; a count that doesn't match is an error; a method's arguments name its own type parameters
- [ ] Every runner: the instance is the one the arguments name (the native backend's `solve_targs` reads the checked types)
- [ ] Tests: parity programs (`let d = deque.new<int>()`, a call statement, `a < b` and `f(a < b, c > d)` still comparisons), error-corpus files for a count mismatch; [[Language/Generics]] and the skill
