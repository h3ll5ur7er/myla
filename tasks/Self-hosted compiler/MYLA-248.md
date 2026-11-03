---
id: MYLA-248
title: "std.num: square root and the basic float functions"
type: feature
status: backlog
priority: medium
labels: [stdlib, floats, runtime]
---
Found while writing the n-body benchmark ([[MYLA-242]]): Myla has no square root. The benchmark takes it by 16 Newton steps in every version, which is about 16 divisions where `sqrtsd` is one instruction. Any program with geometry, physics or statistics needs it, and a few others with it.

- [ ] `sqrt`, as a primitive: `sqrtsd` natively, the same correctly rounded result in the interpreter
- [ ] `abs`, `floor`, `ceil`, `round`, `trunc`, `min`, `max` for `float64` (and `float32` where it matters), with what NaN and the infinities give
- [ ] [[Language/Standard-library]]; the n-body benchmark switched to `sqrt` in all its versions
