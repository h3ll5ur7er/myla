---
id: MYLA-203
title: "Decision: `float` is float32 or float64"
type: chore
status: todo
priority: medium
labels: [decision, language, floats]
---
From the October 2026 review ([[Project/Review-2026-10]], §11.2 and §13.9). D19 made `float` an alias of `float32`, and unsuffixed float literals are `float32`. Everyone expects the opposite (C, Rust, Swift, Go, Python default to 64 bits); the `myla` skill has to put it in bold, `0.1 + 0.2 == 0.3` is true only through float32 rounding, and B7 (an `OverflowError` in the Python interpreter's float32 rounding) comes from emulating it. About 38 uses of `float` in 19 files of the repository.

## Question

What does `float` (and an unsuffixed literal such as `1.5`) mean?

## Options

- **A. Keep float32**, and explain it on a FAQ page. No work; the surprise stays.
- **B. `float` = float64, unsuffixed literals float64.** Both checkers' alias and literal default, both interpreters' literal rounding, the examples whose output changes, the skill and the docs. Both backends already have float64 code.
- **C. Drop the alias.** Only `float32`/`float64`; an unsuffixed literal takes its type from context and defaults to float64. The most explicit, and the most churn in existing code.

## Recommendation

**B.** It matches every language Myla's users come from, removes a footgun and a doc warning, and costs little because both float widths already exist everywhere. Part of the ergonomics round ([[MYLA-215]]).

## Decision

*Open.* The owner's answer goes here and, once given, onto [[Project/Decisions]] as a numbered decision.

- [ ] Decided, and recorded on [[Project/Decisions]]
- [ ] The implementation tasks created or updated to match
