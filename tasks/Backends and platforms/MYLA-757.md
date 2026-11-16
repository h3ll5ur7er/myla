---
id: MYLA-757
title: "Debug information on Windows: `myla build -g --target x86_64-windows`"
type: feature
status: todo
priority: medium
labels: [platforms, windows, debugging]
---
A step of [[MYLA-165]], the Windows target (wave 6). `selfhost/target.my` says `debug_info: false` for x86_64-windows, so `-g` is refused there ("D216: debug information later"). [[MYLA-160]]'s plan for it: "on Windows DWARF first (gdb, lldb), CodeView/PDB for the Microsoft debuggers later (the PDB container is the expensive part)". Linux's hand-written DWARF is [[selfhost/dwarf.my]] (D82), with the gdb script `-g` embeds.

- [ ] `myla build -g --target x86_64-windows` gives an `.exe` whose DWARF (in COFF sections, as clang and lld-link carry it) names Myla's source lines, functions and variables as Linux's does
- [ ] A test under Wine (or with `llvm-dwarfdump`/`llvm-objdump` on the `.exe`) that a function's address maps to its `.my` line, and that a build without `-g` is byte-identical to today's
- [ ] On the Windows runner (`scripts/windows-runner.py`): a case that checks the same with the image's LLVM tools, if they read it there
- [ ] CodeView/PDB: a proposal (cost, what it gives Visual Studio and WinDbg users), not built
