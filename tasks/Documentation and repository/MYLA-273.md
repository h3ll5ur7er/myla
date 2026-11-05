---
id: MYLA-273
title: "Mark the superseded parts of decisions"
type: chore
status: review
priority: low
labels: [docs, decisions]
---
Found by [[Project/Reflection-2026-11]]. Several rows on [[Project/Decisions]] are partly superseded without a mark; only D19 and D71 carry a "changed by" note:

| Row | Superseded part | By |
|---|---|---|
| D2 | x86-64 only, `as`/`ld` | D117, D125 |
| D26 | a shift by ≥ width is an error | D44 (runtime amounts masked) |
| D29 | thin system-call wrappers, everywhere | D117 (2), D125 |
| D67 | "no threads in Myla" | D89 |
| D82 (2) | floats returned in `%rax` | D119 |
| D85 (4), (5) | the runtime as x86-64 assembly; the pressure points | D117, D90, D92, D120–D123 |
| D86 (5), D87 (3) | the callee pops | D119 |
| D108 | "later by the LLVM backend" | D117 |
| D117 (4) | LLVM's tools not allowed | D125 (2) uses clang and wasm-ld (LLVM's assembler and linker; its optimiser not used) |

- [x] The owner decides whether and how to mark them: D134, an italic note now, the page's format later ([[MYLA-193]]); a "changed by" note on D2, D26, D29, D35, D58, D67, D82, D85, D86, D87, D108, D117 and D119
