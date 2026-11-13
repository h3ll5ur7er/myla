# std.quaternion

Rotations of 3D space as `float64` quaternions (D201, [[MYLA-587]]); `std.quaternion32` is the same module in `float32`. `Quat` has the fields `x`, `y`, `z` (the vector part) and `w`, and is made by `from_axis_angle(axis, angle)`, `from_rotation_x/y/z(angle)`, `from_euler_xyz(x, y, z)` (x first, then y, then z), `quat(x, y, z, w)` and `Quat.identity()` ([[Language/Standard-library/Algebra]]). `a * b` rotates by `b` first, as matrices do ([[Language/Standard-library/Matrix]]), and `q * v` rotates the `Vec3` `v`.

```myla
import std.float as float
from std.vector import vec3
from std.quaternion import Quat, from_axis_angle

fun main() {
    let q = from_axis_angle(vec3(0.0, 0.0, 1.0), float.PI / 2.0)
    let v = q * vec3(1.0, 0.0, 0.0)
    print(f"{v.x.round()} {v.y.round()} {v.z}")
    let half = Quat.identity().slerp(q, 0.5)
    let w = half * vec3(1.0, 0.0, 0.0)
    print((w.x - (float.PI / 4.0).cos()).abs() < 1e-12)
    let (axis, angle) = q.to_axis_angle()
    print(f"{axis.z} {(angle - float.PI / 2.0).abs() < 1e-12}")
}
// output:
// 0 1 0
// true
// 1 true
```

Methods: `dot`, `length`, `length_squared`, `normalized`, `conjugate`, `inverse`, `slerp(end, t)` (the shorter arc, at a constant angular speed), `to_mat3`, `to_mat4`, `to_axis_angle`, `to_f32`; operators `*` (by a quaternion, a `Vec3`, a scalar), `s * q`, `+`, `-`, `-q`. The rotation methods expect a unit quaternion, which every constructor but `quat` gives.
