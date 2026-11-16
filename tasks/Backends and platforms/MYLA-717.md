---
id: MYLA-717
title: "Windows: probe the stack for a frame larger than a page"
type: bug
status: review
priority: high
labels: [platforms, windows, backend]
---
Found while building [[MYLA-702]]. Windows commits a thread's stack a page at a time, below a guard page: touching memory more than one page below the committed part, past the guard page, is an access violation instead of a growth. MSVC and clang call `__chkstk` for a frame of 4 KiB or more, which touches each page in turn. The x86-64 backend's prologue is `subq $N, %rsp` with no probe, so a function whose frame is a page or larger can fault on real Windows when its first store lands beyond the guard page. The compiler itself, built for `x86_64-windows`, has 18 functions with frames of 4 KiB or more, the largest 21,440 bytes (`build/stage3 selfhost/gen_main.my lib --target x86_64-windows | grep -oE 'subq \$[0-9]+, %rsp'`, 2026-11-15, MYLA-702's branch).

Wine maps the whole stack it reserves, so the suites under Wine can't show this ([[MYLA-708]]'s Windows runner can). The main thread reserves 120 MiB (`/stack:125829120`) and commits as it grows.

- [x] On Windows, a prologue whose frame is 4 KiB or more touches each page from the top down (a loop of `subq $4096, %rsp; orq $0, (%rsp)`, or a call of a probe routine of the runtime's), as `__chkstk` does; Linux's code unchanged
- [ ] A test: a recursion through a function with a 64 KiB frame, on the Windows runner ([[MYLA-708]]) — written (`tests/burn/test_windows.py`'s `FRAMES`): `FramesOnWindows` runs it under Wine, which commits the whole stack, and [[MYLA-708]]'s `windows` job on Windows itself (`scripts/windows-runner.py`'s `frames/64-kib`, on 1, 2 and 16 workers); open until that job's first run, on the pull request
- [x] Workers' stacks ([[MYLA-703]]) get the same: `CreateThread`'s stack is committed the same way

## What changed

[[selfhost/ir_x86.my]]: on Windows (`CodeGen.windows`), a function whose frame is 4 KiB or more starts with `stack_probes(frame + 8)`: `orq $0, -4096(%rsp)`, `-8192(%rsp)`, … and last `-(frame + 8)(%rsp)`, the lowest byte the push of %rbp and the frame take, a page at a time from the top down, before the stack pointer moves. Probing below the stack pointer, rather than the task's loop of `subq $4096, %rsp; orq $0, (%rsp)`, needs no register (every one may hold an argument at the entry) and leaves the prologue's own lines as they are, so `drop_unused_frame` still reads them; unrolled, as the frames are known when compiling (the compiler's largest takes 6 probes). A frame below a page needs none: the call's push touched the page above it, and the frame stays within the page below, the guard page at worst. The workers' stacks ([[MYLA-703]]) are `CreateThread`'s, 8 MiB reserved (`STACK_SIZE_PARAM_IS_A_RESERVATION`) and committed as they grow, so the same probes serve them; the main thread's is the linker's (`/stack`).

## Evidence

- **Test first.** `tests/burn/test_windows.py`'s `StackProbes.test_a_frame_of_a_page_or_more_is_probed` builds a program whose `down` has a 64 KiB frame (a struct of 64 KiB and its copy) for `x86_64-windows` and reads its prologue. With BASE's compiler (`194c9dc`: the new tests run with the module's `selfhost_tool` and `STDLIB_ROOT` pointed at BASE's `myla`, `stage3` and `lib/`): `AssertionError: Lists differ: [] != ['\torq $0, -4096(%rsp)', …]`. On this branch: 17 probes from `-4096(%rsp)` to `-65560(%rsp)`, then `pushq %rbp`, `movq %rsp, %rbp`, `subq $65552, %rsp`; `test_linux_has_none` holds Linux's prologue to `pushq %rbp` first. `stack_probes`' own cases 2/2 (`build/myla test selfhost/ir_x86.my`: 73/73).
- **The compiler built for Windows**: 18 functions probed, 41 probes in all (`build/stage3 selfhost/gen_main.my lib --target x86_64-windows | grep -c 'orq $0, -4096(%rsp)'`, 2026-11-15); its assembly 28,400,478 bytes against BASE's 28,357,445 (with [[MYLA-703]]'s thread-state loads).
- **Under Wine** the 64 KiB-frame recursion prints `3836` from the main thread 100 deep and `4632` from two tasks 60 deep, as on Linux; BASE's build does the same there, as Wine commits the whole stack: the run on Windows is `FramesOnWindows.test_a_recursion_through_a_64_kib_frame`, skipped under Wine ([[MYLA-708]]'s runner, whose task names it).
- **Linux, aarch64 and wasm32** write byte-identical assembly (see [[MYLA-703]]'s evidence); `scripts/test-target.py x86_64-windows` 38 of 38 suites.
