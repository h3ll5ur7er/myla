---
id: MYLA-259
title: "aarch64: debug information (-g)"
type: feature
status: backlog
priority: low
labels: [backend, platforms, debugging]
---
Split off [[MYLA-163]]: `myla build -g --target aarch64-linux` is refused for now. The aarch64 backend ([[selfhost/ir_a64.my]]) ignores `loc`, `bind` and `scope`, so there are no line tables or variables for gdb, and the DWARF the x86-64 path writes ([[Architecture/Native-backend#debug-information]]) names x86-64's registers (`%rbp`-relative variables, `DW_OP_breg6`).

- [ ] `.loc` lines from `loc` and the frame's CFA described for aarch64 (x29-based)
- [ ] variables and parameters as the frame cells they live in (`DW_OP_fbreg` against x29, or the heap frame's x28 in a frame function)
- [ ] the pretty-printers and the burn tests of [[tests/burn/test_debug_info.py]] under `gdb-multiarch` with qemu's gdbstub, where practical

- [ ] wasm: DWARF in custom sections (clang writes them from `.loc`), for browsers' devtools; [[MYLA-158]]
