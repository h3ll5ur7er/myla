---
id: MYLA-398
title: "A bound can't name a module's trait: T: json.ToJson"
type: improvement
status: backlog
priority: low
labels: [language, parser, modules]
---
Found by the `#derive(Json)` lane ([[MYLA-385]]). With `import std.json as json`, `fun show<T: json.ToJson>(v: T) {}` is "parse error: expected '>' to close type parameters, found '.'". D170 lets a type position name `m.T`, but not a bound. Today's way is `from std.json import ToJson`.

- [ ] A bound names a module's trait as a type names its type (`T: json.ToJson`, `I: iter.Something<T>`): the grammar, the parser, the loader's renaming, the checker, the language server; D170's row extended
