---
id: MYLA-220
title: "`float` is float64"
type: feature
status: todo
priority: medium
labels: [language, floats]
---
D102 ([[MYLA-203]]): the alias `float` means `float64`, and a float literal without a suffix is a `float64`; `float32` and `f32` stay.

- [ ] The alias and the literal default in the checker(s)
- [ ] Literal handling in the interpreter(s) and both backends (constants emitted as doubles)
- [ ] The examples whose output changes, the error corpus, the parity programs
- [ ] [[Language]] pages, the `myla` skill and `AGENTS.md` ("`float` is `float32`" goes)

Order: after [[MYLA-219]] this touches only the self-hosted toolchain (checker, interpreter, lowering) and the grammar; done before it, the Python checker and interpreter need it too. Using it in `selfhost/` itself needs a seed that knows it ([[MYLA-218]]).
