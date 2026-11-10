---
id: MYLA-429
title: "P15 Maps shrink, and iterate in their live size"
type: improvement
status: todo
priority: medium
labels: [maps, runtime, performance, round-5]
---
Work package P15 of [[Project/Review-2026-11-09]] (wave B, after [[MYLA-415]]: the same lowering and runtime). Follow-up of [[MYLA-310]].

- [ ] M26: a map compacts on remove when most of its slots are dead, so iteration costs its live size (20,000 keys taken oldest-first from a once-10^6 map: 82 s)
- [ ] Measured on the map benchmarks before and after
