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

## JSON

A matrix is the JSON array of its elements column by column, as glTF writes a node's `"matrix"` (D206): a `Mat4` is 16 numbers, the translation in the 13th to 15th. A `Matrix` is `{"rows": 2, "cols": 3, "data": […]}`, its data column by column too; data that doesn't fit the shape is an error at `$.data`.

```myla
import std.json as json
from std.vector import Vec3, vec3
from std.matrix import Mat4, translation
from std.quaternion import Quat, quat

#derive(Json)
struct Node {
    name: str,
    translation: Vec3,
    rotation: Quat,
    matrix: Mat4,
}

fun main() {
    let node = Node { name: "box", translation: vec3(1.0, 2.0, 3.0), rotation: quat(0.0, 0.0, 0.0, 1.0), matrix: translation(vec3(7.0, 8.0, 9.0)) }
    let text = json.encode(node)
    print(text)
    match json.decode<Node>(text) {
        Ok(back) => print(back.matrix == node.matrix)
        Err(e) => print(f"{e}")
    }
}
// output:
// {"name":"box","translation":[1.0,2.0,3.0],"rotation":[0.0,0.0,0.0,1.0],"matrix":[1.0,0.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,0.0,1.0,0.0,7.0,8.0,9.0,1.0]}
// true
```

## Speed

`benchmarks/linalg_std.my`, natively on x86-64 (2026-11-13, `3bcafb0`, the fastest run of each, on a shared 4-core machine):

| Work | The library | By hand |
| --- | --- | --- |
| `Mat4 * Vec4` | 19.7 ns | 19.5 ns, the 16 products written on the fields |
| `Mat4 * Mat4` | 76 ns | 142 ns, the triple loop over two `[float]` of 16 |
| `Matrix * Matrix`, 4x4 | 160 ns | 142 ns, the same loop |

`MatN * VecN` sums each component's products; before `1abd660` it added the scaled columns, building a vector for each, and `Mat4 * Vec4` took 26 ns (`Mat4 * Mat4`, four of them, 101 ns).
