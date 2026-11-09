---
id: MYLA-396
title: "Don't parse an imported module's #test cases"
type: improvement
status: todo
priority: medium
labels: [loader, performance, check-time]
---
Found by [[MYLA-376]]. Since [[MYLA-360]] only the tested file's cases are the program's, but the loader still parses every imported module's cases and drops them afterwards (`without_tests` in [[selfhost/loader.my]]); only the implicit modules are parsed with their cases skipped. A `std` module that imports `std.int` explicitly makes every program that imports it parse `std.int`'s 2,042 cases: a hello world importing `std.bitset` with `std.int` took 58 ms to check instead of 46. So `std.bitset` and `std.bigint` keep their own bit counts.

- [ ] Parse every module other than the entry with its cases skipped (`skip_tests`, as the implicit modules are), measured on a hello world importing `std.text`, `std.http`, `std.compress` and on the compiler's own build
- [ ] `std.bitset` and `std.bigint` on `std.int`'s `count_ones`/`leading_zeros`/`trailing_zeros` then, if the native backend's call per word costs nothing measurable (it doesn't inline across modules: [[MYLA-368]])
