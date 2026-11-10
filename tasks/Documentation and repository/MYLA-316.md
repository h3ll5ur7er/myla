---
id: MYLA-316
title: "Docs: #derive(Eq) accepts char and float fields"
type: chore
status: done
priority: low
labels: [docs]
---
Found by Advent of Code ([[Project/AoC-2015-2021]], F7). [[Language/Methods-and-traits]] says of `#derive(Eq)`: "`char` and float fields are rejected for now: [[MYLA-13]]". The compiler accepts both, and on master `d5d80bc` a derived struct with a `char` and a `float` field compares correctly in both runners. The sentence is left over from the Python toolchain.

A float field compares with the floats' `==`, in both runners: a struct holding NaN is unequal to itself, and one holding `0.0` equals one holding `-0.0`. The docs should say so.

- [x] The sentence corrected, with the float rule; a doc block showing a `char` and a `float` field

## Evidence

- On master `0eeea06` the rejecting sentence was already gone from [[Language/Methods-and-traits]] (its `#derive(Eq)` paragraph lists a float and `char` among the `Eq` field types); the float rule was missing. Added: a float field compares with the floats' `==` in both runners (NaN unequal to itself, `0.0` equal to `-0.0`), and a doc block with a `char` and a `float` field printing `true`, `false`, `false`.
- The block's program, interpreted, natively on x86-64 and on aarch64 (qemu): `true`, `false`, `false` in each. `tests.burn.test_doc_blocks` passes (3 tests).
- The entry in [[Project/Known-issues]] went.

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]].
