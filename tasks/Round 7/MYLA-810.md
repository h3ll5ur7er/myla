---
id: MYLA-810
title: "A function named `segv` (or `win_ctrl` on Windows) doesn't assemble: the runtime's label (M5)"
type: bug
status: review
priority: medium
labels: [codegen, labels, runtime, round-7]
---
Filed by [[MYLA-791]] for M5 of [[Project/Review-2026-11-17]] (`repro-r6/interp-harness/fn_named_segv.my`). D196 names a function's local labels `.L<name>_<n>`, `.L<name>_p<n>` and `.L<name>_ret`; the runtime's hand-written signal handler had `.Lsegv_ret` ([[selfhost/runtime_x86.my]], [[selfhost/runtime_a64.my]]) and Windows' console handler `.Lwin_ctrl_ret`, so a program's function `segv` or `win_ctrl` defined its epilogue twice: `Error: symbol '.Lsegv_ret' is already defined`.

- [x] The two labels renamed `.Lsegv_done` and `.Lwin_ctrl_done`
- [x] A test that no label has a function's form unless it is that function's, on x86-64, aarch64 and Windows, so a new runtime label can't bring it back
- [x] The program builds on x86-64, aarch64 and Windows and runs

## Evidence

- `tests/burn/test_label_names.py`, `test_no_other_label_reads_as_a_functions` (new): every label `.L<name>_(<n>|p<n>|ret)` of a program's assembly belongs to a function `myla_<name>` of it. Before: `.Lsegv_ret` on x86-64 and aarch64, `.Lwin_ctrl_ret` too on Windows; after: none.
- `test_a_function_may_be_named_like_a_runtime_label` (new): `segv` and `win_ctrl` as a program's functions. Before: the assembler failed on the three targets; after: built on all three, `21` and `2` natively, under qemu-aarch64 and under Wine.
- The rest of `test_label_names` passes as before.
