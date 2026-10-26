---
id: MYLA-77
title: Grammar description and a tree-sitter grammar generated from it
type: feature
status: backlog
priority: medium
labels: [grammar, tree-sitter, editor, selfhost]
---
Part of the "everything in Myla" direction ([[Project/Roadmap]]). Supersedes [[MYLA-47]].

The compilers' parsers are hand-written ([[src/myla/parser.py]], [[selfhost/parser.my]]), so a tree-sitter grammar can't be derived from their code. Instead, one machine-readable grammar description is the single source for the editor grammar, and tests tie it to the compiler, so it can't drift the way the current hand-written `editor/tree-sitter-myla/grammar.js` did (it still follows the removed Rust dialect).

- [ ] Turn the EBNF in [[Language/Grammar]] into a machine-readable file (in the repository, the wiki page generated from it or checked against it), including the newline/`;` separators (D61) and where line breaks are skipped
- [ ] A generator written in Myla emits `grammar.js` and the highlight queries; tokens (keywords, operators, type names, literal forms) come from [[selfhost/tokens.my]] / [[selfhost/lexer.my]]
- [ ] Newlines as a real token with explicit optional newlines in rules (no external C scanner); approximate where tree-sitter can't express the parser exactly (generic `<` vs less-than, struct literals in `if`/`while` headers, f-string holes)
- [ ] Tests: tree-sitter parses every `.my` file of `examples/`, `selfhost/` and the stdlib without an ERROR node; programs generated from the grammar file are accepted by the self-hosted parser; the syntax-error corpus gives ERROR nodes where feasible
- [ ] Optionally emit the VS Code TextMate grammar from the same source (see [[MYLA-54]])
