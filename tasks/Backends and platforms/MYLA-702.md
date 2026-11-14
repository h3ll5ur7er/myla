---
id: MYLA-702
title: "Windows step 3: hello world as a static .exe"
type: feature
status: todo
priority: high
labels: [platforms, windows]
---
A step of [[MYLA-165]], the Windows target, in the plan the owner accepted on 2026-11-14 ([[Project/Follow-up-plan#windows-2026-11-14]]). D209, D210, D211, D213: the x86-64 backend emits COFF (`.rdata`, no `.type`/`.size`, Win64 at the boundary to kernel32 only, D130), clang assembles it, `llvm-dlltool` makes the import libraries from a list of names, `lld-link` links; the start code reads the command line and environment from kernel32, thread-local state through `gs:` (the TEB).

- [ ] `myla build --target x86_64-windows hello.my` gives a static `hello.exe` that prints under Wine
- [ ] Wine as the target's emulator in `scripts/test-target.py` and `tests/burn/_targets.py` (`MYLA_EMULATOR`), as qemu is for aarch64; the suites that run report what is still `Unsupported`
- [ ] CI's `targets` job runs `x86_64-windows` under Wine
- [ ] The console in UTF-8 (`SetConsoleOutputCP`), `\n` written as is (D214)
