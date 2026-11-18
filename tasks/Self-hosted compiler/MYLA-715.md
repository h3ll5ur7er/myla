---
id: MYLA-715
title: "The interpreter gives a constant made of an imported constant as unit or 0"
type: bug
status: review
priority: high
labels: [interpreter, bug]
---
Found by [[MYLA-701]]. A `const` whose initializer names a constant of another module evaluates wrongly in the interpreter (`myla run`, `myla test`): unit (`ERR: VUnit` when printed) or 0 under a unary minus. Natively it is right. A constant made of one of its own module's constants is right in both.

```myla fragment
from std.ioerror import BAD_HANDLE
const A: int32 = 5
const B: int32 = A            // 5 in both
const C: int32 = BAD_HANDLE   // natively 34; interpreted unit
const D: int32 = -BAD_HANDLE  // natively -34; interpreted 0
```

[[MYLA-701]] worked around it in `std.process` and `std.http` (they name std.ioerror's cause codes directly, not through a constant of their own); `std.process`'s `closed_streams` and `stale_copies` failed interpreted before that.

- [x] The interpreter evaluates a constant's initializer in the module that declares it, its imports visible (`selfhost/interp.my`)
- [x] A parity program with the four constants above in `tests/burn/test_compiler_parity.py`

Raised to `high` by [[Project/Review-2026-11-17]] (H13): it is a silent wrong result in the runner the others are compared with. `const C: int32 = BAD_HANDLE` with `from std.ioerror import BAD_HANDLE` gives `C + 1` as 1 and `-BAD_HANDLE` as 0 interpreted, 35 and -34 natively (`repro-r6/docs/known_715_const.my`). It is in the lane of [[MYLA-792]].

## What was built ([[MYLA-792]], H13)

The interpreter evaluated the constants in the order of its declarations, the entry module's before the library's, so a constant naming another module's constant (or one declared after it, in its own module too) read it before it had a value: unit. A constant is now evaluated when it is first named (`const_value`, `const_state` in [[selfhost/interp.my]]), in a frame of its own; the loader's qualified names make what it names the declaring module's. A constant nobody names is never evaluated, which took an empty program's `myla run` from 35.7 M to 29.3 M instructions (2026-11-17, `fe30af6`). A cycle is the checker's error (`const 'A' is defined in terms of itself`), and so is a constant that would fail (`const division by zero`), so evaluating later changes no output.

## Evidence

- Before (BASE `fe30af6`): `known_715_const.my` printed `1` and `0` interpreted, `35` and `-34` natively; a constant declared after the one that names it, `const B: int32 = A + 1` before `const A: int32 = 5`, printed `1` interpreted, `6` natively.
- After: the parity program `consts_of_another_module` ([[tests/burn/test_compiler_parity.py]], the four constants above, one declared later and a string) prints `5 5 35 -34 40 late!` on both runners, pinned; the interpreter's `const_value` and `consts_evaluated` cases. The suites are [[MYLA-792]]'s.
