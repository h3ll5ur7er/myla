---
id: MYLA-269
title: "An object model instead of GAS text"
type: improvement
status: backlog
priority: medium
labels: [backend, platforms, architecture]
---
Found by [[Project/Reflection-2026-11]]. `assemble_source` writes GAS/ELF text for every target:
- sections, `.quad` records and `.set` aliases;
- a fixed `.bss` list (`__free_buckets`, the timers, `TLS_SIZE * MAX_WORKERS`);
- `.note.GNU-stack`.

x86-64 and aarch64 keep an environment's deep copies as data in front of its drop function. wasm re-parses the text: `wasm_module` (about 290 lines) resolves the aliases, rewrites pointer words as 32-bit words plus 0, and sizes every data label. Mach-O (symbol prefixes, sections) and COFF would hit the same assumptions.

- [ ] A model of what a module holds: functions, data items (bytes, words of the pointer size naming a symbol, zero space), sections, aliases, the runtime's variables. Rendered per format: GAS for ELF, Mach-O assembly, COFF, LLVM's wasm assembly. `wasm_module`'s text rewriting goes.
- [ ] Then a writer of the binary formats in Myla where it pays: wasm modules (D125 (2): the toolchain building wasm in a page), ELF without `as`/`ld` (a quarter of a build is `as`, [[MYLA-160]])
