---
id: MYLA-158
title: A WebAssembly target
type: feature
status: in-progress
priority: low
labels: [backend, wasm, design]
---
WebAssembly as a target ([[MYLA-62]], step 3), so Myla programs, and the self-hosted toolchain itself, run in a browser. It comes after the runtime in Myla ([[MYLA-162]]), and before the website ([[MYLA-159]]), whose editor and tutorial need the checker and interpreter in the page.

## Notes

- A wasm backend of Myla's own from the IR (D117): no register allocation, the structured control flow wasm requires rebuilt from the IR's blocks, and the binary module format written directly. The IR is lowered per target ([[Architecture/IR]], "Lowered per target"): 32-bit wasm has other sizes and offsets, which [[MYLA-160]] settles. A candidate for the first new backend.
- Tail calls (`become`, the suspensions of D90) need wasm's tail-call extension, which current browsers have.
- The runtime (allocator, strings, maps, float formatting byte-identical to the interpreter) has to exist for wasm too; I/O goes through imports the host provides (a browser page, or WASI).
- Concurrency: wasm threads need shared memory and workers, and `SharedArrayBuffer` needs cross-origin isolation headers that static hosts such as GitHub Pages can't set; a first version runs one worker (D92's `MYLA_THREADS=1` order).
- What the website needs first is the self-hosted lexer, parser, checker (with its diagnostics and warnings) and interpreter compiled to wasm, behind a small API: check a source, run it with given input, give back output, diagnostics and positions.

## Done when

- [x] The platform layer for wasm ([[MYLA-162]]): host imports for output, files and time
- [x] The native parity programs give the same output under a wasm runtime
- [x] The self-hosted checker and interpreter run as wasm with an API a page can call

## The plan (2026-11-04, D125 with D122)

The owner chose wasm next, with D122 (sizes from a target description), which only a 32-bit backend can test, and decided wasm's open choices in D125: WASI preview 1, clang's wasm assembly and `wasm-ld`, a dispatch loop for control flow, one worker. Checked first: clang, `wasm-ld` and Node 22's WASI run a hand-written module (`fd_write`, a 10-million-deep `return_call` recursion, `proc_exit`).

Steps, each verified. The backend comes before D122's 4-byte layouts: the runtime in Myla ([[lib/std/rt.my]]) reads its cells at literal 8-byte offsets, so wasm first runs with today's layouts (addresses are 32-bit locals, a pointer in memory a zero-extended 8-byte word), and D122 then shrinks them, tested against a backend that works:
1. **The target:** `--target wasm32-wasi` in `gen_main` and `myla build` (clang, `wasm-ld`), the loader's `std/platform_wasm.my` over WASI imports, a runner for the tests (Node's WASI).
2. **`ir_wasm.my`:** the IR to wasm assembly: temporaries as locals, slots in a shadow stack in linear memory, the dispatch loop, calls (`call`, `call_indirect` through a table for function values, `return_call` for `become`), traps and positions, memory growth for the allocator.
3. **`runtime_wasm.my`:** the start (`_start`), the traps, the bulk copy and comparison, the counts of function values; then tasks on one worker.
4. **Parity:** the examples and the parity programs under Node's WASI against x86-64; the stress programs on one worker; CI.
5. **D122:** a target description (pointer size and alignment: 8 on the native targets, 4 on wasm32); sizes, field offsets, strides, cell headers, frame headers and std.rt's offsets computed from it; the native targets' code byte for byte the same, wasm's cells smaller.

## Progress

- 2026-11-04, steps 1 to 4: `--target wasm32-wasi` in `gen_main` and `myla build`; [[lib/std/platform_wasm.my]] over WASI preview 1; [[selfhost/ir_wasm.my]] (locals, the dispatch loop, the shadow stack, `return_call`); [[selfhost/runtime_wasm.my]] (the start, the WASI dispatcher, the runtime's functions, tasks on one worker, the module put together for clang); [[tools/wasm/run.mjs]] with a WASI shim of our own ([[tools/wasm/wasi.mjs]]), Node 22's own WASI crashing when the memory grows. Evidence ([[tests/burn/test_wasm.py]], 15 tests): every example and test_aarch64's programs as their x86-64 builds; files and directories; the 23 stress programs on one worker in five orders; test_time's timers; the compiler built for wasm compiles the compiler under Node as the native one does, for either target, and reaches the fixed point.
- D126 (2026-11-04): step 5, D122's 4-byte layouts, deferred to [[MYLA-260]]; wasm32 keeps 32-bit addresses on today's layouts.
- 2026-11-04, the page API: [[selfhost/play_main.my]] (`check` as JSON, `run`, `test`) built for wasm, [[tools/wasm/myla.mjs]] (`loadMyla`, `check`, `run`, `test`, files in memory), the WASI shim's core free of Node (backends [[tools/wasm/node_fs.mjs]] and [[tools/wasm/mem_fs.mjs]]), [[tools/wasm/page.html]] and `scripts/build-page.sh`. Evidence ([[tests/burn/test_wasm.py]]): `check` gives `myla check`'s 226 errors of the error corpus (kind, message, position); `run` and `test` give what `myla run` and `myla test` give on every example; input, arguments, a module, written files; the page in Chromium runs its example, shows a type error, reports a runtime error with its source line and an endless recursion as a stack overflow.
- Next ([[MYLA-159]], the website): running the interpreter in a Web Worker (a program that never ends), the editor; then a stackifier for speed, [[MYLA-260]] for memory.
