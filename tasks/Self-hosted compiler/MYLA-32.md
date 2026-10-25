---
id: MYLA-32
title: Self-hosted interpreter diverges from the Python interpreter
type: bug
status: backlog
priority: medium
labels: [selfhost, interpreter, parity]
---
[[selfhost/interp.my]] differs from `src/myla/interpreter.py` in several ways:

- [ ] Float literals evaluate to `0.0` (see [[MYLA-29]])
- [ ] `panic` and `assert` exit 1 without printing the message
- [ ] Integer division by zero returns 0 instead of a runtime error
- [ ] A missing map key yields `VUnit` instead of a runtime error
- [ ] `>>` on `uint64` is an arithmetic shift
- [ ] The receiver is evaluated after the arguments, and a `var self` receiver is evaluated twice
- [ ] `for i in a..b` materializes the whole range, truncated to `int32`
- [ ] Lists, maps and scopes are copied on every update, so assignment is O(n)
- [ ] `Value.to_string` formats a `float64`, which the self-hosted codegen can't render: every float path of the stage3-built `myla run` crashes

## Done when

- [ ] Each item fixed or recorded as a known difference on [[Project/Known-issues]]
- [ ] `test_selfhost_interp.py` covers the fixed items
