---
id: MYLA-359
title: "Check time of the implicit std modules: about 26 ms for every program"
type: improvement
status: backlog
priority: medium
labels: [checker, performance, stdlib]
---
Found while integrating [[MYLA-320]]. With the six implicit modules (D164), `myla check` of a hello-world takes 26 ms (min of 15) instead of 0.4 ms. An AoC-sized program takes 29 ms instead of 3.3 ms, while `selfhost/main` doesn't change measurably. Their `#test` cases are already skipped unparsed outside `myla test` of the module itself. What remains is checking the method bodies, two thirds of it `std.int` (one impl per width, 4,375 lines). Measured with only one module loaded, before the cases were skipped: str 3.5 ms, char 2.3, int 23.2, list 6.8, option 2.5, map 1.4. The language server and `myla run` pay this on every check.

Options, cheapest first:

1. A smaller `std.int`: the operations that are the same for every width written once over a bound, if the bounds can carry them, or the generator emitting less.
2. Checking a method's body only when the program calls it, or caching the result for the embedded library, whose text is fixed per build.

- [ ] std.hash's checksums (FNV-1a, CRC-32, Adler-32) moved to a module of their own, imported as any other (D166): std.hash keeps the `Hasher` and the `Hash` impls
- [ ] A profile of hello-world's check with the seven modules
- [ ] The cheapest fix that brings it under 5 ms, measured

## Comments

- 2026-11-09, [[MYLA-376]]: `std.int`'s new `count_ones`, `leading_zeros` and `trailing_zeros` on eight widths add 2–3 ms to every program's check (a hello world 43.8 → 48.3 ms); and a std module importing `std.int` explicitly parses its 2,042 cases ([[MYLA-396]]). `std.hash`'s CRC-32 and Adler-32 take a whole list and rebuild the CRC table on every call, so `std.compress` keeps its own: a version over a range of a list would let it use them (gunzip of 100 MB went 526 → 802 ms through a slice).
