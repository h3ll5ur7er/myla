---
id: MYLA-851
title: "std.json writes a NaN float as `null`, which `decode` of a float refuses"
type: bug
status: todo
priority: low
labels: [stdlib, json, round-7]
---
Filed by [[MYLA-796]] beside its Low item "`json.encode` of a NaN vector is `[null,null]`, which doesn't decode" ([[Project/Review-2026-11-17]]). The linear algebra modules now read a `null` component as NaN ([[MYLA-796]], `json_numbers` in `scripts/gen_std_linalg.py`), so a vector, matrix or quaternion round-trips. A plain float doesn't:

```myla fragment
import std.json as json
import std.float as float

#derive(Json)
struct P {
    x: float,
}

fun main() {
    let t = json.encode(P { x: float.nan() })
    print(t)                    // {"x":null}
    match json.decode<P>(t) {
        Ok(p) => print(p.x.is_nan())
        Err(e) => print(f"{e}")    // $.x: expected a number, found null
    }
}
```

JSON has no NaN or infinity. JavaScript's `JSON.stringify` writes them as `null`, Python's `json` writes `NaN` and `Infinity` (not JSON) and reads them back, Rust's serde_json writes `null` and refuses it for an `f64`.

- [ ] A decision: (a) `float64.from_json` and `float32.from_json` read `null` as NaN, as the linear algebra types now do (a round trip; but a document's `null` where a number belongs reads silently); (b) `encode` of a NaN or an infinity is an error (`encode` would return a `Result`, an API change); (c) leave it, and document that a NaN doesn't round-trip
- [ ] The test first, then the change; `std.toml` checked too (TOML has `nan` and `inf`)

Files: `lib/std/json.my` (the Router/JSON lane's), and the linear algebra modules' `json_numbers` if the decision differs from (a).
