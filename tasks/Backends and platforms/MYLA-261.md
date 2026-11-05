---
id: MYLA-261
title: "wasm: the shadow stack below the data, and traps reported as native ones are"
type: bug
status: review
priority: high
labels: [backend, wasm, runtime]
---
Found by [[Project/Reflection-2026-11]]. Two wasm32 faults ([[MYLA-158]]):

- **A deep shadow-stack overflow overwrites data silently.** wasm-ld places the shadow stack above the static data by default. In a module built today, `__stack_pointer` starts at 8,409,808 and the data at 1,024. The stack grows down, so a frame-heavy recursion that exhausts the 8 MiB shadow stack before the engine's own call stack writes over string literals and runtime variables instead of trapping. Linking with `--stack-first` puts the stack below the data, so an overflow wraps below address 0 and traps.
- **A trap isn't reported as a runtime error.** Under `tools/wasm/run.mjs`, a trap the program didn't report itself (the engine's call-stack limit, an out-of-bounds access) prints `wasm trap: <engine message>` and exits 134. Native builds print `runtime error: stack overflow` and exit 1. The page API (`myla.mjs`) already maps the stack case.

- [x] `--stack-first` in `myla build` (which `scripts/build-page.sh` uses) and `test_wasm.py`; a test that a frame-heavy recursion is the runtime error, not a write over the data
- [x] `run.mjs` reporting a call-stack trap as `runtime error: stack overflow` with exit 1, like `myla.mjs`; other traps as `runtime error: <message>`
- [x] [[Architecture/Native-backend]] (wasm32 section) on the stack's placement and the engine's limits

## Done (2026-11-04)

- **The stack below the data:** `myla build --target wasm32-wasi` links with `--stack-first` ([[selfhost/driver.my]]), so the 8 MiB shadow stack is `[0, 8 MiB)` and the data starts above it. The stack can't run into the data, only below address 0.
- **Running out of it is the runtime error:** every function's prologue compares `__stack_pointer` with its frame's size first ([[selfhost/ir_wasm.my]]). With no room left it calls `__trap_stack` ([[selfhost/runtime_wasm.my]]), which gives the stack back whole (`__stack_high`) and reports `runtime error: stack overflow` through `__panic`, without a position, as natively. Without the check the stack wrapped below 0, giving the engine's "memory access out of bounds".
- **The engine's own stack:** [[tools/wasm/run.mjs]] reports V8's "Maximum call stack size exceeded" as `runtime error: stack overflow` and any other trap as `runtime error: <message>`, with exit code 1, as `myla.mjs` does; an exception from the shim itself is rethrown, not hidden.

Evidence ([[tests/burn/test_wasm.py]], `WasmStack`, each written first and seen failing):
- `test_the_stack_lies_below_the_data` reads the module: `__stack_pointer` started at 8,399,520 above data at 1,024 before, now at or below every data segment.
- `test_running_out_of_the_shadow_stack`: a recursion with 1.5 KB frames gave `wasm trap: memory access out of bounds`, exit 134, after running through the data. It now gives what its x86-64 build gives: `2001`, `the data is intact`, `runtime error: stack overflow`, exit 1.
- `test_running_out_of_the_engines_stack`: a recursion with small frames gave `wasm trap: Maximum call stack size exceeded`, exit 134; now the same as x86-64.
- The whole wasm suite passes (24 tests, 5 skipped as before). The check's cost under Node is within the noise (binary trees' median 0.4% and 4.3% slower in two rounds of runs, fib 1–2% faster).
