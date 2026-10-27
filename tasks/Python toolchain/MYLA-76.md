---
id: MYLA-76
title: Optional semicolons as statement separators
type: feature
status: review
priority: medium
labels: [lexer, parser, selfhost, spec]
---
A line break is the only way to end a statement or a declaration, so short code can't be written compactly: `fun main() { let x = 1; print(x) }` is a lex error (`;` is an unexpected character).

Allow `;` wherever a line break ends a statement or a declaration, as an optional alternative: between statements in a block, between top-level declarations, between the methods of an `impl` or a trait, and after `return`. A run of `;` and line breaks is one separator, so a trailing `;` at the end of a line is harmless. Everywhere else (`f(a; b)`, `[1; 2]`, struct fields, match arms) `;` stays an error.

## Done when

- [x] Decision recorded on [[Project/Decisions]]
- [x] Both lexers produce a `;` token; both parsers accept it as a separator with the same AST as a line break, and give the same errors
- [x] Unit tests (lexer, parser, errors) and self-hosted gate cases
- [x] An example written compactly, run by every corpus gate
- [x] [[Language/Lexical-structure]], [[Language/Statements]], [[Language/Grammar]], the `myla` skill and `AGENTS.md` updated

## How

D61. Both lexers produce a `SEMI` token for `;` ([[src/myla/lexer.py]], [[selfhost/lexer.my]]). Both parsers have `skip_separators` / `at_separator` (NEWLINE or SEMI) and use them exactly where a NEWLINE ends something: the top level and `terminate`, blocks, `impl` and trait bodies, and the bare-`return` check ([[src/myla/parser.py]], [[selfhost/parser.my]]). The places that merely *skip* line breaks (argument lists, literals, struct and enum bodies, patterns, match arms, before `else`) are unchanged, so `;` there is a syntax error with the usual message. Two messages now name it: `expected newline, ';' or '}', found …` and `expected end of declaration (newline or ';'), found …`. The language server's name lookup also stops at `;`.

## Evidence

- [[tests/unit/test_semicolons.py]]: the token; a program written compactly has the same canonical AST as with line breaks and prints the same; trailing and repeated `;`; `return;`; lambda and match-arm blocks; six rejected placements and the two messages. Before: `LexError: unexpected character ';'`.
- [[examples/semicolons.my]] runs through every corpus gate (self-hosted lexer, parser, checker, compiler and interpreter) and the example tests; 8 new `SYNTAX_ERRORS` cases in [[tests/burn/test_selfhost_parser.py]] match Python's messages and positions.
- The bootstrapped self-hosted compiler builds the example to the same output (`12 size 7 15 21 42`); fixed point holds (6,093,146 bytes). Unit (450), integration and burn (373) suites pass.
