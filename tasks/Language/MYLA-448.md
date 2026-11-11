---
id: MYLA-448
title: "A compound assignment's hoisted map key loses the map's key type"
type: bug
status: todo
priority: low
labels: [language, types, parser, checker]
---
Found by the checker lane of round 5 ([[MYLA-417]]). `m[k] += v` computes an index that isn't a name or a literal once, in a hidden `let %index… = k` before the assignment (the parser's `hoisted`, [[MYLA-223]]). That `let` has no type, so a key that needs the map's key type to be inferred fails, though `m[k] = m[k] + v` checks:

```myla error
fun main() {
    var r: [Result<str, int>: int] = [:]
    r[Ok("a")] = 1
    r[Ok("a")] += 10      // cannot infer type parameter(s) E
    var m: [Option<int>: int] = [:]
    m[None] = 0
    m[None] += 1          // cannot infer type argument(s) for 'None'
}
```

- [ ] The hoisted key takes the map's key type (the checker could check `%index` lets against the place they index, or the parser could hoist only what can't be typed alone)
- [ ] A parity program with both lines, interpreted and natively
