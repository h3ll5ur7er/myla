---
id: MYLA-592
title: "Native: a SIGSEGV sent by `kill` is swallowed once"
type: bug
status: review
priority: low
labels: [runtime, native, signals, round-6]
---
Found by [[MYLA-548]] (the runtime lane of round 6) with the review's `t_raw.py`, beside D192. The stack overflow handler `__on_segv` ([[selfhost/runtime_x86.my]], `runtime_a64.my`) takes every SIGSEGV for a fault: one whose address isn't near a stack gets its default action back and returns, so that the fault happens again and kills the program. A SIGSEGV sent by another process (`kill -SEGV`, `si_code` SI_USER) faults nothing again, so the program goes on as if nothing came; only a second one kills it.

```myla
import std.task as task
from std.io import println

#main
async fun main() {
    println("ready")
    await task.sleep(3000)
    println("still running")
}
```

Built (`build/myla build`) and sent one `kill -SEGV` half a second in: `ready`, then `still running` and exit status 0, where a program dies of the signal (status -11, as a C program does). In raw mode the terminal then stays raw as well. Base `07445ab` and after MYLA-548.

- [x] `__on_segv` tells a signal sent (`si_code` <= 0: SI_USER, SI_TKILL, SI_QUEUE) from a fault and ends the program as the signal would (the default back, the signal sent again), on x86-64 and aarch64
- [x] A case that sends SIGSEGV to a sleeping program and expects it killed by it

## What changed

`__on_segv` ([[selfhost/runtime_x86.my]], [[selfhost/runtime_a64.my]]) reads `si_code` (siginfo + 8) first, into a register the system calls keep (`%r9d`, `x10`). A signal sent (`si_code` at most 0) skips the stack overflow test (its siginfo + 16 is the sender's pid and uid, not an address) and goes where any other fault goes: the default action back. Then, for a sent one only, the handler calls `__on_raw_signal(11)` (std.platform's `raw_signal`, D192's handler: it puts a raw terminal's mode back from the exit hook's block and sends the signal again with `kill`) and returns; the signal, pending with its default, ends the program, status -11 as a C program's, the terminal cooked. A fault returns as before and happens again. wasm32 has no handler: Node already died of the signal (-11, before and after).

## Evidence

`never.my` (the reproducer: `ready`, a sleep of 3 s, `still running`), one SIGSEGV half a second in (a scratch driver):
- before (the seed's compiler, `build/stage0`): x86-64 `ready`, `still running`, status 0 after 3.0 s; aarch64 under qemu the same; wasm32 (Node) status -11 after 0.5 s.
- after: x86-64 `ready`, status -11 after 0.5 s; aarch64 `ready`, status -11 after 0.5 s (qemu adds `qemu: uncaught target signal 11 (Segmentation fault) - core dumped`); wasm32 -11.

Tests (new), interpreted (`myla run`, whose binary has the same handler) and built:
- `tests.burn.test_term.Signals.test_a_sent_sigsegv_ends_the_program` (the sleeping program, SIGSEGV, killed by it within 10 s): before, both runs failed (`-9`: still running when the test killed it); after, OK natively, on aarch64 (qemu's line taken off stderr) and on wasm32.
- `tests.burn.test_term.RawModeEnds.test_a_sent_sigsegv_while_raw_puts_the_mode_back` (a SIGSEGV while the terminal is raw: status -11 and the terminal cooked): OK natively and on aarch64.
- The bootstrap reaches its fixed point.
- Suites: `scripts/test.sh` (1,656 tests, 342 skipped): only `test_embedded_std` (expected until the seed commit) and `test_children_run_in_parallel` under load (OK alone); `scripts/test-target.py aarch64-linux` and `wasm32-wasi` for `test_term`, `test_net`, `test_stdio`, `test_process`: 4 of 4 each.
