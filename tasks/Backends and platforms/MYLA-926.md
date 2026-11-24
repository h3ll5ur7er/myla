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

## Evidence (step 2, 2026-11-24)

The `burn-windows` job on `windows-latest` (`python scripts/test-target.py host`), on the branch:

| Run | Head | Suites | Result |
|---|---|---|---|
| 45337804748 | `5006f69` | the 39 of the Wine job | stopped printing its logs (cp1252: `PYTHONUTF8`, UTF-8 logs) |
| 45342580451 | `82856b0` | 39 | 25 of 39 in 5 min (the Wine job: 8 min) |
| 45346263902 | `9b25804` | 39 | 30 of 39: the loader's Windows paths ([[MYLA-931]]) |
| 45353314368 | `2f48251` | 39 | 36 of 39 (test_http: [[MYLA-933]]) |
| 45358031010 | `b2c1061` | all 114 | 94 of 114 in 19 min |
| 45365757361 | `b7c3965` | 114 | 95: test_http passes ([[MYLA-933]]) |
| 45371789872 | `640e5c8` | 114 | 111: groups A–E ([[MYLA-934]], [[MYLA-936]], [[MYLA-937]], [[MYLA-938]], [[MYLA-940]], [[MYLA-941]], [[MYLA-942]], [[MYLA-943]]) |
| 45378102638 | `fd0abe0` | 114 | 111 (test_std_cache: the PE time stamp) |
| 45384362001 | `692f445` | 114 | 112: left [[MYLA-944]] (a wasm32 harness's scratch directory on another drive) and test_http's `test_kept_connections_wait_parked` at 4.532 s of its 4.5 ([[MYLA-945]]) |

What the suites assumed of Linux, ported: the build sites (`_native.assemble`, `.exe`), POSIX modules imported where they're used, process groups and signals (`taskkill`, `CTRL_BREAK_EVENT`), a reader thread for `select` on pipes, text-mode files and input (CRLF), `\` in expected paths (`_native.shown`), `relpath` across drives, Git's read-only objects, an executable still held a moment after its process, `nul` as a name, `/bin/echo`, Windows' loopback (a refused connect retried for 2 s), the exit code's 32 bits (D216), a handle number that is open, the UCRT's `expm1`. What they found in Myla, fixed: the loader's and the project tool's paths ([[MYLA-931]], [[MYLA-930]]), interp_main's library ([[MYLA-932]]), a parked socket's close and Winsock's send buffering ([[MYLA-933]]), CRLF in manifests and diagnostics ([[MYLA-934]], [[MYLA-941]]), a test program's CRLF block ([[MYLA-936]]), read-only files ([[MYLA-937]]), the language server's URIs ([[MYLA-938]]), the interpreter's environment ([[MYLA-942]]), the driver's drive paths and an exit past 255 ([[MYLA-943]]), and `lld-link`'s time stamp (`/Brepro`: a Windows program builds to the same bytes each time). Linux unchanged: the `burn` job, the Wine job and `burn-arm64` (114 of 114) pass on the same heads. The Wine job's `test_children_run_in_parallel` failed twice in seven runs (runs 275 and 281) and passes natively: Wine's, one more reason to retire it.
