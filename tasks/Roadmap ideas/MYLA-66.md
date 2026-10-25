---
id: MYLA-66
title: Debugger support
type: feature
status: backlog
priority: low
labels: [tooling, debugging, backend]
---
Debug Myla programs: breakpoints, stepping, inspecting variables.

## A cheap first step

The assembler already supports line tables: emitting GAS `.file` and `.loc` directives before each statement's code (every AST node knows its line and column) gives DWARF line information, so `gdb ./prog` can set breakpoints on `file.my:12`, step line by line and show backtraces with Myla function names, with no other change. Labels are already `myla_<name>`.

## Further steps

- Variable locations: every local has a fixed `%rbp` offset (one slot per local, never reused), which maps directly onto DWARF `DW_OP_fbreg` locations; types need DWARF type descriptions (structs, enums with tags, lists through their cell layout) or a gdb pretty-printer script.
- Interpreter-level debugging: a step/breakpoint hook in the tree-walking interpreter is easy and gives a debugger for `myla run`.
- An editor front end: the Debug Adapter Protocol in the VS Code extension, next to the language server.
- Runtime traps could print the failing source position by mapping the trap's return address through the same line table ([[MYLA-65]]).

## Done when

- [ ] `myla build -g` emits line tables; `gdb` steps through `examples/structs.my`
- [ ] Locals visible in gdb for scalars and strings
