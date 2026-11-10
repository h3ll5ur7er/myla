---
id: MYLA-357
title: "myla test --native: a case whose receiver is an empty list doesn't build"
type: bug
status: done
priority: medium
labels: [testing, native, harness]
---
Found by the `std.list` lane ([[MYLA-323]]). A `#test` case on a method of a list impl whose receiver is `[]` passes in the interpreter, but `myla test --native` stops. The generated harness writes `var __recv = []` without the receiver's type, so it fails with "cannot infer the element type of an empty list `[]`", at a position past the file's end.

```myla fragment
impl [str] {
    #test([], "-")[1]
    #test(["a"], "-")[2]
    fun width(self, sep: str) -> int { return self.len() + sep.len() }
}
```

The `std.int` lane ([[MYLA-322]]) found a second problem in the harness: it types an unsuffixed literal receiver as `int32`, so `#test(5)[…]` on a method of `impl int8` doesn't build natively. Its cases suffix every receiver (`5i8`).

A smaller thing seen in the same place: a case on a method of `impl [str]` is reported as `__list.width #1`, the internal name, where `[str].width #1` would read better (D116 names a case by the method's checked name).

- [x] The harness ([[selfhost/harness.my]]) annotates every receiver and argument it binds with the parameter's type, which covers both: `[]` and an unsuffixed literal (the receiver is the one value it binds, `var __recv: [str] = []`, with the type the checker gave the case's argument; the other arguments go straight into the call, where the parameter's type is expected already. A type with a type parameter in it stays unannotated)
- [x] A case of every receiver kind with an empty value (`[]`, `[:]`) in `test_test_functions` or the harness's own tests, interpreted and native (`test_test_native.TestNative.test_receivers_and_large_unsigned_values`: `[]`, `[:]`, `""` and `#test(5, 2)` on `impl int8`; on wasm32 too)
- [x] The report's name of a method on a built-in type: `[str].width #1`, `[str: int32].sum_values #1` (the receiver's type as the checker writes it, `interp.case_func_name`, in both reports and in `--only`)

## Evidence

- Before: `tests.burn.test_test_native.TestNative.test_receivers_and_large_unsigned_values` failed: the interpreter named the cases `__list.width_with #1` and `__map.sum_values #1`, and `--native` stopped with "cannot infer the element type of an empty list `[]`", "cannot infer the key/value types of an empty map `[:]`" and "type 'int32' has no method 'plus_i8'".
- After: it passes, interpreted and natively (and on wasm32, `TestWasm32.test_every_case_runs_after_one_that_ends_the_run`); `build/myla test selfhost/harness.my` 33/33 (`nameable`, `runner_case`), `selfhost/interp.my --only case_func_name` 3/3.
- Suites: see [[MYLA-370]]'s evidence (the three tasks were tested together).

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]].
