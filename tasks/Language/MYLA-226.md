---
id: MYLA-226
title: "`if let` and `while let`"
type: feature
status: todo
priority: medium
labels: [language, ergonomics]
---
D104 (5) ([[MYLA-215]]): `if let Some(x) = e { … } else { … }` and `while let Some(x) = next(it) { … }`, as sugar over `match`.

- [ ] Parser and grammar; desugaring (or checking and lowering) with the pattern's bindings scoped to the block; refutable patterns only (an irrefutable one is a warning or an error, decided here)
- [ ] Tests and error-corpus files; [[Language]] pages and the skill

Order: after [[MYLA-219]] this touches only the self-hosted toolchain (checker, interpreter, lowering) and the grammar; done before it, the Python checker and interpreter need it too. Using it in `selfhost/` itself needs a seed that knows it ([[MYLA-218]]).
