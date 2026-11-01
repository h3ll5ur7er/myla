---
id: MYLA-225
title: "One trailing-comma rule"
type: feature
status: todo
priority: low
labels: [language, ergonomics, parser]
---
D104 (4) ([[MYLA-215]]): a trailing comma is allowed after the last element of every comma-separated list (arguments, parameters, list, map and tuple literals, struct fields and literals, enum variants, generic arguments, patterns, imports). A one-element tuple keeps its comma rule.

- [ ] An inventory of the lists and which accept a trailing comma today; the parser and grammar made uniform
- [ ] Tests; [[Language]] pages

Order: after [[MYLA-219]] this touches only the self-hosted toolchain (checker, interpreter, lowering) and the grammar; done before it, the Python checker and interpreter need it too. Using it in `selfhost/` itself needs a seed that knows it ([[MYLA-218]]).
