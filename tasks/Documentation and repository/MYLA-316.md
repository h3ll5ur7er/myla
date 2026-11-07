---
id: MYLA-316
title: "Docs: #derive(Eq) accepts char and float fields"
type: chore
status: todo
priority: low
labels: [docs]
---
Found by Advent of Code ([[Project/AoC-2015-2021]], F7). [[Language/Methods-and-traits]] says of `#derive(Eq)`: "`char` and float fields are rejected for now: [[MYLA-13]]". The compiler accepts both, and on master `d5d80bc` a derived struct with a `char` and a `float` field compares correctly in both runners. The sentence is left over from the Python toolchain.

A float field compares with the floats' `==`, in both runners: a struct holding NaN is unequal to itself, and one holding `0.0` equals one holding `-0.0`. The docs should say so.

- [ ] The sentence corrected, with the float rule; a doc block showing a `char` and a `float` field
