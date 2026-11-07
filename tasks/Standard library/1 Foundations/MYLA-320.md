---
id: MYLA-320
title: Std methods on built-in types in every program (the implicit imports)
type: feature
status: todo
priority: high
labels: [stdlib, compiler, checker, wave-1]
---
Wave 1 of [[Project/Standard-library-roadmap]]. Make the method modules of [[MYLA-319]] (1) visible in every program without an `import`, as the prelude's `get` and `Option` are. The modules are `std.str`, `std.char`, `std.int`, `std.list`, `std.option` and `std.map`. This is the one compiler task of wave 1. The library lanes don't wait for it: they test with an explicit `import`, and this task removes the need.

- **Owns:** `selfhost/` (loader, checker, LSP)
- **Needs:** [[MYLA-319]]

- [ ] The loader adds the implicit modules to every program (not to the modules of `std` itself, which import what they use); a program's own method of the same name on the same type is the existing duplicate error
- [ ] `myla check` time and native binary size measured before and after on the examples and an AoC-sized program; methods a program doesn't call cost nothing in its binary (if they do, the dead-function pass fixed first)
- [ ] The language server completes the implicit methods
- [ ] [[Language/Modules]] and [[Language/Standard-library]] updated
