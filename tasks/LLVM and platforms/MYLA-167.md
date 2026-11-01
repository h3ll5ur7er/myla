---
id: MYLA-167
title: "LLVM: debug information"
type: feature
status: backlog
priority: low
labels: [llvm, debugging]
---
With [[MYLA-161]]: `myla build -g --backend llvm` describes lines, functions and variables through LLVM's debug metadata instead of the hand-written DWARF ([[Development/Debugging]], [[MYLA-71]], [[MYLA-141]]), so gdb and the VS Code debugger ([[MYLA-99]]) work on LLVM-built binaries and on the new targets.

- [ ] Line tables, functions, parameters and locals (frame functions' slots in their heap frame, as [[MYLA-141]] describes them), types for the pretty-printers (D82)
- [ ] The gdb tests of `tests/burn/test_debug_info.py` pass with `--backend llvm`
