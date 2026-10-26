---
id: MYLA-6
title: Float-to-integer casts crash the interpreter or disagree with native code
type: bug
status: review
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

- [x] Decide the semantics (proposal: saturate like Rust, NaN → 0) and record it as a decision on [[Project/Decisions]] (D59)
- [x] Implement it identically in the interpreter, const folding (`types._cast_const_value`) and both native backends, including `uint64` above 2^63
- [x] Parity tests for NaN, ±inf and out-of-range values

## How

D59: a float → integer cast truncates toward zero and clamps to the target's range; NaN gives 0.

- Python: `types.float_to_int` is shared by the interpreter's `_cast_value` and the const folder's `_cast_const_value`.
- Native (`CodeGen._float_to_int` in [[src/myla/compiler/codegen_x86.py]], `float_to_int` in [[selfhost/codegen.my]], identical sequences): `ucomisd x, x` + `jp` for NaN; compare with the bounds 2^top and the minimum (both loaded as double bit patterns with `movabsq`) and jump to the clamped value; otherwise `cvttsd2si`. A `uint64` from 2^63 up converts `x - 2^63` and sets bit 63 with `btcq`.
- Self-hosted interpreter: `float_to_int` in [[selfhost/interp.my]] clamps explicitly before its native casts. The self-hosted checker does not fold float values (`CV.CVFloat`), so const float casts are evaluated by the code generator.

## Evidence

- Unit tests `test_float_to_int_casts_saturate` and `test_const_float_to_int_casts_saturate` ([[tests/unit/test_floats.py]]): before, `ValueError: cannot convert float NaN to integer`; after, pass.
- Parity program `float_to_int_casts_saturate` (33 values × six target types, float32 sources, consts) in [[tests/burn/test_compiler_parity.py]] and the self-hosted `PARITY_PROGRAMS`: native, self-hosted native and self-hosted interpreter all match the interpreter, e.g. `1e19 as uint64` = `10000000000000000000`, `3e19 as uint64` = `18446744073709551615`, `-inf as int64` = `-9223372036854775808`, `300.0 as uint8` = `255`, NaN = `0`.
- Bootstrap fixed point holds (5,929,672 bytes); unit, integration and burn suites pass.
