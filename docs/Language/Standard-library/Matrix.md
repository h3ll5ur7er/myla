# std.matrix

Matrices of `float64` (D201, [[MYLA-587]]); `std.matrix32` is the same module in `float32`. `Mat2`, `Mat3` and `Mat4` are **column-major**: their fields are the columns, `x_axis`, `y_axis`, `z_axis`, `w_axis` (vectors of [[Language/Standard-library/Vector]]), and a matrix multiplies a **column vector**, `m * v`, so in `a * b * v` the transform `b` comes first. `m[(row, col)]` is an element, `m[i]` a column (D200). They are made by `mat3(c0, c1, c2)` (columns), `mat3_from_rows(r0, r1, r2)`, `Mat3.identity()` and `Mat3.zero()` ([[Language/Standard-library/Algebra]]), and the transforms below, all right-handed. `Matrix` has any shape, its elements in one column-major list, its operators checking the shapes (`matrix shapes don't fit: 2x3 * 2x3`).

```myla
import std.float as float
from std.vector import Vec3, vec3
from std.matrix import Mat4, translation, rotation_z, scaling

fun main() {
    let m = translation(vec3(1.0, 0.0, 0.0)) * rotation_z(float.PI / 2.0) * scaling(vec3(2.0, 2.0, 2.0))
    let p = m.transform_point3(vec3(1.0, 0.0, 0.0))
    print(f"{p.x.round()} {p.y.round()} {p.z}")
    print(m.determinant().round())
    match m.inverse() {
        Some(inv) => print((inv * m).to_list().len()),
        None => print("singular"),
    }
    var e = Mat4.identity()
    e[(0, 3)] = 5.0
    print(e.transform_point3(Vec3.zero()))
}
// output:
// 1 2 0
// 8
// 16
// (5, 0, 0)
```

| Group | |
| --- | --- |
| Operators | `a * b`, `m * v`, `m * s`, `s * m`, `+`, `-`, `-m`, `m[(r, c)]`, `m[(r, c)] = s`, `m[i]`, `m[i] = col` |
| Methods | `col(i)`, `row(i)`, `transpose`, `determinant`, `inverse` (an `Option`; a `Mat4`'s by elimination with partial pivoting), `trace`, `to_list` (column by column, as a GPU takes them), `to_matrix`, `to_f32` |
| `Mat3` | `to_mat4`; as a 2D affine transform, `transform_point2`, `transform_vector2` |
| `Mat4` | `upper_left` (the 3x3 part), `transform_point3` (with the translation, no divide), `transform_vector3`, `project_point3` (divided by `w`) |
| 2D | `rotation2(angle) -> Mat2`; `translation2d(v)`, `rotation2d(angle)`, `scaling2d(v)` give affine `Mat3`s |
| 3D | `translation(v)`, `scaling(v)`, `rotation_x/y/z(angle)`, `rotation_axis(axis, angle)`, `look_at_rh(eye, center, up)` |
| Projections | `perspective_rh_gl(fov_y, aspect, near, far)` and `orthographic_rh_gl(l, r, b, t, n, f)` (depth to OpenGL's -1..1), `perspective_rh` and `orthographic_rh` (0..1: Vulkan, Metal, Direct3D, WebGPU) |
| `Matrix` | `matrix(rows, cols, data)`, `from_rows([[…]])`, `zero_matrix(r, c)`, `identity(n)`; `*` by a `Matrix`, a `Vector` or a scalar, `+`, `-`, `m[(r, c)]`, `row`, `col`, `transpose`, `determinant`, `inverse` (Gauss-Jordan with partial pivoting) |

Angles are in radians, rotations counterclockwise looking at the origin from the axis' positive side. Matrices are `Eq` and `Hash`, and print by rows: `[(1, 0), (0, 1)]` (a `Matrix`, `[[1, 0], [0, 1]]`).
