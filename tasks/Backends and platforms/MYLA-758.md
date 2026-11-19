---
id: MYLA-758
title: "One Linux platform layer for x86-64 and aarch64, over the generic system calls"
type: refactor
status: review
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

- [x] x86-64's platform module uses the generic calls, with the suites' `strace` on x86-64 compared before and after
- [ ] The numbers and layouts in a per-architecture copy module; `platform_aarch64.my` removed (the copy module is in; the removal is the second half, which waits for a `Stage:` commit: below)
- [ ] The bootstrap's fixed point on both architectures, and both seeds still bootstrap the sources (a `Stage:` commit if not, D207): the fixed point holds and every seed bootstraps the first half; aarch64's seed can't bootstrap the second, which needs wave 2's `Stage:` commit
- [x] `scripts/test-target.py aarch64-linux` and the full suite pass

## What changed

In two halves, because aarch64's seed can't bootstrap the second (D207, below).

**The first half** (this branch, both seeds bootstrap it):
- **x86-64 makes the generic calls** ([[lib/std/platform.my]]): `openat` for `open`, `newfstatat` for `stat` and `lstat`, `mkdirat`, `unlinkat` (with `AT_REMOVEDIR` for `rmdir`), `renameat2`, `dup3` for `dup2`, `ppoll` for `poll`, `epoll_pwait` for `epoll_wait`, and `clone(SIGCHLD)` for `fork`. `wait4` now passes its fourth argument as 0 (`sys5`). The module is aarch64's code line for line: `diff` of `platform.my` against `platform_aarch64.my` shows only the header, the imports and comments, and the constants of the new module where aarch64's has its numbers.
- **std.linux_calls** ([[lib/std/linux_calls.my]], [[lib/std/linux_calls_aarch64.my]], D223): the 56 system-call numbers, checked against the kernel's headers (`asm/unistd_64.h` and `asm-generic/unistd.h`); `TARGET_NAME`, which std.platform's `TARGET` is; and what differs in layout. That turned out to be more than the task's "two layout constants": `STAT_SIZE` (144 or 128), `STAT_MODE` (24 or 16), `EVENT_SIZE` (12 or 16), `EVENT_DATA` (4 or 8), `O_DIRECTORY` (0x10000 or 0x4000), and `SA_RESTORER` with `sig_restorer()`. On x86-64 that function is `__rt_addr("__sig_restorer")`; on aarch64 it is 0, since aarch64's runtime has no such label and its kernel returns through a trampoline of its own. platform.my imports them with eight `from .linux_calls import` lines, so no call site had to change its names.
- **The loader** ([[selfhost/loader.my]] `for_target`, [[selfhost/target.my]]): a target's own copies of modules end as its record's new `copies` field says (`_aarch64.my`, `_wasm.my`, `_windows.my`, "" for x86-64). D223 named them after the platform module, and aarch64 will have none. `copied_modules()` lists the modules (path, path_style, system_error, linux_calls) for `for_target`, `for_host` and the driver's `harness_entry` ([[selfhost/driver.my]], whose `copy_key` takes the ending now; the driver is the Interpreter-and-harness lane's file).
- **Tests**: `test_platform_interface` reads Linux's `TARGET` through `TARGET_NAME`, and holds `linux_calls_aarch64.my` to `linux_calls.my`'s names and types (`TargetCopies`). The website's internal modules (`tests/burn/test_website.py`, `website/scripts/prepare.mjs`) gain the two copies.

