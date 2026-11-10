---
id: MYLA-425
title: "P11 Numbers and containers: D184 sweep, iterators, error types"
type: bug
status: todo
priority: medium
labels: [std, collections, num, overflow, round-5]
---
Work package P11 of [[Project/Review-2026-11-09]] (wave A2), with round 4's additions from [[Project/Review-2026-11-10]]. Files: `lib/std/num.my`, `time.my`, `deque.my`, `set.my`, `heap.my`, `btree.my`, `grid.my`, `bitset.my`, `graph.my`, `encoding.my`, `url.my`'s error type only, `list.my` for one test.

- [ ] M18 and D184: `to_hex`/`to_binary` widths ([[MYLA-331]]), `Duration.abs` of the minimum and "arithmetic wraps" ([[MYLA-334]]), `deque.with_capacity` (2^30 + 1 hangs natively, [[MYLA-330]]), `grid.new`; then a sweep of each module for arithmetic on caller-supplied numbers
- [ ] `iter()` on Set, Deque, Heap and the B-tree; `==` on Set ([[MYLA-330]])
- [ ] D168: `message()` and `Format` on `EncodingError`, `UrlError` and `ParseIntError` ([[MYLA-329]], [[MYLA-405]])
- [ ] [[MYLA-342]]'s follow-ups: `row`/`column` out of range behave alike; negative weights refused where a negative cycle would never return
- [ ] [[MYLA-323]]'s follow-up: a test for `sort_unstable`'s heapsort fallback in `list.my`
