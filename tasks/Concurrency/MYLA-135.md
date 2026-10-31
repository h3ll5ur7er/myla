---
id: MYLA-135
title: Concurrency in the language and both checkers
type: feature
status: in-progress
priority: medium
labels: [concurrency, language, checker, selfhost]
---
D89, first step of [[MYLA-61]]: the syntax and the rules, on the Language pages and in both checkers (with the same errors).

- [x] The syntax by example on a new Language page, for review: `actor` declarations and methods, `async fun`, `await`, `async let`, task groups, `#main async fun main()`; keywords and grammar ([[Language/Concurrency]], [[Language/Grammar]], the tree-sitter grammar, the VS Code grammar, the LSP's keywords)
- [x] Lexers and parsers (Python and self-hosted), with the same canonical trees and syntax errors
- [x] The rules: where `await` may stand, calling async functions only from async code, actor isolation (state only through `self` in its own methods, every outside call awaited), `async let` not outliving its scope (structural: only async functions have child tasks, and lambdas can't await them)
- [x] The error corpus for each rule (`examples/errors/type_*async*`, `type_actor_*`, …) and snippets for the self-hosted checker's parity test
- [x] The interpreters and backends refuse concurrent programs at their first construct of concurrency until [[MYLA-136]] … [[MYLA-139]]

Left for [[MYLA-136]]: `std.task` (groups), and sendability, which every value has today (D89 point 5): a check only once a kind of value can't be copied.
