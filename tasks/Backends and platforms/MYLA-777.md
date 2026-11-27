---
id: MYLA-777
title: "Windows: CodeView and a PDB for Visual Studio and WinDbg"
type: feature
status: backlog
priority: low
labels: [platforms, windows, debugging]
---
The step after [[MYLA-757]] (DWARF in the `.exe`, for gdb and lldb), if the owner takes its third proposal: the Microsoft debuggers read CodeView from a PDB, not DWARF, so a Myla program shows them neither lines nor variables. MYLA-757's proposal has the cost and the alternatives; in short: the code generator writes CodeView records into the object's `.debug$S` and `.debug$T` sections beside the DWARF (clang's `.cv_file`, `.cv_func_id` and `.cv_loc` give the line table as `.file` and `.loc` give DWARF's; the symbols and types are data, as `.debug_info` is), `lld-link /debug` builds the PDB from them, and a `.natvis` file shows Myla's cells as the gdb printers do (D82).

Not before [[MYLA-776]] (unwind tables): without `.pdata` those debuggers' call stacks stop at the first Myla frame.

- [ ] CodeView line tables, functions, parameters and locals (`S_GPROC32`, `S_REGREL32` from `%rbp`, `S_BLOCK32`), and types (structs, tuples, enums as a union with a tag, lists, `str`) for `-g --target x86_64-windows`; the DWARF as it is
- [ ] The link keeps both (`/debug` with the DWARF kept, or a flag of `-g`'s, measured); a `.natvis` for `str`, lists, builders and maps, embedded with `/natvis`
- [ ] Tests: `llvm-pdbutil dump` on Linux; on the runner, cdb (the Windows SDK's debugger, if the image has it) stopping on a line and printing a local
