---
id: MYLA-488
title: "`Url` derives `Eq` and `Hash`"
type: improvement
status: done
priority: low
labels: [std, url, round-5]
---
Found by [[MYLA-427]] ([[Project/Review-2026-11-09]] §3.3, "`Url` and `Eq`"). [[Language/Standard-library/Url]] said `Url` doesn't derive `Eq` "as `Option` isn't `Eq`"; since [[MYLA-379]] `Option` is `Eq`, and `Hash` since D182, so nothing stops it. Today two parsed URLs can't be compared or used as a map key:

```myla error
import std.url as url

fun main() {
    match (url.parse("http://example.com/a"), url.parse("http://example.com/a")) {
        (Ok(x), Ok(y)) => print(x == y)
        _ => print("err")
    }
}
```

`operator '==' is not defined for 'url.Url': it needs 'impl Eq for url.Url' (or '#derive(Eq)')`. With `#derive(Eq, Hash)` on `pub struct Url` in [[lib/std/url.my]] the program prints `true` interpreted and natively (tried on `95785ab` with a copy of the library).

- [x] `#derive(Eq, Hash)` on `Url`, with a test function comparing parsed URLs and using one as a map key
- [x] The sentence on [[Language/Standard-library/Url]], saying the equality is field by field: the parser lower-cases nothing, so `HTTP://a/` and `http://a/` differ

## Evidence

Done in round 5's wave A2 integration: [[MYLA-422]] (P8) had made `Url` derive `Eq`; `Hash` joined it here.

- Test first: the test function `urls_compare_and_key_maps` in [[lib/std/url.my]] (two equal parses, another scheme's case, a map keyed by `Url`). With `#derive(Eq)` alone: `type error: map key type must be Eq and Hash, found 'Url': 'Url' isn't Hash`. With `#derive(Eq, Hash)`: `build/myla test lib/std/url.my --stdlib lib` 169/169.
- [[Language/Standard-library/Url]] says the equality is field by field and that parsing lower-cases nothing.

## Review 2026-11-12

Signed off in [[Project/Review-2026-11-12]].
