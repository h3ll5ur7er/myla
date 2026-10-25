---
id: MYLA-5
title: Native int64 division of the minimum by -1 dies with SIGFPE
type: bug
status: backlog
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

- [ ] Signed 64-bit `/` and `%` special-case a divisor of `-1` (`neg` for `/`, `0` for `%`) before `idivq` ([[src/myla/compiler/codegen_x86.py#L3331-L3342]])
- [ ] Parity test, also for consts (the folder already wraps)
- [ ] The same fix in [[selfhost/codegen.my]]
