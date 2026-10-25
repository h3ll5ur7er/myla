---
id: MYLA-47
title: tree-sitter grammar lags behind the Rust parser
type: improvement
status: backlog
priority: low
labels: [rust, editor, tree-sitter]
---
`rust/editor/tree-sitter-myla/grammar.js` is much looser than the real parser. It lacks:

- [ ] `;` separators, `as` casts, `?`, `..`, `<<`/`>>`, struct literals, `select`
- [ ] Real patterns (match arms are `_expr`)
- [ ] Float forms `1e9` and `2f32`, suffixes on hex/binary/octal literals, `'\u{…}'` chars
- [ ] `from … import x as y`
- [ ] `highlights.scm` lists a `unit` builtin type that the spec doesn't have
- [ ] Version 0.0.1 in `Cargo.toml` vs 0.1.0 in `package.json`, a placeholder repository URL, and an empty stray `rust/editor/package-lock.json`
