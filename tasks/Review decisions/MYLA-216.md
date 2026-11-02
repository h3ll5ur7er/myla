---
id: MYLA-216
title: "Decision: CI runs the burn suite against the bootstrapped toolchain"
type: chore
status: review
priority: medium
labels: [decision, ci]
---
From the October 2026 review ([[Project/Review-2026-10]], §13.10). Pull-request burn tests run the CLI and the language server built by the Python backend; only the bootstrap job runs the real `build/myla`, and only on `hello.my`. What users run is the self-hosted build. The burn job takes about 6.5 minutes.

## Question

How does CI test what users run?

## Options

- **A. As today.**
- **B. Bootstrap inside the burn job.** `scripts/bootstrap.sh` takes seconds since [[MYLA-60]], so the burn job builds `build/myla` and `build/myla-lsp` itself and runs the suite against them.
- **C. Build once, share it.** The bootstrap job uploads stage 3 as an artifact (or a cache keyed by the compiler's sources), the burn job downloads it.

## Recommendation

**B**, after measuring the bootstrap on a CI runner; C only if the measurement says it matters. Together with gdb in the burn job ([[MYLA-156]]).

## Decision

**D115 (2026-11-01): the recommendation.** Implementation: [[MYLA-235]].

- [x] Decided, and recorded on [[Project/Decisions]]
- [x] The implementation tasks created or updated to match
