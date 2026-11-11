---
id: MYLA-496
title: "A `for` over a map lists all its keys first, so leaving the loop early still costs the map's size"
type: improvement
status: todo
priority: low
labels: [maps, performance, runtime, round-5]
---
Found by [[MYLA-429]]. `for k in m` makes the list of the map's keys before its first step (native code: std.rt's `map_keys`, which walks every slot and, when the ranks have gaps, a block of the ranks; the interpreter: `map_keys_of`, which copies the entries without the holes). So a loop that leaves at its first key, the way to take a map's oldest key, costs the map's size, and a queue drained that way is quadratic in its live keys, even since MYLA-429 made the walk cost the live keys rather than the capacity:

```myla
fun main() {
    var m: [int: int] = [:]
    for i in 0..20000 { m[i] = i }
    var taken = 0
    while m.len() > 0 {
        var first = -1
        for k in m {
            first = k
            break
        }
        m.remove(first)
        taken += 1
    }
    print(taken)
}
```

Natively: 2.8 s for 20,000 keys (x86-64, 2026-11-11), where a dict in insertion order (Python's, or the C of `benchmarks/map_remove`) takes milliseconds.

- [ ] Choose: a `for` that walks the retained cell by rank as it goes (the loop holds a reference, so the cell doesn't change under it; a cursor of the next rank and a way to find the slot of a rank without the block of ranks, e.g. the ranks dense once compacted), or a method that gives the oldest key (`first_key() -> Option<K>`), or both
- [ ] The queue above linear in its keys natively and interpreted, on every target, D105's order unchanged
