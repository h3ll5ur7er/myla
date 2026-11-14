---
id: MYLA-715
title: "The interpreter gives a constant made of an imported constant as unit or 0"
type: bug
status: todo
priority: medium
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

- [ ] The interpreter evaluates a constant's initializer in the module that declares it, its imports visible (`selfhost/interp.my`)
- [ ] A parity program with the four constants above in `tests/burn/test_compiler_parity.py`
