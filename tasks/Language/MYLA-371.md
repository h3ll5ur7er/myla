---
id: MYLA-371
title: "Dotted type names in type positions (m.Point)"
type: improvement
status: backlog
priority: low
labels: [language, modules, decision]
---
[[Language/Modules]] says a module bound with `import` is used only as `m.member`, and that dotted type names like `m.Point` aren't supported in type positions: a type comes in with `from … import`. Two wave 2 lanes hit it (`num.ParseIntError` in [[MYLA-331]], `args.Spec` in [[MYLA-333]]): with module functions as the standard library's convention (D164), `import std.args as args` and then `args.parse(…)` read well, but naming the result's type means a second import line.

- [ ] The owner's decision: allow `m.T` in type positions (the parser's type rule, the checker's resolution, the grammar and tree-sitter), or keep `from … import`
