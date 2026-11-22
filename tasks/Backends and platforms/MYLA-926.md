---
id: MYLA-926
title: "CI's tests on native runners: Windows on windows-latest, aarch64 on ubuntu-24.04-arm (D296)"
type: chore
status: in-progress
priority: medium
labels: [ci, windows, aarch64, testing]
---
D296 (the owner, 2026-11-19): tests run on native runners, and Wine and qemu stay for local experiments only. Today CI's `targets` job runs the burn suites under qemu-aarch64 and under Wine on an x86-64 Linux runner. The `burn` job also installs Wine for `test_windows` and `test_debug_info`. That emulation was behind most of round 7's flaky failures: Wine's services holding a program's pipes ([[MYLA-759]]), its prefix being set up while the suites ran, and t15 under Wine ([[MYLA-781]]). It is also behind the 45-minute apt installs. qemu runs instructions in program order, so it can't show a memory-ordering bug at all.

Python stays the harness for now: it is 3 to 9 percent of a suite's CPU time (2026-11-19, `02fc265`: `test_compiler_parity` 3.4 s of 109.6 s, `test_http` 1.3 s of 26.0 s, `test_error_corpus` 0.6 s of 7.1 s), and its oracles (`repr`, `decimal`, `tomllib`, `zlib`, …) are independent of Myla's code.

**Step 1: aarch64.** CI already has `ubuntu-24.04-arm` (`bootstrap-arm64`: the bootstrap, the stress and litmus programs). Run the whole burn suite there as the host (`scripts/test.sh`, `TEST_TARGET` unset). The tests that assume an x86-64 host (those that read x86-64 assembly, the x86-64 seed) then need to key on the host's architecture, not only on `TEST_TARGET`. Then drop qemu from the `targets` job and from the burn job's apt, along with the timing limits that are looser only under an emulator.

**Step 2: Windows.** Run the burn suites on `windows-latest` against `myla.exe` (the `bootstrap-windows` job builds it; the image has LLVM and Python). Port each POSIX-only test, or mark it Linux-only with its reason (`/proc`, signals, ptys, `fcntl`, `strace`), never skip one silently. Keep `scripts/windows-runner.py`'s cases as the Windows-only layer. Then drop the Wine job and Wine from the Linux jobs' apt.

Windows' loopback is not Linux's, which three of test_net's tests assume. Seen on the owner's workstation in WSL2 with `networkingMode=mirrored` (2026-11-19, `d7e65c1`), where localhost goes through Windows' network stack:
- `Primitives.test_each_on_its_own`: an `accept` right after the client's connect completed said would-block, and a datagram sent to itself wasn't there yet when read at once.
- `Tcp.test_a_listeners_backlog`: all 200 connects completed with the default backlog, not Linux's 128 + 1 (200 is Windows' own backlog); 164 and 185 in another run.
- `Tcp.test_a_blocking_read_that_holds_the_only_worker_says_so` (built): no warning within 30 s.

On `windows-latest` these need to wait for what they read (a poll of the listener or the socket first) or key their counts on the platform.

Each step drops the emulated job only once the native one has been green beside it for a while, so no coverage is lost on the way.

- [x] aarch64: the burn suite on `ubuntu-24.04-arm`, host-architecture keys for the x86-64-only tests
- [ ] aarch64: qemu off CI (the `targets` job's entry, apt, emulator-only limits)
- [ ] Windows: the burn suites on `windows-latest`, each POSIX-only test ported or marked with its reason
- [ ] Windows: Wine off CI (the Wine job, Wine in the Linux jobs' apt)
- [ ] `docs/Development/Testing.md`, the skill's CI table and [[Language/Targets]] say where each target is tested

## Evidence (step 1, 2026-11-22)

The `burn-arm64` job on `ubuntu-24.04-arm` (`scripts/test-target.py host`), on the branch:

| Run | Head | Result |
|---|---|---|
| 45004595333 | `20088f5` | cancelled at 75 min (`unittest discover`, serial); some 70 tests failed, no tracebacks |
| 45011729950 | `7725ae0` | 105 of 114 suites, 35 min |
| 45016466400 | `43e721a` | 113 of 114 (`test_wasm.test_compiler`, its reference the machine's own default), 33 min |

What the tests assumed of an x86-64 machine, now keyed on it (`_native.HOST_TARGET`, `AS_CMD`, `READS_X86`): the x86-64 seed and `as --64` (`_tools`, sixteen suites), the x86-64 assembly and registers read (codegen, float registers, loop overhead, register arguments, small and byte copies, packed lists, overflow, `test_raw_memory`'s `call`, gdb's `$rdi`), `-g` (x86-64 Linux's and Windows' alone: `test_debug_info`, `test_installed`, the debugger, a project's `-g` build), the host's name in messages (`test_selfhost_cli`, `test_test_native`, `test_label_names`), and an x86-64 reference build (`test_wasm`). Two tests were too slow for the slower machine and changed: `test_selfhost_parser`'s linear-time bound is relative now, and `num`'s `pow10_sig_is_exact` makes each power of ten from the one before (15.8 s interpreted on x86-64, 10.3 s now). The slowness itself is [[MYLA-929]].
