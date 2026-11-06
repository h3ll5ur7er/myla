---
id: MYLA-285
title: Raw-memory primitives are callable from a program with a warning
type: bug
status: todo
priority: high
labels: [checker, safety]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]). D100 made calling a `__` primitive from a program a warning, written for the I/O primitives. `__load64`, `__store64`, `__free`, `__addr_of`, `__copy_bytes`, `__call_code` and the other raw-memory primitives (`is_raw_memory_primitive` in [[selfhost/checker.my]]) are under the same warning: `print(__load64(0))` passes `check` and segfaults natively with no `runtime error` line (`__on_segv` reports only stack faults); `__free(__load64(__addr_of(s)))` frees a live string. The interpreter refuses them (`'__load64' reads and writes raw memory, which only native code does`). `build/myla build selfhost/main.my` prints 36 such warnings from `interp.my`, which implements them.

- [ ] A call of a raw-memory primitive outside `std$` (and outside the self-hosted interpreter's own module, which implements them) is an error in the checker; the I/O primitives keep D100's warning
- [ ] An error-corpus file; the 36 warnings from `interp.my` gone (the interpreter's uses allowed by its module, or the primitives reached another way)
