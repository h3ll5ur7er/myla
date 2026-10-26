---
id: MYLA-83
title: Retire the Python tools that have Myla replacements
type: chore
status: backlog
priority: low
labels: [cleanup]
---
Part of the "everything in Myla" direction ([[Project/Roadmap]]). The last step, one tool at a time, as was done for the compiler: once a Myla tool passes the parity tests of its Python counterpart, the Myla one becomes the default and the Python one is removed or kept only as the bootstrap/reference.

- [ ] Language server ([[MYLA-80]]): remove [[src/myla/lsp/]] and the `myla lsp` command
- [ ] `myla test` ([[MYLA-81]]) and `run`/`build`: decide which Python commands stay for the bootstrap
- [ ] Decide the long-term role of the Python interpreter (the semantics reference) and record it on [[Project/Decisions]]
