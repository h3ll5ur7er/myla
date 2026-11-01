---
id: MYLA-236
title: "`#test` on methods"
type: feature
status: in-progress
priority: high
labels: [language, tests]
---
D116: a method takes `#test` cases above it inside its `impl`, the receiver as the first argument; needed by the generated test cases of [[MYLA-184]] (methods are 46 % of the self-hosted compiler's value-returning functions).

- [x] Both parsers accept attributes before an impl method (not before a trait signature); error recovery treats `#` like `fun` inside an impl body
- [x] Both checkers: the receiver counts as the first argument; actor methods, generic methods and any attribute but `#test` rejected (three error-corpus files); `async` as for functions
- [x] Both runners: method cases in source order with the functions, named `Type.method #n`, a `var self` method's result compared
- [x] The loaders qualify names in method cases; the language server resolves them
- [x] [[grammar/myla.ebnf]], the tree-sitter grammar, [[Language/Grammar]], [[Language/Attributes-and-testing]], the `myla` skill
