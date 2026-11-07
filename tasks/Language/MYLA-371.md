---
id: MYLA-371
title: "Dotted type names in type positions (m.Point)"
type: improvement
status: todo
priority: low
labels: [language, modules, decision]
---
[[Language/Modules]] says a module bound with `import` is used only as `m.member`, and that dotted type names like `m.Point` aren't supported in type positions: a type comes in with `from … import`. Two wave 2 lanes hit it (`num.ParseIntError` in [[MYLA-331]], `args.Spec` in [[MYLA-333]]): with module functions as the standard library's convention (D164), `import std.args as args` and then `args.parse(…)` read well, but naming the result's type means a second import line.

- [x] The owner's decision: allow `m.T` in type positions (D170)
- [ ] The parser's type rule takes a dotted name; the checker resolves it as `m.T` (a module bound by `import … as`); the grammar, tree-sitter and the language server (hover, go-to-definition on `T`)
- [ ] Tests: a parity program, error-corpus files for an unknown module and a type the module doesn't export; [[Language/Modules]] (its sentence that dotted type names aren't supported) and the skill
