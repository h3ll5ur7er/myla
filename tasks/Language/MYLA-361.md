---
id: MYLA-361
title: "myla test: a uint64 of 2^63 or more prints as negative in a failure's report"
type: bug
status: review
priority: low
labels: [testing, printing, integers]
---
Found by the `std.hash` lane ([[MYLA-327]]). When a case fails, `myla test` reports a `uint64` of 2^63 or more as a negative number, interpreted and with `--native`. The comparison is right; `print` shows the value right. Inside a derived struct or a tuple too (`got H { s: -1 }`, `got (-1, 2)`).

```myla fragment
#test[1u64]
fun g() -> uint64 {
    return 0xFFFFFFFFFFFFFFFF
}
// FAIL  g #1: expected 1, got -1
```

The native harness's `__myla_repr` for a `uint64` does `format("{}", v as int64)` (found by [[MYLA-331]]); the interpreter's runner likewise prints it as signed.

- [x] The report's value text by the value's type, unsigned as `print` does, in the interpreter's runner and the native harness (`interp.typed_repr`, by the function's checked result type, inside structs, tuples, lists, maps and enums; a test function's `Err(e)` too. The harness's repr of a `uint64` no longer casts to `int64`)
- [x] A test of a failing case with a large `uint64`, alone and inside a struct and a tuple (and a list, an `Option`, and a `[panic]` case that returned one: `test_test_native`'s `_RECEIVERS`; `typed_repr`'s and `returned_text`'s own cases)

## Evidence

- Before: `#test()[1u64] fun big() -> uint64 { return 0xFFFFFFFFFFFFFFFF }` reported `FAIL  big #1: expected 1, got -1` interpreted and natively; `H { s: -1 }`, `(-1, 2)`, `[-9223372036854775808]`, `Option.Some(-9223372036854775808)`.
- After: `got 18446744073709551615`, `H { s: 18446744073709551615 }`, `(18446744073709551615, 2)`, `[9223372036854775808]`, `Option.Some(9223372036854775808)`, interpreted, natively and on wasm32 (`test_test_native.TestNative.test_receivers_and_large_unsigned_values`, `TestWasm32`); `build/myla test selfhost/interp.my --only typed_repr` 6/6.
- Suites: see [[MYLA-370]]'s evidence.

## Review 2026-11-09

Not ready ([[Project/Review-2026-11-09]]): natively a test function returning `Result<(), uint64>` (any scalar) doesn't build its harness (M8). The fix is in [[MYLA-418]].

- [x] The review's blocker, fixed with [[MYLA-418]]

  Natively `Result<(), uint64>` gave `type 'uint64' has no method 'format'` in the harness; now `FAIL  big: 18446744073709551615` as interpreted, and a float, `char` or `bool` `Err` as `f"{e}"` writes it (`test_test_native.TestNative.test_failing_reports_agree`, also under qemu-aarch64 and on wasm32).
