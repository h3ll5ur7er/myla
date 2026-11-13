---
id: MYLA-588
title: "x86-64 passes `exit`'s status to exit_program zero-extended"
type: bug
status: review
priority: low
labels: [native, backend, x86-64, round-6]
---
Found by [[MYLA-547]] (the harness lane of round 6). `Inst.Exit` on x86-64 ([[selfhost/ir_x86.my]]) loads the status and passes it with `movl %eax, %edi`, which zero-extends, to std.rt's `exit_program(code: int)`, whose body reads the `int` as the 64-bit register holds it: there `exit(-1)`'s `code as int64` is 4294967295, not -1. Nothing a program sees changes today, as `os.exit` ends the process with the low byte either way, which is why it went unnoticed; the first record D191's test child wrote for `exit(-1)` was `X:4294967295;` before the lane masked the status (`(code as int64) & 255`).

```myla
from std.process import exit

fun main() {
    exit(-1)
}
```

To see it, print `code as int64` in `exit_program` (or look at `%rdi` in gdb at `std$rt$exit_program`): 4294967295 natively on x86-64: an `int` is kept sign-extended in a 64-bit register (`as int64` adds no instruction), and this call alone breaks that.

- [x] `Inst.Exit` passes the status as every other `int` argument (`movslq`), on x86-64; aarch64 and wasm32 checked the same way
- [x] A test that sees `exit_program`'s argument (a runtime test of the IR, or the record without the mask)

## What changed

`Inst.Exit` on x86-64 ([[selfhost/ir_x86.my]]) passes the status with `movslq %eax, %rdi`, so `exit_program` gets the `int` sign-extended, as every argument of its type, through `__exit_program` and through `__task_exit` (which pushes `%rdi` and pops it for `__exit_program`; its comment now says so, [[selfhost/runtime_x86.my]]). The other targets already did: aarch64's `a64_ld` loads the temporary's whole 64 bits, which hold the `int` sign-extended (the disassembly of `std$process$exit` for `exit(-1)`: `ldr x0, [sp]` of `mov x10, #-1`, then `__task_exit`'s `stp x0`/`ldp x0` keep it), and wasm32's `wasm_get` pushes the i64 local, sign-extended likewise. D191's record keeps its mask (`(code as int64) & 255`): its number is the status the process ends with.

## Evidence

- `tests.burn.test_native_runtime.NativeRuntime.test_exit_passes_its_status_sign_extended` (new; gdb at `__exit_program`, `printf "code %ld"` of `%rdi`, with and without tasks; the status 255): before, `code 4294967295` for both programs (2 failures); after, `code -1`, OK. Skipped without gdb; x86-64 only (gdb here has no aarch64, and that suite builds with `as`/`ld`).
- The bootstrap reaches its fixed point (`stage2.s` and `stage3.s` byte-identical).
- Suites: `scripts/test.sh` (1,656 tests, 342 skipped): only `test_embedded_std` (expected until the seed commit) and `test_children_run_in_parallel` under load (OK alone); `scripts/test-target.py aarch64-linux` and `wasm32-wasi` for `test_term`, `test_net`, `test_stdio`, `test_process`: 4 of 4 each.
