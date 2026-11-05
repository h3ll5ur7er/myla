---
id: MYLA-166
title: A C FFI - calling C libraries from Myla
type: design
status: backlog
priority: low
labels: [ffi, language, backend, gui]
---
Calling C libraries, which the GUI ([[MYLA-63]]) needs for GPU APIs and system toolkits, and which macOS and Windows need for anything graphical. Each of Myla's backends (D117) implements its platforms' C calling conventions and struct layout, which [[MYLA-160]] scopes; the design here is the language side. A design round first, recorded as a decision.

- [ ] The declarations: extern functions, C types (integers, floats, pointers, structs with C layout), strings across the boundary, callbacks into Myla
- [ ] Safety: what the checker can promise at the boundary, ownership of what crosses, and how concurrency (D89, actors) meets C code
- [ ] Linking: dynamic libraries, a dynamically linked executable where needed, and what it means for D2

## From the first two targets (2026-11-04, [[Project/Reflection-2026-11]])

- **D119 isn't what the backends do** (wasm's uniform `(i64…) -> i64` signatures and its environment in a memory word; aarch64's floats in x registers). If Myla keeps an internal convention per target, the FFI is where the platform's C convention is used, and its design follows [[MYLA-272]]'s decision.
- **wasm already has a hand-made FFI:** `__syscall(n, args, …)` in [[lib/std/platform_wasm.my]] means "call WASI import number `n` with the words at `args`", dispatched by a table in [[selfhost/runtime_wasm.my]]. Typed `extern` imports would replace it, and they are a small first case of this task: no structs, no callbacks, one module name (`wasi_snapshot_preview1`).
