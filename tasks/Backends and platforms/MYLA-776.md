---
id: MYLA-776
title: "Windows: unwind tables (.pdata, .xdata) for the x64 code"
type: improvement
status: backlog
priority: low
labels: [backend, platforms, windows, debugging]
---
Found by [[MYLA-757]]: a Windows program has no unwind information. x64 Windows describes every function that isn't a leaf by a `RUNTIME_FUNCTION` in `.pdata` and its unwind codes in `.xdata` (clang writes them from `.seh_proc`, `.seh_pushreg`, `.seh_setframe`, `.seh_stackalloc`, `.seh_endprologue`, `.seh_endproc`). gdb doesn't need them for Myla's code (it follows `%rbp`, as [[tests/burn/test_debug_info.py]]'s session under Wine shows), but Windows' own stack walkers do: WinDbg's and Visual Studio's backtraces, `RtlVirtualUnwind`, profilers (ETW, VTune) and any C++ exception or `longjmp` passing through Myla frames once there is an FFI ([[MYLA-166]]). Without an entry a function is taken for a leaf, so a walk stops at the first Myla frame.

- [ ] The prologue and epilogue of [[selfhost/ir_x86.my]] (and the runtime's assembly functions with a frame) described by `.seh_*` directives on Windows only; Linux's output byte for byte the same
- [ ] A test that `llvm-readobj --unwind` lists every function of a Windows program, and that a walk with `RtlVirtualUnwind` (or WinDbg's `k` on the runner) from a runtime error's frame reaches `_start`
- [ ] Measured: the `.exe`'s size and the build's time against today's
