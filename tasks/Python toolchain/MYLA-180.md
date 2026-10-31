---
id: MYLA-180
title: A method's parameter list takes a trailing comma, a function's and a lambda's don't
type: bug
status: todo
priority: low
labels: [parser, grammar]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). `fun f(self, a: int,)` parses in an `impl` (`method_head` in [[grammar/myla.ebnf]] has `","?`), while `fun f(a: int,)` and `(a: int,) => a` are errors, and [[Language/Lexical-structure]] says no parameter list takes one. The grammar and both parsers agree with each other; the prose disagrees with them.

- [ ] One rule for all three (the grammar, both parsers, the page); an error-corpus file or an example pins it
