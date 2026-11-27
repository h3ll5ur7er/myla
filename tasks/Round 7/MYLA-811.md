---
id: MYLA-811
title: "Native code: `g[^at(1)].push(9)` writes `g[0]`"
type: bug
status: review
priority: high
labels: [lowering, native, round-7]
---
Found by [[MYLA-791]] while testing H5's sync twins: in plain (not async) code, natively, a method or a nested assignment on a place indexed from the end by a call wrote the wrong element. The interpreter was right.

```myla
fun at(i: int) -> int { return i }

fun main() {
    var g = [[1], [2]]
    g[^at(1)].push(9)
    print(f"{g[0].len()} {g[1].len()}")     // 1 2; natively 2 1
}
```

`g[^one]` and `g[^1]` were right. A place whose index may change its variable has its indices held first ([[selfhost/lower.my]]'s `held_place`, for H4 of [[MYLA-543]]); a `^n` index was held as a value of its own, which `^` isn't (D142), so the element taken was another. `held_index` holds what the `^` counts and keeps the `^`; `fixed_receiver` (an actor's place) likewise.

- [x] Fixed natively, every target
- [x] A parity program

## Evidence

- `tests/burn/test_compiler_parity.py`, `places_counted_from_the_end_by_a_call` (new): a push, a push of a called value, an `insert`, an element's assignment and compound assignment, a `var self` method's own counter as the index, two levels from the end. Before, natively: `4,1,1,` and then `list index 1 out of bounds (len 1)`; after: the interpreter's `2,2,2,`, `5 10`, `1,2, 2 1`, `2 1`, natively and on aarch64.
