---
id: MYLA-588
title: "x86-64 passes `exit`'s status to exit_program zero-extended"
type: bug
status: todo
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

- [ ] `Inst.Exit` passes the status as every other `int` argument (`movslq`), on x86-64; aarch64 and wasm32 checked the same way
- [ ] A test that sees `exit_program`'s argument (a runtime test of the IR, or the record without the mask)
