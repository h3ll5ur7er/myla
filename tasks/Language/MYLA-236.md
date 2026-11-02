---
id: MYLA-236
title: "`#test` on methods"
type: feature
status: review
priority: high
labels: [language, tests]
---
D116: a method takes `#test` cases above it inside its `impl`, the receiver as the first argument; needed by the generated test cases of [[MYLA-184]] (methods are 46 % of the self-hosted compiler's value-returning functions).

- [x] Both parsers accept attributes before an impl method (not before a trait signature); error recovery treats `#` like `fun` inside an impl body
- [x] Both checkers: the receiver counts as the first argument; actor methods, generic methods and any attribute but `#test` rejected (three error-corpus files); `async` as for functions
- [x] Both runners: method cases in source order with the functions, named `Type.method #n`, a `var self` method's result compared
- [x] The loaders qualify names in method cases; the language server resolves them
- [x] [[grammar/myla.ebnf]], the tree-sitter grammar, [[Language/Grammar]], [[Language/Attributes-and-testing]], the `myla` skill

## Evidence

- Tests first: `TestTestRunner.test_method_cases` (two cases on a `self` method, one failing on purpose, one on a `var self` method, functions before and after: the report in source order, `expected 6, got 5`) and four checker tests in `tests/unit/test_types.py` (the receiver counted, trait impls and `impl int32`, the rejections) failed before the change (a parse error) and pass after.
- Both runners print the same report on `examples/methods.my` (six new method cases), on `FAILING` of `tests/burn/test_selfhost_cli.py` (a failing method case, a `var self` method), on a module whose method case calls a function of the module and reads a constant (the loader's qualification), and from an importing file (no cases: own cases only).
- Error corpus: `type_test_actor_method.my`, `type_test_generic_method.my`, `type_main_on_method.my`, pinned for both checkers. Language server: `test_names_in_a_method_s_test_cases` (a constant, the struct and its field resolve inside a method's case).
- Unit 626, integration 2, burn 833 (5 skipped) and the extension's 54 tests pass on commit b5f14aa; the bootstrap reaches its byte-identical fixed point (6,194,010 bytes).

