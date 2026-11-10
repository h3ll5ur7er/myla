---
id: MYLA-382
title: "The checker's fill_in rebuilds every function body for one for-over-an-iterator or default"
type: improvement
status: done
priority: medium
labels: [checker, performance]
---
Found by the `std.iter` lane ([[MYLA-381]]). One `for x in it` over an iterator anywhere in a program makes `fill_in` ([[selfhost/checker.my]], [[MYLA-380]]) rebuild every function body, the standard library's included, and that costs about 8 ms more check time for a hello world (47 → 55 ms). A call that leaves a default parameter out probably does the same, since `fill_in` runs when `call_defaults` is not empty.

A struct `Upto` with `impl Iterator<int>`, then `fun main() { var n = 0; for x in (Upto { i: 0, stop: 3 }) { n += x }; print(n) }`, checks in 55 ms. The same with `var it = Upto { … }; while let Some(x) = it.next() { n += x }` checks in 47 ms. Because of this, `std.iter`, `std.list` and `std.map` loop with `while let` (a comment says why); they can use `for` once this is fixed.

- [x] `fill_in` rewrites only the bodies holding a recorded `for` or default, and returns the rest as they are
- [x] Measured: a hello world, a program with one `for` over an iterator, one with a default argument, before and after
- [x] `std.iter`, `std.list`'s and `std.map`'s test functions back to `for`

## Evidence

The checker records the declaration each default or `for` over an iterator was met in (`fill_decls`: a function, a const, or a method's impl), and `fill_in` rebuilds only those declarations' bodies (and their copies in `functions` and `method_decls`); a program with neither returns at once as before. A `#test` on `filled_in` in [[selfhost/checker.my]] pins which declarations are rebuilt (a caller of a default, an impl whose method loops over an iterator; not the callee, a const, a `for` over a list or a program without either).

`build/myla check`, before (master `0eeea06`) and after, the median of 31 runs, and the instructions of one run (valgrind's lackey), x86-64:

| Program | Before | After | Instructions before | After |
| --- | --- | --- | --- | --- |
| hello world | 46.6–48.8 ms | 43.5–49.6 ms (noise) | 197.31 M | 197.40 M |
| one `for` over an iterator (the task's `Upto`) | 55.8–58.0 ms | 47.6–49.1 ms | 212.26 M | 197.93 M |
| one call leaving a default out | 51.1–57.3 ms | 45.9–46.0 ms | 211.86 M | 197.56 M |

The "after" includes `std.list`'s `iterates` and `std.map`'s `map_iter`, now looping with `for` (`std.map`'s with `for p in m.iter() { let (k, v) = p … }`, as `for (k, v) in` waits for [[MYLA-390]]), and `std.iter`'s `pipes`: they cost a hello world 0.09 M instructions (0.05 %), the rebuild of those two test functions. `std.iter`'s adapters keep `while let Some(v) = self.inner.next()`, since a `for` would loop over a copy of `self.inner`; the header comment and [[Language/Standard-library/Iter]] say so now.

Suites at the batch's tip: the bootstrap's fixed point; `scripts/test.sh fast` 714 OK (with the embedded library regenerated); `tests.burn.test_compiler_parity`, `test_selfhost_cases`, `test_error_corpus`, `test_selfhost_checker`, `test_lsp`: 673 OK.

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]].
