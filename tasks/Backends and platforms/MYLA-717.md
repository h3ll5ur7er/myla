---
id: MYLA-717
title: "Windows: probe the stack for a frame larger than a page"
type: bug
status: todo
priority: high
labels: [platforms, windows, backend]
---
Found while building [[MYLA-702]]. Windows commits a thread's stack a page at a time, below a guard page: touching memory more than one page below the committed part, past the guard page, is an access violation instead of a growth. MSVC and clang call `__chkstk` for a frame of 4 KiB or more, which touches each page in turn. The x86-64 backend's prologue is `subq $N, %rsp` with no probe, so a function whose frame is a page or larger can fault on real Windows when its first store lands beyond the guard page. The compiler itself, built for `x86_64-windows`, has 18 functions with frames of 4 KiB or more, the largest 21,440 bytes (`build/stage3 selfhost/gen_main.my lib --target x86_64-windows | grep -oE 'subq \$[0-9]+, %rsp'`, 2026-11-15, MYLA-702's branch).

Wine maps the whole stack it reserves, so the suites under Wine can't show this ([[MYLA-708]]'s Windows runner can). The main thread reserves 120 MiB (`/stack:125829120`) and commits as it grows.

- [ ] On Windows, a prologue whose frame is 4 KiB or more touches each page from the top down (a loop of `subq $4096, %rsp; orq $0, (%rsp)`, or a call of a probe routine of the runtime's), as `__chkstk` does; Linux's code unchanged
- [ ] A test: a recursion through a function with a 64 KiB frame, on the Windows runner ([[MYLA-708]])
- [ ] Workers' stacks ([[MYLA-703]]) get the same: `CreateThread`'s stack is committed the same way
