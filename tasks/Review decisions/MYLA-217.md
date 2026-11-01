---
id: MYLA-217
title: "Decision: splitting codegen.my, one frame-layout record, one AST visitor"
type: chore
status: todo
priority: low
labels: [decision, selfhost, backend]
---
From the October 2026 review ([[Project/Review-2026-10]], §13.11). `selfhost/codegen.my` is 8,100 lines: the hand-written runtime, frame layout, DWARF and the census in one module. Four AST walks collect names separately. The Python backend keeps its runtime as strings in Python. Related: [[MYLA-185]] (layout constants in one place, a typed table of runtime helpers).

## Question

Is the backend split now, and how far?

## Options

- **A. Split now**: modules for the runtime, frame layout, DWARF and the census, sharing one frame-layout record; one visitor for the name-collecting walks.
- **B. Runtime as `.s` templates** emitted verbatim, in both backends.
- **C. Wait for the runtime to move off assembly** ([[MYLA-162]]), which removes most of the runtime code from `codegen.my` anyway.

## Recommendation

**A for the layout record and the visitor** (with [[MYLA-185]]; the LLVM backend needs the same layout), **C for the runtime**: no templates now. Nothing on the Python backend's runtime strings, following [[MYLA-201]].

## Decision

*Open.* The owner's answer goes here and, once given, onto [[Project/Decisions]] as a numbered decision.

- [ ] Decided, and recorded on [[Project/Decisions]]
- [ ] The implementation tasks created or updated to match
