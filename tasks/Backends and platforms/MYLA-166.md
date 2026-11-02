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
