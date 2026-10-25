---
id: MYLA-25
title: remove() on a map changes copies of the map too
type: bug
status: backlog
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

- [ ] `remove` runs `cow_unique` on the holder first and drops the removed value
- [ ] Differential test
