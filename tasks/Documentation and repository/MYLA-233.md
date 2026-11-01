---
id: MYLA-233
title: "A burn test for the code blocks in the docs"
type: improvement
status: todo
priority: medium
labels: [docs, tests]
---
D114 ([[MYLA-213]]): every fenced `myla` block in `docs/` and the README is extracted and checked; a block with a `main` runs, and its printed lines are compared with the `// output` comments. Blocks that are deliberately fragments or deliberately wrong carry a marker (`myla fragment`, `myla error`).

- [ ] The extractor and the burn test, running on the self-hosted toolchain
- [ ] The blocks that fail today fixed or marked; the convention in [[Development/Conventions]]
