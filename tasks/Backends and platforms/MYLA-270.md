---
id: MYLA-270
title: "Benchmarks on wasm and on aarch64 hardware"
type: chore
status: backlog
priority: medium
labels: [performance, platforms, benchmarks]
---
Found by [[Project/Reflection-2026-11]]. [[Development/Benchmarks]] measures x86-64 only ([[MYLA-242]]). A first look for the reflection, under Node against the x86-64 build: fib 1.9×, binary trees 2.7×, string building 2.4×, with wasm's simple dispatch loop. aarch64 has no meaningful number, as qemu's timing isn't hardware's, and its backend has no register allocation yet ([[MYLA-257]]).

- [ ] `benchmarks/run.py` with a target: wasm under Node (and wasmtime, if available), aarch64 on hardware (a GitHub arm64 runner), against C built for the same target
- [ ] The results on [[Development/Benchmarks]], so the stackifier ([[MYLA-158]]) and the shared allocator ([[MYLA-257]]) have a baseline
