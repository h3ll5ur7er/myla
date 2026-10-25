---
id: MYLA-47
title: tree-sitter grammar follows the removed Rust dialect
type: improvement
status: backlog
priority: low
labels: [editor, tree-sitter]
---
`editor/tree-sitter-myla/grammar.js` was written for the Rust edition's dialect (moved here from `rust/editor/` when the Rust edition was removed, [[MYLA-70]]) and is much looser than the real parser ([[src/myla/parser.py]], [[Language/Grammar]]).

- [ ] Drop the Rust-dialect constructs: `;` separators, `select`, `actor`, `async`/`await`, `spawn`/`go`, `chan`
- [ ] Add what real Myla has: `as` casts, `?`, ranges in `for` heads, `<<`/`>>`, struct literals, `|>`/`>>`/`_`, f-strings, `#test(args)[expected]` and `#derive`, `pub` and `from … import x as y`
- [ ] Real patterns (match arms are `_expr`)
- [ ] Float forms `1e9` and `2f32`, suffixes on hex/binary/octal literals, `'\u{…}'` chars
- [ ] `highlights.scm` lists a `unit` builtin type that Myla doesn't have; type names are `int32`, `float64`, … (not `i32`, `f64`)
- [ ] Version 0.0.1 in `Cargo.toml` vs 0.1.0 in `package.json`, and a placeholder repository URL
- [ ] A corpus test (`tree-sitter test`) over the examples, so the grammar can't drift again
