---
id: MYLA-260
title: "4-byte pointers on wasm32, with packed struct fields (D122, deferred by D126)"
type: feature
status: backlog
priority: low
labels: [ir, backend, wasm, performance]
---
D122 decided that the lowering takes the target's pointer size and computes the layouts from it; D126 deferred that for wasm32, which runs with 32-bit addresses and today's 8-byte layouts ([[MYLA-158]]). Doing it saves memory on wasm only: pointer-typed values (strings, lists, maps, builders, boxed enums, actors, a function value's code and environment) would take 4 bytes in struct and tuple fields, enum payloads, list elements, map values and closure captures. Headers and counts stay 8-byte words.

Packing struct fields at their natural sizes (as list elements are since D120) touches the same places, so the two go together:

- [ ] A target description in the code generator (pointer size, alignment), the sizes and offsets (`size`, `stored_size`, `elem_size`, `word_size`) from it; the native targets' code byte for byte the same
- [ ] Every load and store of a pointer-typed value at its width (the lowering, the ownership pass, the per-type routines, environments, partial applications, composition, the deep copies)
- [ ] The wasm backend and runtime reading a function value's code and environment at the pointer size
- [ ] Measured: memory of pointer-heavy programs on wasm; [[tests/burn/test_wasm.py]] and the wasm compiler's fixed point hold
