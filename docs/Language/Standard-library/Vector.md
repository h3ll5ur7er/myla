# std.vector

Vectors of `float64` (D201, [[MYLA-587]]); `std.vector32` is the same module in `float32` (`vector32.Vec3`), both generated from one template by `scripts/gen_std_linalg.py`. `Vec2`, `Vec3` and `Vec4` have the fields `x`, `y`, `z`, `w` and are made by `vec3(x, y, z)`, `splat3(s)`, `Vec3.zero()` and `Vec3.one()` ([[Language/Standard-library/Algebra]]); `Vector` has any length, made by `vector([…])`, `zeros(n)` or `filled(n, v)`, and its operators check that the lengths agree (`vector lengths differ: 2 and 3`).

```myla
from std.vector import Vec3, vec3

fun main() {
    let a = vec3(1.0, 2.0, 2.0)
    let b = vec3(0.0, 1.0, 0.0)
    print(a.length())
    print(a + b * 2.0)
    print(2.0 * a - a / 2.0)
    print(a.cross(b))
    print(a.dot(b))
    var p = Vec3.zero()
    p[1] = 5.0
    p += a
    print(p)
    print(vec3(3.0, 4.0, 0.0).normalized())
}
// output:
// 3
// (1, 4, 2)
// (1.5, 3, 3)
// (-2, 0, 1)
// 2
// (1, 7, 2)
// (0.6, 0.8, 0)
```

| Group | |
| --- | --- |
| Operators (D200) | `+ - * /` between two vectors by component, `v * s`, `s * v`, `v / s`, `-v`, `v[i]`, `v[i] = s`, and the compound forms |
| Measures | `dot`, `length`, `length_squared`, `distance`, `distance_squared`, `angle_between` (radians), `min_element`, `max_element` |
| New vectors | `normalized` (NaN for a zero vector), `try_normalized` (an `Option`), `lerp(o, t)`, `min`, `max`, `abs`, `reflect(normal)`, `project_onto(o)` |
| By size | `Vec2`: `perp` (a quarter turn left), `perp_dot`, `extend(z)`; `Vec3`: `cross`, `extend(w)`, `truncate`; `Vec4`: `truncate` |
| Other | `to_list()`, `to_f32()` (`to_f64()` in std.vector32); `Vector`: `len`, `sum`, `map(f)`, `dot`, `length`, `normalized`, `distance` |

Vectors are `Eq` and `Hash` (map keys, D198) and print as `(1, 2, 3)`, a `Vector` as `[1, 2, 3]`.

## JSON

Vectors are JSON arrays, as glTF writes them (D206): a `Vec3` is `[1.0, 2.0, 3.0]`, a `Vector` the array of its elements. So a `#derive(Json)` struct with a `Vec3` field reads a document's `"translation": [1, 2, 3]`. An array of another length, or an element that isn't a number, is an error with its path ([[Language/Standard-library/Json]]).

```myla
import std.json as json
from std.vector import Vec3, vec3

fun main() {
    print(json.encode(vec3(1.0, 2.5, -3.0)))
    for text in ["[1, 2, 3]", "[1, 2]", "[1, 2, \"x\"]"] {
        match json.decode<Vec3>(text) {
            Ok(v) => print(v)
            Err(e) => print(f"{e}")
        }
    }
}
// output:
// [1.0,2.5,-3.0]
// (1, 2, 3)
// $: expected an array of 3 numbers for 'Vec3', found an array of 2 items
// $[2]: expected a number, found a string
```

## Speed

`benchmarks/linalg_std.my` times the library against the same work written by hand with `std.bench`, natively on x86-64 (2026-11-13, `3bcafb0`, the fastest run of each; this 4-core machine was shared with other work, and its medians varied by up to a third between runs):

| Work | The library | By hand |
| --- | --- | --- |
| `Vec4.dot` | 3.4 ns | |
| `Vector.dot`, 1000 elements | 1.08 µs | 0.95 µs, a loop over two `[float]` |
| `Vector + Vector`, 1000 elements | 2.03 µs | 2.04 µs, the same loop pushing to a `[float]` |

`Vector`'s operators are loops over its list; before `3bcafb0` they called a closure for each element and `Vector + Vector` took half as long again as the loop by hand (3.12 µs). `Vector.dot` checks the lengths before its loop.
