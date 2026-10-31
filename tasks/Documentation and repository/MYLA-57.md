---
id: MYLA-57
title: playground.my is a scratch file pinned by the test gates
type: chore
status: done
priority: low
labels: [examples, tests]
---
`examples/playground.my` has no header comment, a mis-indented arm (line 41) and an unused `resolve(var self)`, yet `test_examples_run`, `test_examples_compile` and `test_examples_tests` pin it like a feature example.

- [x] Turn it into a proper example of what it exercises, fold it into `regressions.my`, or move it out of `examples/`

## How

The playground became a real example: [[examples/traits_on_builtins.my]] (renamed with `git mv`), with a header saying what it shows (traits on built-in types, a generic trait, methods on literals, a literal in an enum payload pattern, `#main` on a function not named `main`, the `>=` split of [[MYLA-15]]), the arm indented, `resolve` taking `self` instead of a pointless `var self`, and `main`'s last lines without needless `var`s. The output is unchanged; the example tests now name the new file.
