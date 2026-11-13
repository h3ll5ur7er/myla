# std.vector

Vectors of `float64` (D199, [[MYLA-587]]); `std.vector32` is the same module in `float32` (`vector32.Vec3`), both generated from one template by `scripts/gen_std_linalg.py`. `Vec2`, `Vec3` and `Vec4` have the fields `x`, `y`, `z`, `w` and are made by `vec3(x, y, z)`, `splat3(s)`, `Vec3.zero()` and `Vec3.one()` ([[Language/Standard-library/Algebra]]); `Vector` has any length, made by `vector([…])`, `zeros(n)` or `filled(n, v)`, and its operators check that the lengths agree (`vector lengths differ: 2 and 3`).

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
| Operators (D198) | `+ - * /` between two vectors by component, `v * s`, `s * v`, `v / s`, `-v`, `v[i]`, `v[i] = s`, and the compound forms |
| Measures | `dot`, `length`, `length_squared`, `distance`, `distance_squared`, `angle_between` (radians), `min_element`, `max_element` |
| New vectors | `normalized` (NaN for a zero vector), `try_normalized` (an `Option`), `lerp(o, t)`, `min`, `max`, `abs`, `reflect(normal)`, `project_onto(o)` |
| By size | `Vec2`: `perp` (a quarter turn left), `perp_dot`, `extend(z)`; `Vec3`: `cross`, `extend(w)`, `truncate`; `Vec4`: `truncate` |
| Other | `to_list()`, `to_f32()` (`to_f64()` in std.vector32); `Vector`: `len`, `sum`, `map(f)`, `dot`, `length`, `normalized`, `distance` |

Vectors are `Eq` and `Hash` (map keys, D196) and print as `(1, 2, 3)`, a `Vector` as `[1, 2, 3]`.
