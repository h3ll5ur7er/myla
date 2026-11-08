---
id: MYLA-381
title: "std.iter: adapters and consumers over Iterator"
type: feature
status: backlog
priority: medium
labels: [stdlib, iterators]
---
The library part of D171 ([[MYLA-353]]), after [[MYLA-380]]. Functions of `std.iter`, chained with `|>`:

```myla fragment
import std.iter as iter

let total = xs.iter() |> iter.map((x) => x * 3) |> iter.filter((x) => x % 2 == 0) |> iter.sum()
```

- **Owns:** `lib/std/iter.my`, `docs/Language/Standard-library/Iter.md`, and `xs.iter()` in `lib/std/list.my`, `m.iter()` in `lib/std/map.my`, `s.chars_iter()` or the like in `lib/std/str.my` (decide the name)

- [ ] Sources: `xs.iter()`, `m.iter()` (key-value pairs in insertion order), `iter.range(a, b)`, `iter.repeat(v)`, `iter.from_fn(state, step)`
- [ ] Adapters: `map`, `filter`, `take`, `skip`, `take_while`, `skip_while`, `enumerate`, `zip`, `chain`, `flat_map`
- [ ] Consumers: `to_list`, `count`, `sum`, `fold`, `any`, `all`, `find`, `min`, `max`
- [ ] `std.list`'s own methods stay eager (D171)
- [ ] Test functions (generic, D162), interpreted and with `--native`; a page with a doc block that runs
- [ ] Measured natively and interpreted against the eager list methods
- [ ] A thin wrapper type with methods (`iter.of(xs).map(f)`) only if someone asks for it (D171)
