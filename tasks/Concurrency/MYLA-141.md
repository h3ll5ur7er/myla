---
id: MYLA-141
title: Debug information for frame functions
type: feature
status: done
priority: medium
labels: [concurrency, debugging, codegen, selfhost]
---
After [[MYLA-138]] (D90): with `-g`, the self-hosted backend describes no variable of an async function's frame function, so `info args` and `info locals` show nothing in an async function of a program with tasks ([[Development/Debugging]]). Its slots live in its heap frame, not at `%rbp`.

- [x] Parameters and locals of frame functions (async functions and lambdas) in the DWARF, at their places in the heap frame
- [x] The normalizer's temporaries (`%aw1`, …) left out, as the compiler's own (`__…`) are
- [x] A gdb test: arguments, locals of several kinds, a value after an `await`, an async lambda's captures

## Design

A frame function's one argument is its frame, in the argument word at `16(%rbp)` for the whole function (its prologue copies it to `%r15`). A variable's location is that word, dereferenced, plus the slot's offset: `DW_OP_fbreg 16; DW_OP_deref; DW_OP_plus_uconst off`, then what the type needs, as for any variable. It holds wherever the function runs, also when gdb looks at it from a callee, where `%r15` might hold anything (the backend emits no unwind information for it). The parameters, owned copies in the frame, are described as parameters, visible in the whole function.

## Evidence

- Before: at a line of an async function of a program with tasks, gdb printed `No arguments.` and `No locals.` (the frame line `myla_greet ()`).
- After (`test_async_functions_show_their_variables`, one worker): the frame line reads `myla_greet (name=..., times=3)`; `info args` shows `name = "bo"`, `times = 3`; `info locals` shows `label = "bo!"`, `words = ["hi", "bo"]` (with the pretty-printers), `count = 6`; in `main` after `let r = await a`, `r = 9` and `print r + 1` gives 10; in the async lambda its captures `r = 9`, `base = 40`; no `%` name anywhere.
- The 32 debug-information tests of both backends pass.
- Unit 621, integration 2, burn 797 (5 skipped) and the extension's 54 tests pass; the bootstrap reaches its byte-identical fixed point (5,966,163 bytes).