**The second half** (its one commit on the branch ``myla-758-second-half``, not on this branch): `platform_aarch64.my` goes, aarch64's record gets `platform_file: ""`, lower.my's `checked_code` drops `std$platform_aarch64$`, and the tests and docs that named the module follow (`test_std_modules`, `test_test_native`, `test_aarch64`, `test_platform_interface`, the `myla` skill, [[Language/Attributes-and-testing]]). It needs a `Stage:` commit first. aarch64's seed reads `std/platform_aarch64.my` for std.platform. With the file gone, it finds no copy carried by `gen_main` and overrides std.platform with an empty text: `module '.platform' does not export 'TARGET'` at `lib/std/process.my:7` (`MYLA_ARCH=aarch64 … scripts/check-seed.sh` under qemu, exit 2). The order D207 asks for is: the first half (the compiler's side: `copies`, `linux_calls_aarch64.my`), then a `Stage:` commit of the seeds (wave 2's lane), then the second half. That half was built and tested in full before it was split off; the evidence below says which half each result is from.

## Proposals

1. **A target's copies are named by a field of their own, `Target.copies`** (built). Alternatives: *(a)* derive the ending from the architecture's name (`"_" + arch`), which gives `_x86_64`, not `_windows`, for Windows and `_wasm32` for wasm32, so the existing files would have to be renamed; *(b)* keep a `platform_file` for aarch64 that names no file, which `for_target` would try to read on every build; *(c)* name the copies after the platform module, as D223 does, which aarch64 can't do once it has none. Proposed row (refining D223): *"A target's own copy of a module ends as the target's record says (`copies`: `path_windows.my` on Windows, `linux_calls_aarch64.my` on aarch64), not after its platform module, which a target may share (MYLA-758)."*
2. **What differs between the architectures, beyond the numbers** (built: six constants and one function in std.linux_calls). The alternative was to keep the largest `struct stat` (144 bytes) on both, which saves one constant at the cost of 16 bytes per call on aarch64. I took the exact sizes.
3. **The order of the halves** (D207 settles it): the second half waits for a `Stage:` commit. If the owner wants one commit instead, wave 2's `Stage:` commit can go between the two.

Proposed row for the task (as the task gives it): *"Linux's platform layer is one module on both architectures, over the generic system calls; the numbers and layouts are a per-architecture copy (D223)."*

## Evidence

- **strace on x86-64, before and after** (`strace -f -ff` of `python3 -m unittest` for test_fs, test_stdio, test_process, test_platform_primitives, test_platform_interface, test_net, test_term, test_http, test_timer_scaling, test_reactor_scaling and test_examples_run; each Myla-built process's calls by name, its threads' and its forked child's calls before exec counted as its own; BASE `3add216`'s tree against this change's, 2026-11-18). Over every suite, 54 names are the same. Only before: `open`, `stat`, `lstat`, `mkdir`, `rmdir`, `unlink`, `rename`, `poll`, `epoll_wait`, `fork`, `dup2` (and `close_range`, once, in one `myla` process: noise, std calls none). Only after: `openat`, `newfstatat`, `mkdirat`, `unlinkat`, `renameat2`, `ppoll`, `epoll_pwait`, `dup3`. Per program the same substitutions, for example test_fs's programs `-mkdir -open -rmdir -unlink +mkdirat +openat +unlinkat`, test_process's `-dup2 -epoll_wait -fork -poll +dup3 +epoll_pwait +ppoll`, and the toolchain's own `myla` and interpreter likewise. The other per-program differences are runs that went differently under strace (a `nanosleep` and a `restart_syscall` in one tool run). Under strace, timing tests failed in both runs (test_http's `test_kept_connections_wait_parked`, test_reactor_scaling's `test_round_trips_beside_tasks_that_only_yield`, 75 round trips where 1,000 are wanted). After, so did the new `FailedPipeRead` ([[MYLA-862]]), which can't run strace under strace.
- **Sizes**: `examples/maps.my` built for x86-64 went from 30,472 to 30,344 bytes, and for aarch64 from 64,776 to 64,512 (both halves; the aarch64 change is the exact `struct stat` and MYLA-862's `run_with`). The compiler reaches the fixed point at 30,398,437 bytes in the first half and 30,006,184 in the second. The second carries no `platform_aarch64.my` in its embedded library.
- **Check cost** (callgrind, `MYLA_THREADS=1`, the library the tools carry, BASE against the second half): a hello world's `myla check` went from 21,405,002 to 21,407,798 instructions and its `myla run` from 24,327,287 to 24,330,096. A program importing std.io checks in 39,321,814 instead of 39,318,652, and one importing std.fs in 43,848,216 instead of 43,844,540.
- **Seeds**: `scripts/check-seed.sh` passes with x86-64's seed on both halves. aarch64's seed under qemu (`MYLA_ARCH=aarch64 AS=aarch64-linux-gnu-as LD=aarch64-linux-gnu-ld MYLA_RUN=qemu-aarch64`) fails on the second half (above). On the first half it bootstraps the sources to the fixed point, and so does Windows' seed under Wine 9.0 (`MYLA_OS=windows MYLA_RUN=wine64`).
- **Cases**: `build/myla test` passes for lib/std/platform.my (54/54: interpreted, `--native`, and `--target aarch64-linux` in the second half), platform_aarch64.my (54/54: interpreted and under qemu, first half), selfhost/driver.my (43/43), loader.my (194/194), target.my (7/7) and lower.my (159/159). test_platform_interface and test_embedded_std pass.
- **Suites**: `scripts/test-target.py aarch64-linux` on the second half: 38 of 39 suites passed. The one failure was `test_children_run_in_parallel` (cpu 4.44 s, wall 5.15 s), a known timing test (MYLA-745); `test_selfhost_codegen` alone then passed. On the first half, `scripts/test-target.py aarch64-linux` passes for test_fs, test_stdio, test_process, test_platform_primitives, test_platform_interface, test_net and test_term (7 of 7). Host runs of the second half's own tests pass: test_platform_interface, test_std_modules' module list, test_test_native's `TestAarch64` (its platform module under every spelling of the paths) and test_embedded_std. `scripts/test.sh` (all, `TMPDIR` unset for Wine) at `4f60cb6`, 2026-11-18: 1,856 tests, OK (394 skipped), in 2,501 s. A first `scripts/test.sh fast` with `TMPDIR` set had 103 failures, all of them Wine aborting at once with `free(): invalid pointer` (test_windows, test_debug_info under Wine), which is the container's known trouble; without `TMPDIR` they pass in the full run.
