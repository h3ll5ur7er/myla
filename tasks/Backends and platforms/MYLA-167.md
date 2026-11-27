---
id: MYLA-167
title: "LLVM: debug information"
type: feature
status: done
priority: low
labels: [llvm, debugging]
---
> [!NOTE]
> **Dropped by D117** (2026-11-02): Myla gets its own backends from the IR instead of LLVM ([[MYLA-62]], [[MYLA-160]]), so debug information through LLVM's metadata won't be built. Nothing of it was started. In `review` for the owner to close; the text below is the plan as it was.

With [[MYLA-161]]: `myla build -g --backend llvm` describes lines, functions and variables through LLVM's debug metadata instead of the hand-written DWARF ([[Development/Debugging]], [[MYLA-71]], [[MYLA-141]]), so gdb and the VS Code debugger ([[MYLA-99]]) work on LLVM-built binaries and on the new targets.

- [ ] Line tables, functions, parameters and locals (frame functions' slots in their heap frame, as [[MYLA-141]] describes them), types for the pretty-printers (D82) (dropped by D117: no LLVM backend)
- [ ] The gdb tests of `tests/burn/test_debug_info.py` pass with `--backend llvm` (dropped by D117: no LLVM backend)

LLVM was dropped by D117; closed with the owner's agreement (2026-11-05).
