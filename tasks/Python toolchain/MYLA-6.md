---
id: MYLA-6
title: Float-to-integer casts crash the interpreter or disagree with native code
type: bug
status: backlog
priority: medium
labels: [interpreter, native-backend, floats, parity]
---
## Steps to reproduce

```myla
fun main() {
    let z: float64 = 0.0
    print((z / z) as int32)          // NaN
    let big: float64 = 1e19
    print(big as uint64)             // above int64 range
}
```

## Actual

- `nan as int32`: the interpreter crashes with `ValueError: cannot convert float NaN to integer` ([[src/myla/interpreter.py#L933-L945]]); native prints `0`. `inf` raises `OverflowError` the same way.
- `1e19 as uint64`: the interpreter prints `10000000000000000000`, native `9223372036854775808` (`cvttsd2si` returns the "integer indefinite" value).

## Done when

- [ ] Decide the semantics (proposal: saturate like Rust, NaN → 0) and record it as a decision on [[Project/Decisions]]
- [ ] Implement it identically in the interpreter, const folding (`types._cast_const_value`) and both native backends, including `uint64` above 2^63
- [ ] Parity tests for NaN, ±inf and out-of-range values
