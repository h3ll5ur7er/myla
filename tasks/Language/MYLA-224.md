---
id: MYLA-224
title: "Line continuation inside brackets and after a trailing operator"
type: feature
status: done
priority: medium
labels: [language, ergonomics, parser]
---
D104 (3) ([[MYLA-215]]): a newline inside `()` or `[]`, inside the braces of a struct or map literal, or after a binary operator that ends a line does not end the statement; a line that starts with an operator still starts a new statement (so `|>` and `>>` chains put the operator at the end of the line).

- [x] The lexer's newline handling (a bracket depth; the last token's kind) and the grammar
- [x] Tests for each case, including that a leading `-` still starts a statement; the language server's tokens and ranges unchanged
- [x] [[Language]] pages and the skill

Order: after [[MYLA-219]] this touches only the self-hosted toolchain (checker, interpreter, lowering) and the grammar; done before it, the Python checker and interpreter need it too. Using it in `selfhost/` itself needs a seed that knows it ([[MYLA-218]]).

## Evidence

- **The lexer.** [[selfhost/lexer.my]] keeps the brackets open at the cursor (`opens`: `(` and `[` true, `{` false). A line break makes no NEWLINE token inside `( )`/`[ ]`, unless within a `{ }` in them, or after a binary operator that ends the line (`continues_line`; not `>`, which also closes a generic type, and so not `>>`).
  - **Recovery.** A line held back this way that starts with a word only a statement or declaration starts (`starts_statement`: `let`, `return`, `fun`, `while`, …; not `if`, `match`, `async` or `var`, which `(var self` uses) ends the unclosed brackets, and its line break counts. A `}` closes the brackets left open in its block. So a missing `)` gives its error and the parser goes on to the next statement, as before.
- **The grammar.** [[grammar/myla.ebnf]] and [[Language/Grammar]] allow `NL` after the binary operators (not `>`, `>>`) and at the edges of parenthesised expressions, indexes, tuples, parameter and lambda parameter lists, and say how the lexer works. The tree-sitter grammar is regenerated; it doesn't see a line break before an operator inside brackets (documented).
- **Test first.** `tests/burn/test_line_continuation.py`:
  - trailing operators, a `|>` chain, a break before an operator inside parentheses;
  - parameters, an index and a tuple across lines;
  - a block lambda and a `match` inside call arguments, whose line breaks still separate statements;
  - `typealias Num = Box<int>` ending its line, and a leading `-` starting a statement;
  - and an operator at the end of a block, which is an error.

  Before the change the program didn't parse ("expected parameter name"); after, it gives the same output in the interpreter and natively.
- **Recordings made before continuation.**
  - The lexer gate drops the NEWLINE tokens the rule leaves out from the recorded tokens before comparing (`tests/burn/_continuation.py`), so the comparison stays exact elsewhere.
  - The parser gate keeps comparing the 119 of 128 garbled sources that have no such line break; for the other 9 it checks that errors are still reported.
  - Pinned with their new, more precise messages ("found '}'" instead of "found '\n'"): two syntax-error cases, three diagnostics in `test_selfhost_codegen` and one in `test_packages`. `newline_token` now reads `1 + print(x)` and reports the unknown `x`.
  - `unclosed_parenthesis` gives the recorded answer again thanks to the recovery.
- **The language server.** Its tests pass unchanged.
- **Docs.** [[Language/Lexical-structure]] (with a tested example), [[Language/Grammar]] and the myla skill. The burn suite passes, and the bootstrap reaches its fixed point with the new seed.

