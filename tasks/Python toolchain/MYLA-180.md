---
id: MYLA-180
title: A method's parameter list takes a trailing comma, a function's and a lambda's don't
type: bug
status: review
priority: low
labels: [parser, grammar]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). `fun f(self, a: int,)` parses in an `impl` (`method_head` in [[grammar/myla.ebnf]] has `","?`), while `fun f(a: int,)` and `(a: int,) => a` are errors, and [[Language/Lexical-structure]] says no parameter list takes one. The grammar and both parsers agree with each other; the prose disagrees with them.

- [x] One rule for all three (the grammar, both parsers, the page); an error-corpus file or an example pins it

## Evidence

- No trailing comma in any parameter list: both parsers (the method list's special case removed), `grammar/myla.ebnf` and [[Language/Grammar]] (tree-sitter regenerated with `scripts/gen_treesitter.sh`), [[Language/Lexical-structure]]. Error corpus: `parse_method_params_trailing_comma.my`; no source in the repository used one.
- Unit 622, integration 2, burn 826 (5 skipped) and the extension's 54 tests pass on commit 12f6e94; the bootstrap reaches its byte-identical fixed point (6,153,392 bytes).
