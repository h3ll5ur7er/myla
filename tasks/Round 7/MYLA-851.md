---
id: MYLA-851
title: "std.json writes a NaN float as `null`, which `decode` of a float refuses"
type: bug
status: review
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

- [x] A decision: (a) `float64.from_json` and `float32.from_json` read `null` as NaN, as the linear algebra types now do (a round trip; but a document's `null` where a number belongs reads silently); (b) `encode` of a NaN or an infinity is an error (`encode` would return a `Result`, an API change); (c) leave it, and document that a NaN doesn't round-trip
- [x] The test first, then the change; `std.toml` checked too (TOML has `nan` and `inf`)

Files: `lib/std/json.my` (the Router/JSON lane's), and the linear algebra modules' `json_numbers` if the decision differs from (a).

## Proposals

Accepted by the owner on 2026-11-19 as D302.

Built: **(a)**, `float64.from_json` (and so `float32.from_json`, which goes through it) reads `null` as NaN. The alternatives:

- **(a) `null` reads as NaN** (built). A NaN float round-trips through `encode` and `decode`, as a vector's, matrix's or quaternion's component already does (D291), so every float of a document reads alike; an infinity, also written `null`, comes back as NaN. What it costs: a `null` where a document should have had a number reads silently as NaN, which shows at its first use (a NaN compares unequal, prints `nan`, and is a map key's runtime error). An `Option<float>` field keeps `null` as `None`, so `Some(NaN)` comes back `None`.
- **(b) `encode` of a NaN or an infinity is an error**: `encode` would return a `Result` (as `toml.encode` does), an API change for every caller, though `ToJson`'s own `to_json` couldn't fail without changing the trait (D172), so a `Json` value built by hand would still hold one.
- **(c) leave it** and document that a NaN doesn't round-trip: the vector types (D291) and plain floats would keep disagreeing.
- **(d) write `NaN`, `Infinity` and `-Infinity`**, as Python's `json` does (and `parse` already reads): exact round trips, the infinities too, but a text that isn't JSON, which [[MYLA-424]] chose `null` over (JavaScript, Go and serde refuse it).
- **(e) `null` as NaN only under an option of `decode`**: no options exist yet; a new API for one case.

std.toml needs nothing: TOML has `nan` and `inf`, which `toml.encode` writes and `toml.decode` reads, so a struct of `nan`, a float32 NaN and `-inf` round-trips exactly (checked, interpreted and natively). The linear algebra modules' `json_numbers` (`scripts/gen_std_linalg.py`) read `null` as NaN themselves; with (a) that branch is redundant but harmless, and left as it is.

## Evidence

Round 7's follow-ups, Numerics lane, over `3add216`.

- **The test first**: `std.json`'s `non_finite_floats_round_trip` (`encode([nan, 1.5, inf])` is `[null,1.5,null]` and decodes to NaN, 1.5, NaN; a float32 NaN; `[null, 2.5]` as `[Option<float64>]` is `None` and `Some(2.5)`; a string is still `WrongType`) failed before (`$[0]: expected a number, found null`) and passes after; `float64.from_json`'s new cases. `std.json` 115/115 interpreted, `--native`, on aarch64 (qemu), wasm32 (Node) and x86_64-windows (Wine).
- The task's program printed `{"x":null}` and `$.x: expected a number, found null` before, `{"x":null}` and `true` now; with a float32 and an infinity beside it, JSON gives `nan nan nan` and TOML `nan nan -inf`, the same interpreted and natively.
