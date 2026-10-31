---
id: MYLA-158
title: A WebAssembly target
type: feature
status: backlog
priority: low
labels: [backend, wasm, design]
---
A backend that turns the IR ([[Architecture/IR]], D85) into WebAssembly, so Myla programs, and the self-hosted toolchain itself, run in a browser. It comes after [[MYLA-62]] (LLVM) and before the website ([[MYLA-159]]), whose editor and tutorial need the checker and interpreter in the page.

## Notes

- The IR is lowered per target ([[Architecture/IR]], "Lowered per target"): 32-bit wasm has other sizes and offsets, so it means lowering again, not just a new emitter. LLVM's wasm target ([[MYLA-62]]) is one way; emitting `.wat`/`.wasm` directly keeps the toolchain free of dependencies, as the x86-64 backend is.
- The runtime (allocator, strings, maps, float formatting byte-identical to the interpreter) has to exist for wasm too; I/O goes through imports the host provides (a browser page, or WASI).
- Concurrency: wasm threads need shared memory and workers; a first version can run one worker (D92's `MYLA_THREADS=1` order).
- What the website needs first is the self-hosted lexer, parser, checker (with its diagnostics and warnings) and interpreter compiled to wasm, behind a small API: check a source, run it with given input, give back output, diagnostics and positions.

## Done when

- [ ] Direct or through LLVM decided, recorded on [[Project/Decisions]]
- [ ] The native parity programs give the same output under a wasm runtime
- [ ] The self-hosted checker and interpreter run as wasm with an API a page can call
