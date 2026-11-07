---
id: MYLA-324
title: "std.option and std.map: combinators and map helpers"
type: feature
status: todo
priority: high
labels: [stdlib, functional, maps, wave-1]
---
Wave 1 of [[Project/Standard-library-roadmap]], roadmap #20, #23. Methods on `Option<T>`, `Result<T, E>` and maps.

- **Owns:** `lib/std/option.my`, `lib/std/map.my`, `docs/Language/Standard-library/Option.md`, `docs/Language/Standard-library/Map.md`
- **Needs:** [[MYLA-319]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] `Option`: `map`, `and_then`, `or_else`, `unwrap_or`, `unwrap_or_else`, `ok_or`, `is_some`, `is_none`, `expect`
- [ ] `Result`: `map`, `map_err`, `and_then`, `unwrap_or`, `ok`, `err`, `is_ok`, `is_err`, `expect`
- [ ] Maps: `get_or(k, default)`, `update(k, default, f)`, `values()`, `items()`, `merge`, and a function counting how often each element of a list occurs
- [ ] AoC's `get` uses with a default (14 of 29, [[MYLA-318]]) read as `m.get_or(k, d)`
- [ ] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [ ] Its page below [[Language/Standard-library]], with a doc block that runs
