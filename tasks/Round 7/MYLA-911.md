---
id: MYLA-911
title: "Print a float's shortest digits without reading candidates back (Schubfach or Ryū)"
type: improvement
status: backlog
priority: low
labels: [runtime, numerics, performance, round-7]
---
Follow-up of [[MYLA-849]], which took that task's lesser option: `float_to_str` (`lib/std/rt.my`) still binary-searches the digit count and reads each candidate back, now by `std.num.decimal_bits` (Eisel–Lemire, [[MYLA-843]]) rather than in big integers. 200 floats of random bits cost 1.94 M instructions natively (callgrind, 2026-11-18 over 3add216), of which 0.44 M are the program's own: about 7,500 a float, three quarters of it reading back.

Schubfach (Java's `Double.toString` since 17) or Ryū (Rust's, Go's) find the shortest digits from the float's two neighbours' bounds with one 128-bit multiplication each, by a table of powers of ten that [[MYLA-843]]'s `POW10_SIG` nearly is (Schubfach's are rounded up where they're not exact); they give the nearest of the shortest digits, as Python's repr, which would close [[MYLA-910]] too, but change `print`'s output for its cases: an owner's decision (D155).

- [ ] A test first: [[MYLA-849]]'s instruction count with a lower bound, and its differential corpus against repr
- [ ] Schubfach (or Ryū) for float64; a float32 reads back as a float64 rounded to float32 (D155), so its digits need their own bounds
- [ ] The digits the same as before everywhere but [[MYLA-910]]'s cases
