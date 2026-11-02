---
id: MYLA-221
title: "Methods on builtin types; the free collection functions deprecated"
type: feature
status: todo
priority: medium
labels: [language, builtins, stdlib]
---
D103 ([[MYLA-204]]): `impl` blocks on builtin types are allowed, the builtin collection and string functions become methods, the free forms warn until the repository has moved, then go.

- [ ] The list: every builtin function on lists, maps, strings and chars with its method name and whether it takes `var self` (`push`, `insert`, `remove`, `set`, …)
- [ ] `impl [T]`, `impl Map<K, V>`, `impl str`, `impl char` and the numeric types in the checker; method lookup on builtin receivers; mutating methods need a `var` place, with the same diagnostics as `var self` methods today
- [ ] The free forms give a deprecation warning that names the method
- [ ] The repository's code moved (examples, `tools/`, the standard library; `selfhost/` after a seed update, [[MYLA-218]])
- [ ] The free forms removed; [[Language]] pages, the skill, `AGENTS.md` ("`push(xs, v)`") and the grammar updated

Before the standard library round ([[MYLA-211]]), which builds on it. Order: after [[MYLA-219]] this touches only the self-hosted toolchain (checker, interpreter, lowering) and the grammar; done before it, the Python checker and interpreter need it too. Using it in `selfhost/` itself needs a seed that knows it ([[MYLA-218]]).
