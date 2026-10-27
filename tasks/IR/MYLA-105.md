---
id: MYLA-105
title: IR: heap values, ownership and the verifier
type: feature
status: backlog
priority: high
labels: [ir, codegen, selfhost]
---
Step 3 of [[MYLA-67]] ([[Architecture/IR]]): strings, lists, maps and builders through the IR, with every ownership rule of [[Architecture/Native-backend#heap-and-reference-counting]] as explicit `retain`/`drop`/`cow`.

- [ ] Literals, concatenation, indexing, the collection builtins, staged stores and copy-on-write
- [ ] Drops at scope exit, `return`, `break`/`continue`, statement ends; match scrutinee copies retained when an arm may write
- [ ] The verifier, run on every function the gates compile; a test with deliberately broken IR for each rule
- [ ] The stress tests (millions of cells) with `--ir`
