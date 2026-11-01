---
id: MYLA-54
title: VS Code grammar and snippets describe a different Myla
type: bug
status: done
priority: low
labels: [vscode]
---
The TextMate grammar and snippets mix in the Rust dialect and miss parts of the real language:

- [x] The grammar highlights `actor`, `async fun`, `spawn`, `go`, `await`, `chan`, which the Python/self-hosted Myla doesn't have
- [x] The type pattern lists `f32`, `f64`, `void` but not `float32`/`float64` (`\bfloat\b` doesn't match `float32`)
- [x] The Trait snippet has a method body (traits hold signatures only)
- [x] The Impl snippets omit the `self` receiver, which is a parse error (`examples/errors/parse_method_no_self.my`)
- [x] The Actor and Async snippets are for constructs that don't exist
- [x] The `#test` snippet lacks the `(args)[expected]` the checker requires

## How

- [[vscode-extension/myla/syntaxes/myla.tmLanguage.json]]: the Rust-dialect words (`actor`, `async`, `spawn`, `go`, `await`, `chan`) and `void` are gone; the type names are exactly the built-in ones (`float32`/`float64`, no `f32`/`f64`); float literals in all forms (`1e9`, `2f32`, `1.5e-3f64`), suffixes on hex/binary/octal literals, `'\u{…}'` chars, `<<`, `?`, and `;` as a statement separator (D61).
- [[vscode-extension/myla/snippets/myla.code-snippets]]: no Actor/Async snippets; the trait snippet has a signature only, the impl snippets a `self` receiver, `#test` its `(args)[expected]`; every default text is valid Myla.

## Evidence

[[tests/unit/test_vscode_extension.py]] ties the files to the compiler: the grammar's keywords must be lexer keywords ([[src/myla/tokens.py]]), its type names exactly the built-in ones, no Rust-dialect word anywhere, every literal form matched; every snippet, expanded with its default text, must parse with the Myla parser. Before: 16 failures and 8 errors (7 snippets didn't parse); after: all 6 tests pass. The TextMate grammar could later be generated with the tree-sitter grammar ([[MYLA-77]]).

