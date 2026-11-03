---
id: MYLA-62
title: Other platforms through Myla's own backends
type: feature
status: backlog
priority: medium
labels: [backend, platforms, design]
---
Other CPUs and operating systems for Myla programs and the toolchain itself. The plan was an optional LLVM backend; D117 (2026-11-02) replaced it: backends of Myla's own written from the IR ([[Architecture/IR]]), as the x86-64 one is, and the runtime in Myla over a thin platform layer, so a new backend only translates the IR.

## Notes

- The IR is stable (D79, D85), lowered per target ("Lowered per target"), and the x86-64 backend ([[selfhost/ir_x86.my]]: instruction selection, register allocation, tail calls) is the template for the next ones.
- What makes a platform expensive is the runtime (about 3,000 lines of x86-64 assembly in [[selfhost/codegen.my]]) and the platform layer (D2, no libc), not the code generator. With the runtime in Myla ([[MYLA-162]]) both shrink to the platform layer.
- Float formatting must stay byte-identical to the interpreter (same operation order; no fast-math) on every target.
- The LLVM plan of 2026-10-31 (a decision round, user code through `llc`, its debug metadata) is history: [[MYLA-161]] and [[MYLA-167]] were dropped with D117.

## Plan (2026-11-02, D117)

1. [[MYLA-160]] De-risking D117 before the first new backend: the gap to C measured ([[MYLA-242]]), the runtime's port sized, the IR's open points (a pointer kind, sizes per target, SSA where a pass wants it), object files and linking per platform, debug information per platform, the gates
2. [[MYLA-162]] The runtime in Myla, over a thin platform layer: the step that makes other platforms affordable
3. Backends and targets: [[MYLA-158]] WebAssembly, [[MYLA-163]] Linux on aarch64, then [[MYLA-164]] macOS and [[MYLA-165]] Windows (mostly platform layers and linking)
4. [[MYLA-166]] A C FFI, which the GUI ([[MYLA-63]]) needs, and its other direction [[MYLA-241]]

## Done when

- [x] IR first: D79, D85
- [x] The backend strategy decided: D117
- [ ] [[MYLA-160]]'s questions answered and recorded
- [ ] At least one target besides x86-64 Linux ([[MYLA-158]], [[MYLA-163]] to [[MYLA-165]])
