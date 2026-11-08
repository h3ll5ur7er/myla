---
id: MYLA-382
title: "The checker's fill_in rebuilds every function body for one for-over-an-iterator or default"
type: improvement
status: todo
priority: medium
labels: [checker, performance]
---
Found by the `std.iter` lane ([[MYLA-381]]). One `for x in it` over an iterator anywhere in a program makes `fill_in` ([[selfhost/checker.my]], [[MYLA-380]]) rebuild every function body, the standard library's included, and that costs about 8 ms more check time for a hello world (47 → 55 ms). A call that leaves a default parameter out probably does the same, since `fill_in` runs when `call_defaults` is not empty.

A struct `Upto` with `impl Iterator<int>`, then `fun main() { var n = 0; for x in (Upto { i: 0, stop: 3 }) { n += x }; print(n) }`, checks in 55 ms. The same with `var it = Upto { … }; while let Some(x) = it.next() { n += x }` checks in 47 ms. Because of this, `std.iter`, `std.list` and `std.map` loop with `while let` (a comment says why); they can use `for` once this is fixed.

- [ ] `fill_in` rewrites only the bodies holding a recorded `for` or default, and returns the rest as they are
- [ ] Measured: a hello world, a program with one `for` over an iterator, one with a default argument, before and after
- [ ] `std.iter`, `std.list`'s and `std.map`'s test functions back to `for`
