---
id: MYLA-158
title: A WebAssembly target
type: feature
status: backlog
priority: low
labels: [backend, wasm, design]
---
WebAssembly as a target of the LLVM backend ([[MYLA-62]], step 4), so Myla programs, and the self-hosted toolchain itself, run in a browser. It comes after the LLVM backend ([[MYLA-161]]) and the portable runtime ([[MYLA-162]]), and before the website ([[MYLA-159]]), whose editor and tutorial need the checker and interpreter in the page.

## Notes

- Through LLVM's wasm target (the plan of [[MYLA-62]]). The IR is lowered per target ([[Architecture/IR]], "Lowered per target"): 32-bit wasm has other sizes and offsets, which D98 ([[MYLA-160]]) settles.
- Tail calls (`become`, the suspensions of D90) need wasm's tail-call extension, which current browsers have.
- The runtime (allocator, strings, maps, float formatting byte-identical to the interpreter) has to exist for wasm too; I/O goes through imports the host provides (a browser page, or WASI).
- Concurrency: wasm threads need shared memory and workers, and `SharedArrayBuffer` needs cross-origin isolation headers that static hosts such as GitHub Pages can't set; a first version runs one worker (D92's `MYLA_THREADS=1` order).
- What the website needs first is the self-hosted lexer, parser, checker (with its diagnostics and warnings) and interpreter compiled to wasm, behind a small API: check a source, run it with given input, give back output, diagnostics and positions.

## Done when

- [ ] The platform layer for wasm ([[MYLA-162]]): host imports for output, files and time
- [ ] The native parity programs give the same output under a wasm runtime
- [ ] The self-hosted checker and interpreter run as wasm with an API a page can call
