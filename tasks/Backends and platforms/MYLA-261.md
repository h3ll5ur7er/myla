---
id: MYLA-261
title: "wasm: the shadow stack below the data, and traps reported as native ones are"
type: bug
status: backlog
priority: high
labels: [backend, wasm, runtime]
---
Found by [[Project/Reflection-2026-11]]. Two wasm32 faults ([[MYLA-158]]):

- **A deep shadow-stack overflow overwrites data silently.** wasm-ld places the shadow stack above the static data by default. In a module built today, `__stack_pointer` starts at 8,409,808 and the data at 1,024. The stack grows down, so a frame-heavy recursion that exhausts the 8 MiB shadow stack before the engine's own call stack writes over string literals and runtime variables instead of trapping. Linking with `--stack-first` puts the stack below the data, so an overflow wraps below address 0 and traps.
- **A trap isn't reported as a runtime error.** Under `tools/wasm/run.mjs`, a trap the program didn't report itself (the engine's call-stack limit, an out-of-bounds access) prints `wasm trap: <engine message>` and exits 134. Native builds print `runtime error: stack overflow` and exit 1. The page API (`myla.mjs`) already maps the stack case.

- [ ] `--stack-first` in `myla build`, `test_wasm.py` and `scripts/build-page.sh`; a test that a frame-heavy recursion traps instead of corrupting a printed literal
- [ ] `run.mjs` reporting a call-stack trap as `runtime error: stack overflow` with exit 1, like `myla.mjs`; other traps as `runtime error: <message>`
- [ ] [[Architecture/Native-backend]] (wasm32 section) on the stack's placement and the engine's limits
