---
id: MYLA-5
title: Native int64 division of the minimum by -1 dies with SIGFPE
type: bug
status: review
priority: medium
labels: [native-backend, parity, arithmetic]
---
## Steps to reproduce

```myla
fun main() {
    let a: int64 = -9223372036854775807 - 1
    var b: int64 = -1
    print(a / b)
}
```

## Expected

`-9223372036854775808`: integer arithmetic wraps (D4), and the interpreter prints this.

## Actual

The native binary is killed by SIGFPE (exit 136): `idivq` raises #DE when the quotient overflows. `%` with the same operands traps too (Python gives `0`).

Narrower types are fine, because their operands are sign-extended to 64 bits before `idivq`.

## Done when

- [x] Signed 64-bit `/` and `%` special-case a divisor of `-1` (`neg` for `/`, `0` for `%`) before `idivq` ([[src/myla/compiler/codegen_x86.py#L3378-L3397]])
- [x] Parity test, also for consts (the folder already wraps)
- [x] The same fix in [[selfhost/codegen.my]]

## How

Both backends compare the divisor with `-1` before a signed division and take `negq %rax` (for `/`) or `0` (for `%`) instead of `idivq`, then wrap to the result type as before. This covers every signed width, not just `int64`. The gate tools (built by the Python backend) and the self-hosted checker's const folder (`li / ri`, compiled natively) trapped on the same division; they are fixed by the codegen change.

## Evidence

- New parity program `int64_min_divided_by_minus_one` (variables, function arguments, `int32`, consts) in [[tests/burn/test_compiler_parity.py]] and the self-hosted `PARITY_PROGRAMS`. Before: the Python native binary died with SIGFPE (exit -8), the self-hosted compile and the self-hosted interpreter crashed with -8. After: all three match the interpreter.
- Bootstrap fixed point holds (5,919,838 bytes); unit, integration and burn suites pass.
