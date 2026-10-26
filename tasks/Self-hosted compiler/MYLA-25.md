---
id: MYLA-25
title: remove() on a map changes copies of the map too
type: bug
status: review
priority: medium
labels: [selfhost, codegen, collections]
---
`gen_map_remove` ([[selfhost/codegen.my]], around line 2527) neither makes the map unique (copy-on-write) nor drops the removed value.

```myla
fun main() {
    var a = ["x": 1, "y": 2]
    var b = a
    remove(b, "x")
    print(len(a))
    print(contains(a, "x"))
}
```

Python toolchain: `2 true`. Self-hosted: `1 false`.

## Done when

- [x] `remove` runs `cow_unique` on the holder first and drops the removed value
- [x] Differential test: the parity program `remove_leaves_map_copies_alone` (printed `1 false 1` before), and the stress program `STRESS_MAP_REMOVE_SRC` (600k removals from one map: 54 MB peak before, under the 30 MB bound after; also run against the Python backend)
