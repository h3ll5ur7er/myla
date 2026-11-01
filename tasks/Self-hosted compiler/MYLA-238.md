---
id: MYLA-238
title: "The self-hosted interpreter loses an argument's change to a `var self` receiver"
type: bug
status: review
priority: high
labels: [selfhost, interpreter, parity]
---
Found by the generated `#test` cases of [[MYLA-184]]: cases computed by the Python interpreter failed in `build/myla test`. In `c.add(c.bump_get())`, where both are `var self` methods, the self-hosted interpreter read `c`'s value before evaluating the arguments and wrote its stale copy back after the call, so the change `bump_get` made to `c` was lost (`3` instead of `4`). The Python interpreter and both native backends keep it. The receiver factory `lower_on` (`lw.start(lw.new_block())`) hit the same thing.

- [x] `eval_method_call` in [[selfhost/interp.my]]: the receiver's place (its indices once) first, then the arguments, then its value
- [x] A regression program in all four runners: `examples/methods.my` (`c.add(c.bump_get())`, `bump_get` with a case)
- [x] [[Language/Expressions-and-operators]] says how a `var self` method takes its receiver

## Evidence

- Before: `examples/methods.my`'s new last line printed `3` from `build/myla run` and `4` from the Python interpreter and both native backends; a reduced program (`l.start(l.add())`) printed `0 0` against `1 0`. After the fix all four print `4` and `1 0`, and the 29 generated `lower.my` cases that failed in the self-hosted runner pass in both.
- The full verification of the change is recorded on [[MYLA-184]].
