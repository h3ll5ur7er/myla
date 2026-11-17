---
id: MYLA-758
title: "One Linux platform layer for x86-64 and aarch64, over the generic system calls"
type: refactor
status: todo
priority: low
labels: [platforms, linux]
---
[[MYLA-716]]'s sixth proposal, which the owner accepted on 2026-11-17 as a task of its own after Windows' wave 6.

`lib/std/platform.my` (x86-64 Linux) and `lib/std/platform_aarch64.my` are 2,083 and 2,096 lines and differ in 47 places, 229 lines:
- 158 of those lines are system-call numbers;
- 44 are code: the `*at` calls, `AT_FDCWD`, `clone` for `fork`, `ppoll`, `epoll_pwait`, `stat`'s mode offset and `EVENT_DATA`;
- the rest are comments.

The recommended form, from MYLA-716:
1. x86-64 moves to the generic calls aarch64 already uses (`openat`, `mkdirat`, `unlinkat`, `renameat2`, `dup3`, `ppoll`, `epoll_pwait`, `clone`). This changes x86-64's assembly in every program.
2. The numbers and the two layout constants go into a module with a copy per architecture (`std/linux_calls.my` and `std/linux_calls_aarch64.my`, D223).
3. `platform_aarch64.my` goes, and aarch64's target record gets `platform_file: ""`.

That is about 250 changed lines.

The alternative, a shared `platform_linux.my` that both modules import, would need each of the 85 `pub` functions declared again in each module, for the interface test and for the loader's one module per target.

Proposed row: *"Linux's platform layer is one module on both architectures, over the generic system calls; the numbers and layouts are a per-architecture copy (D223)."*

- [ ] x86-64's platform module uses the generic calls, with the suites' `strace` on x86-64 compared before and after
- [ ] The numbers and layouts in a per-architecture copy module; `platform_aarch64.my` removed
- [ ] The bootstrap's fixed point on both architectures, and both seeds still bootstrap the sources (a `Stage:` commit if not, D207)
- [ ] `scripts/test-target.py aarch64-linux` and the full suite pass
