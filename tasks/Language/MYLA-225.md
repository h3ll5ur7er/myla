---
id: MYLA-225
title: "One trailing-comma rule"
type: feature
status: review
priority: low
labels: [language, ergonomics, parser]
---
D104 (4) ([[MYLA-215]]): a trailing comma is allowed after the last element of every comma-separated list (arguments, parameters, list, map and tuple literals, struct fields and literals, enum variants, generic arguments, patterns, imports). A one-element tuple keeps its comma rule.

- [x] An inventory of the lists and which accept a trailing comma today; the parser and grammar made uniform
- [x] Tests; [[Language]] pages

Order: after [[MYLA-219]] this touches only the self-hosted toolchain (checker, interpreter, lowering) and the grammar; done before it, the Python checker and interpreter need it too. Using it in `selfhost/` itself needs a seed that knows it ([[MYLA-218]]).

## Evidence

- **Inventory.** Before, these already took a trailing comma: list, map and tuple literals, struct and enum declarations, struct literals, tuple and function types, variant payloads, tuple and variant patterns, struct patterns. These didn't: call and attribute arguments, the parameters of functions, methods and lambdas, generic arguments, type parameters, import lists. A method's trailing comma was even a deliberate error (MYLA-180).
- **The change.** [[selfhost/parser.my]] stops each of those lists at its closing token after a comma: `call_args`, `expr_list`, `fun_decl`, `method_header`, `lambda_expr`, `generics`, `type_args`, and the import list at the end of the declaration. [[grammar/myla.ebnf]] and [[Language/Grammar]] say the same, and the tree-sitter grammar is regenerated. The error-corpus file `parse_method_params_trailing_comma.my` is gone (D104 (4) reverses MYLA-180). A one-element tuple keeps its comma rule.
- **Test first.** `tests/burn/test_trailing_commas.py`: one program with a trailing comma in every list, run alike by the interpreter, natively and by `myla test` (the `#test` attribute has one too); a lone or doubled comma stays a parse error. Before the change the program didn't parse ("expected an imported name"); now all pass.
- **Docs.** [[Language/Lexical-structure]] and the myla skill (its "don't write `f(a, b,)`" row is gone). The burn suite passes, and the bootstrap reaches its fixed point with the new seed.

