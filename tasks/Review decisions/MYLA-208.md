---
id: MYLA-208
title: "Decision: the roadmap's scope beside the open backlog"
type: chore
status: todo
priority: medium
labels: [decision, roadmap, process]
---
From the October 2026 review ([[Project/Review-2026-10]], §11.7). The roadmap lists an LLVM backend, four more platforms (aarch64, macOS, Windows, wasm), a C FFI, a website and a GUI framework, while 87 tasks waited for review. Since the review the review pile has been signed off and about 30 tasks are open, most of them review findings in `backlog`.

## Question

How much of the roadmap is a plan, and what is only an idea?

## Options

- **A. Keep the roadmap as it is**: everything listed, ordered.
- **B. Now / Next / Later / Parked.** *Now*: the review follow-ups and these decisions ([[MYLA-201]] first), the ergonomics round, the standard library. *Next*: LLVM for x86-64 Linux ([[MYLA-160]], [[MYLA-161]]). *Later*: wasm and the website ([[MYLA-158]], [[MYLA-159]]). *Parked*: macOS, Windows, aarch64, the C FFI, the GUI framework. An item moves up when the one before it is done.
- **C. Remove the ideas from the roadmap**, keep them only as `Roadmap ideas` tasks; the roadmap shows only committed work.

## Recommendation

**B.** It keeps the ideas visible and in order without implying they are planned, and makes "what's next" a one-line answer. The parked ones stay as tasks.

## Decision

*Open.* The owner's answer goes here and, once given, onto [[Project/Decisions]] as a numbered decision.

- [ ] Decided, and recorded on [[Project/Decisions]]
- [ ] The implementation tasks created or updated to match
