---
id: MYLA-116
title: Debugger for the interpreter (myla run)
type: feature
status: backlog
priority: low
labels: [tooling, debugging, interpreter]
---
Breakpoints, stepping and variables for programs run by the tree-walking interpreter (`myla run`), without gdb, a native build or Linux: the open item "interpreter-level debugging" of [[MYLA-66]], split off because it is more than the hook.

## Plan

- [ ] **The hook.** `Interpreter.debug_hook` (None by default: one attribute test per statement) is called before every statement and every expression-bodied match arm with the statement and its environment; `_call` keeps a stack of frames (function, declaration, environment, current statement) for backtraces and `finish`. Runtime errors call the hook before they unwind, so a debugger stops where they happen.
- [ ] **A command line front end.** `myla run --debug file.my`: a gdb-like loop reading commands from the terminal (`/dev/tty`, so the program keeps its stdin) and writing to stderr: `break file:line`, `break function`, `delete`, `continue`, `step`, `next`, `finish` (prints the result), `bt`, `up`/`down`, `info locals`/`info args`, `print <path>`. Values print in Myla syntax with the interpreter's formatting (`Bag { items: [4, 5], label: "two" }`). A path is a name with `.field`, `.0` and `[index]` at first; full expressions later (parse with the Myla parser, type with the checker's scope at the stop).
- [ ] **The editor.** A second mode of the VS Code debug adapter ([[MYLA-99]]) talking to `myla run --debug-protocol` (JSON lines over a pipe: stop events, frames, variables), reusing its DAP layer, so `F5` works without gdb and on macOS and Windows.
- [ ] **The self-hosted interpreter** (`selfhost/interp.my`) gets the same hook and front end once the Python one is settled.
- [ ] Tests: scripted command sessions against example programs (unit), the adapter's integration test in interpreter mode.

## Notes

- Estimated size: the hook is a few lines; the front end with tests a few hundred; the protocol mode and the adapter's second mode about as much again.
- The interpreter defines the semantics, so the values it shows are the ones `myla run` prints, with no layout to describe (unlike [[MYLA-66]]'s DWARF and pretty-printers).
