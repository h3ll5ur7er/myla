---
id: MYLA-41
title: Rust numeric and hashing semantics
type: bug
status: backlog
priority: medium
labels: [rust, interpreter, spec]
---
- [ ] Integer equality and arithmetic ignore the kind: `1u8 == 1i64` is `true`, `200u8 + 100i64` is `44` (the left kind wins); the spec says there is no implicit numeric conversion
- [ ] Integer literals overflow silently: `300u8` is `44`, a 23-digit literal becomes `-159383553` (`unwrap_or(0)` in `lit.rs`)
- [ ] Hash and equality disagree: floats hash by bits but compare with `==` (`0.0 == -0.0`, yet a map keyed by `0.0` says `contains(-0.0)` is false; NaN isn't reflexive); maps hash in insertion order but compare order-independently
- [ ] `operator_method` maps `Eq`/`Ne` to `eq`, but equality is always structural, so user `eq` is never called (and the mapping is dead)
