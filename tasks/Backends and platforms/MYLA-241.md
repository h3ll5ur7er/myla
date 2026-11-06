---
id: MYLA-241
title: Myla as a shared library for other languages
type: chore
status: backlog
priority: low
labels: [ffi, library, backend, platforms, design]
---
The other direction of [[MYLA-166]]: building Myla code into a library that C, Python, Swift, a browser or any other host can call. That means a `.so` on Linux, a `.dll` on Windows, a `.dylib` on macOS and a wasm module's exports. The owner's question (2026-11-02) was whether the standard library and users' code could be shared libraries (`myla new --lib`). The answer: not between Myla programs. Generics are copied per type ([[Architecture/Monomorphization]]), every program carries its own runtime (D2, D29), and value layouts still change (MYLA-179 grew map slots), so a binary interface between Myla programs would freeze what must stay free to change. Myla libraries stay source packages ([[Architecture/Project-tool]]); the standard library ships inside the compiler. A C-shaped interface is the boundary where a compiled library does make sense. A design round first, recorded as a decision.

- [ ] What can be exported: plain functions of types that cross the boundary as C sees them (integers, floats, booleans, pointers, structs with C layout); generic functions only as named concrete instances; strings and lists through explicit conversions; an attribute marking the exports (`#export`)
- [ ] The runtime inside a library: its start-up without a `main` (heap, the actor executor's workers, D92), more than one Myla library in one process, a host calling from its own threads, and what a runtime error does there (no `exit` under a host)
- [ ] Ownership across the boundary: who frees what a Myla function returns (reference-counted cells handed out and released through exported functions), callbacks from the host into Myla ([[MYLA-166]]'s callbacks in reverse)
- [ ] Per target: ELF shared objects and position-independent code (the assembly backend emits absolute addresses today), Windows DLL exports, macOS dylibs, wasm exports and imports ([[MYLA-158]]); each from Myla's own backends (D117)
- [ ] The commands: `myla build --lib` (a library and a C header generated from the exports), and how a project declares it in `myla.toml`
