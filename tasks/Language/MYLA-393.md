---
id: MYLA-393
title: "Retire the prelude's free get(m, k) for a map method m.get(k)"
type: improvement
status: backlog
priority: low
labels: [language, stdlib, prelude]
---
Found by the `std.http` lane ([[MYLA-347]]). The prelude declares a free function `get<K: Eq + Hash, V>(m: [K: V], k: K) -> Option<V>` at the top level of every program. An imported module's names are qualified (`http.get` is `std$http$get`), but the file being checked or tested keeps its own unqualified, so its `pub fun get` is "duplicate top-level declaration 'get'". `myla test lib/std/http.my` could never run, and the lane named the function `fetch`.

- [ ] `m.get(k) -> Option<V>` in `std.map` (implicit, D164), the free `get` gone from the prelude (`prelude_src` in [[selfhost/checker.my]]); the about 15 uses in `examples/`, `lib/std/` and the docs moved; the language server's `<prelude>` path for it (MYLA-372) removed
- [ ] `http.get(url)` beside `http.fetch(url)`
