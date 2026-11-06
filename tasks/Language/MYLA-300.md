---
id: MYLA-300
title: "Float printing: the shortest round-trip form by default"
type: improvement
status: backlog
priority: medium
labels: [floats, printing, decision]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]). `print(0.1)` gives `0.10000000000000001`, `print(1e300)` a 301-digit number, `ldexp(1.0, -1074)` 330 characters; `format_float` has the shortest form but `print` and `{}` don't use it. With format specs in place (D139), the shortest round-trip form (Python, Rust, JavaScript) as the default is the obvious next decision; it changes the recorded answers, so it is a decision plus a refresh of the expectations.

- [ ] The decision; both runners and every target; the recordings or expectations updated
