"""Burn test: std.vector, std.matrix, std.quaternion and their float32 twins
(D201, MYLA-587).

The fixed sizes (`Vec2`-`Vec4`, `Mat2`-`Mat4`, `Quat`) and `Vector`/`Matrix`
of any size, in float64 and float32: their operators (D200), the transforms
(column-major, column vectors, right-handed), inverses, quaternion rotations
agreeing with the matrices, std.algebra's `Zero`/`One`/`Identity`, vectors as
map keys (D198), the conversions between the precisions; alike in the
interpreter and natively. A shape mismatch is a runtime error. The six
modules are what scripts/gen_std_linalg.py writes."""
import os
import subprocess
import sys
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON, Program, build_and_run_full, run_source_both_now, selfhost_run, write_program

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROGRAM = """import std.vector as vector
import std.matrix as matrix
import std.quaternion as quaternion
import std.vector32 as v32
import std.matrix32 as m32
import std.quaternion32 as q32
import std.algebra as algebra
import std.float as float
from std.vector import Vec2, Vec3, Vec4, vec2, vec3, vec4
from std.matrix import Mat3, Mat4, mat3, translation, scaling, rotation_x, rotation_y, rotation_z
from std.quaternion import Quat, from_axis_angle

fun close3(a: Vec3, b: Vec3) -> bool {
    return (a - b).length() < 1e-9
}

fun close4(a: Mat4, b: Mat4) -> bool {
    var worst = 0.0
    var i = 0
    while i < 4 {
        worst = worst.max((a[i] - b[i]).abs().max_element())
        i += 1
    }
    return worst < 1e-9
}

fun main() {
    // vectors
    let a = vec3(1.0, 2.0, 3.0)
    let b = vec3(4.0, 5.0, 6.0)
    print(a + b)
    print(a * 2.0 - b / 2.0)
    print(2.0 * a)
    print(a.dot(b))
    print(a.cross(b))
    print(vec3(3.0, 4.0, 0.0).length())
    print(vec3(3.0, 4.0, 0.0).normalized())
    print(Vec3.zero().try_normalized() == None)
    print(-a)
    print(a[2])
    var p = a
    p[0] = 10.0
    p += vec3(1.0, 1.0, 1.0)
    print(p)
    print(vec2(1.0, 0.0).perp())
    print(a.extend(1.0))
    print(Vec4.one().truncate())
    print(algebra.sum([a, b, Vec3.one()]))
    print(vec3(1.0, -1.0, 0.0).reflect(vec3(0.0, 1.0, 0.0)))
    print(vec2(1.0, 0.0).angle_between(vec2(0.0, 1.0)) == float.PI / 2.0)
    var seen: [Vec2: int] = [:]
    seen[vec2(1.0, 2.0)] = 1
    seen[vec2(1.0, 2.0)] += 1
    print(seen[vec2(1.0, 2.0)])

    // matrices: column vectors, `a * b` applies `b` first
    let t = translation(vec3(1.0, 2.0, 3.0))
    print(t.transform_point3(Vec3.zero()))
    print(t.transform_vector3(vec3(1.0, 0.0, 0.0)))
    print(close3(rotation_z(float.PI / 2.0).transform_point3(vec3(1.0, 0.0, 0.0)), vec3(0.0, 1.0, 0.0)))
    print(close3(rotation_x(float.PI / 2.0).transform_point3(vec3(0.0, 1.0, 0.0)), vec3(0.0, 0.0, 1.0)))
    print(close3(rotation_y(float.PI / 2.0).transform_point3(vec3(0.0, 0.0, 1.0)), vec3(1.0, 0.0, 0.0)))
    let m = t * rotation_z(0.5) * scaling(vec3(2.0, 3.0, 4.0))
    print(close3(m.transform_point3(vec3(1.0, 1.0, 1.0)), t.transform_point3(rotation_z(0.5).transform_point3(vec3(2.0, 3.0, 4.0)))))
    match m.inverse() {
        Some(inv) => print(close4(m * inv, Mat4.identity())),
        None => print("no inverse"),
    }
    print(scaling(vec3(1.0, 0.0, 1.0)).inverse() == None)
    print((rotation_z(0.3).determinant() - 1.0).abs() < 1e-12)
    print(scaling(vec3(2.0, 3.0, 4.0)).determinant())
    print(Mat3.identity()[(1, 1)] + Mat3.identity()[(0, 1)])
    var e = Mat3.identity()
    e[(0, 2)] = 7.0
    print(e.row(0))
    print(e.transpose()[2])
    print(mat3(vec3(1.0, 0.0, 0.0), vec3(1.0, 1.0, 0.0), vec3(0.0, 0.0, 1.0)))
    print(Mat4.identity().to_list().len())

    // projections and the view
    let gl = matrix.perspective_rh_gl(float.PI / 2.0, 1.0, 1.0, 10.0)
    print((gl.project_point3(vec3(0.0, 0.0, -1.0)).z + 1.0).abs() < 1e-12)
    print((gl.project_point3(vec3(0.0, 0.0, -10.0)).z - 1.0).abs() < 1e-12)
    let vk = matrix.perspective_rh(float.PI / 2.0, 1.0, 1.0, 10.0)
    print(vk.project_point3(vec3(0.0, 0.0, -1.0)).z.abs() < 1e-12)
    print((vk.project_point3(vec3(0.0, 0.0, -10.0)).z - 1.0).abs() < 1e-12)
    let view = matrix.look_at_rh(vec3(0.0, 0.0, 5.0), Vec3.zero(), vec3(0.0, 1.0, 0.0))
    print(view.transform_point3(Vec3.zero()))
    let ortho = matrix.orthographic_rh_gl(-2.0, 2.0, -1.0, 1.0, 0.0, 10.0)
    print(ortho.transform_point3(vec3(2.0, 1.0, -10.0)))

    // quaternions
    let q = from_axis_angle(vec3(0.0, 0.0, 1.0), float.PI / 2.0)
    print(close3(q * vec3(1.0, 0.0, 0.0), vec3(0.0, 1.0, 0.0)))
    print(close3(q.to_mat4().transform_point3(vec3(1.0, 2.0, 3.0)), q * vec3(1.0, 2.0, 3.0)))
    let half = Quat.identity().slerp(q, 0.5)
    print(close3(half * vec3(1.0, 0.0, 0.0), vec3((float.PI / 4.0).cos(), (float.PI / 4.0).sin(), 0.0)))
    let eq = quaternion.from_euler_xyz(0.1, 0.2, 0.3)
    print(close4(eq.to_mat4(), rotation_z(0.3) * rotation_y(0.2) * rotation_x(0.1)))
    print(close3((q * q.inverse()) * a, a))
    let (axis, angle) = q.to_axis_angle()
    print(close3(axis, vec3(0.0, 0.0, 1.0)) && (angle - float.PI / 2.0).abs() < 1e-12)

    // any size
    let mm = matrix.from_rows([[2.0, 1.0], [1.0, 3.0]])
    print(mm)
    print(mm.determinant())
    print(mm * vector.vector([1.0, 1.0]))
    match mm.inverse() {
        Some(inv) => {
            var worst = 0.0
            for x in (inv * mm - matrix.identity(2)).to_list() { worst = worst.max(x.abs()) }
            print(worst < 1e-12)
        },
        None => print("no inverse"),
    }
    print(matrix.from_rows([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]).transpose())
    print(vector.vector([1.0, 2.0, 2.0]).length())

    // float32
    let c = v32.vec3(1.0, 2.0, 2.0)
    print(c.length())
    print(c * 0.5)
    let qz = q32.from_axis_angle(v32.vec3(0.0, 0.0, 1.0), 1.5707964)
    print(((qz * v32.vec3(1.0, 0.0, 0.0)) - v32.vec3(0.0, 1.0, 0.0)).length() < 1e-6)
    let t32 = m32.translation(v32.vec3(1.0, 2.0, 3.0)) * m32.scaling(v32.Vec3.one() * 2.0)
    print(t32.transform_point3(v32.Vec3.one()))
    print(a.to_f32().to_f64() == a)
    print(t32.to_f64().transform_point3(Vec3.one()))
}
"""

WANT = """(5, 7, 9)
(0, 1.5, 3)
(2, 4, 6)
32
(-3, 6, -3)
5
(0.6, 0.8, 0)
true
(-1, -2, -3)
3
(11, 3, 4)
(-0, 1)
(1, 2, 3, 1)
(1, 1, 1)
(6, 8, 10)
(1, 1, 0)
true
2
(1, 2, 3)
(1, 0, 0)
true
true
true
true
true
true
true
24
1
(1, 0, 7)
(0, 0, 1)
[(1, 1, 0), (0, 1, 0), (0, 0, 1)]
16
true
true
true
true
(0, 0, -5)
(1, 1, 1)
true
true
true
true
true
true
[[2, 1], [1, 3]]
5
[3, 4]
true
[[1, 4], [2, 5], [3, 6]]
3
3
(0.5, 1, 1)
true
(3, 4, 5)
true
(3, 4, 5)
"""

SHAPE_ERROR = """import std.matrix as matrix
import std.vector as vector

fun main() {
    let m = matrix.from_rows([[1.0, 2.0], [3.0, 4.0]])
    print(m * vector.vector([1.0, 2.0, 3.0]))
}
"""


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class LinearAlgebra(unittest.TestCase):
    def test_in_the_interpreter_and_natively(self) -> None:
        self.assertEqual(run_source_both_now(PROGRAM), (WANT, "", 0))

    def test_a_shape_mismatch_is_a_runtime_error(self) -> None:
        # the same message and place in std.matrix (the interpreter shows the
        # source line under them too)
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, SHAPE_ERROR)
            interp = selfhost_run(path)
            native = build_and_run_full(Program(path), argv0=path)
        for out, err, code in (interp, native):
            self.assertEqual((out, code), ("", 1))
            self.assertTrue(err.startswith("runtime error: matrix shapes don't fit: 2x2 * a vector of 3\n  --> "), err)
        self.assertEqual(interp[1].split("\n")[:2], native[1].split("\n")[:2])


# JSON as arrays, as glTF writes them (the owner's choice, 2026-11-13): a
# vector its components, a matrix its elements column by column, a quaternion
# [x, y, z, w]; `Vector` an array, `Matrix` {"rows", "cols", "data"}
JSON_PROGRAM = """import std.json as json
from std.vector import Vec3, Vector, vec2, vec3, vector
from std.matrix import Mat2, Mat4, Matrix, mat2, matrix, translation
from std.quaternion import Quat, quat
import std.vector32 as v32

#derive(Json)
struct Node {
    name: str,
    translation: Vec3,
    rotation: Quat,
    matrix: Mat4,
}

fun main() {
    print(json.encode(vec3(1.0, 2.5, -3.0)))
    print(json.encode(mat2(vec2(0.0, 0.0), vec2(3.0, 4.0))))
    print(json.encode(quat(0.0, 0.0, 0.5, 1.0)))
    print(json.encode(vector([1.0, 2.0])))
    print(json.encode(matrix(2, 1, [5.0, 6.0])))
    print(json.encode(v32.vec3(0.1, 0.2, 0.3)))
    let node = Node { name: "box", translation: vec3(1.0, 2.0, 3.0), rotation: quat(0.0, 0.0, 0.0, 1.0), matrix: translation(vec3(7.0, 8.0, 9.0)) }
    let text = json.encode(node)
    print(text)
    match json.decode<Node>(text) {
        Ok(back) => print(back.translation == node.translation && back.rotation == node.rotation && back.matrix == node.matrix)
        Err(e) => print(f"{e}")
    }
    match json.decode<Vec3>("[1, 2, 3]") {
        Ok(v) => print(v)
        Err(e) => print(f"{e}")
    }
    match json.decode<Mat2>("[1, 2, 3, 4]") {
        Ok(m) => print(m.y_axis.x)
        Err(e) => print(f"{e}")
    }
    for bad in ["[1, 2]", "[1, 2, \\"x\\"]", "{\\"x\\": 1}"] {
        match json.decode<Vec3>(bad) {
            Ok(v) => print(v)
            Err(e) => print(f"{e}")
        }
    }
    match json.decode<Matrix>("{\\"rows\\": 2, \\"cols\\": 2, \\"data\\": [1, 2, 3]}") {
        Ok(m) => print(m)
        Err(e) => print(f"{e}")
    }
    match json.decode<Vector>("[1.5, 2]") {
        Ok(v) => print(v)
        Err(e) => print(f"{e}")
    }
}
"""

JSON_WANT = """[1.0,2.5,-3.0]
[0.0,0.0,3.0,4.0]
[0.0,0.0,0.5,1.0]
[1.0,2.0]
{"rows":2,"cols":1,"data":[5.0,6.0]}
[0.1,0.2,0.3]
{"name":"box","translation":[1.0,2.0,3.0],"rotation":[0.0,0.0,0.0,1.0],"matrix":[1.0,0.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,0.0,1.0,0.0,7.0,8.0,9.0,1.0]}
true
(1, 2, 3)
3
$: expected an array of 3 numbers for 'Vec3', found an array of 2 items
$[2]: expected a number, found a string
$: expected an array of 3 numbers for 'Vec3', found an object
$.data: a 2x2 matrix takes 4 elements, got 3
[1.5, 2]
"""


class Json(unittest.TestCase):
    def test_as_arrays_in_the_interpreter_and_natively(self) -> None:
        self.assertEqual(run_source_both_now(JSON_PROGRAM), (JSON_WANT, "", 0))

class Generated(unittest.TestCase):
    def test_the_modules_are_the_generators(self) -> None:
        proc = subprocess.run([sys.executable, os.path.join(_REPO, "scripts", "gen_std_linalg.py"), "--check"],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)


class Benchmark(unittest.TestCase):
    def test_its_by_hand_versions_are_tested(self) -> None:
        # benchmarks/linalg_std.my times the library against loops by hand;
        # its #test cases keep the two computing the same (MYLA-587)
        from tests.burn._tools import STDLIB_ROOT, selfhost_tool
        proc = subprocess.run([selfhost_tool("main"), "test", os.path.join(_REPO, "benchmarks", "linalg_std.my"),
                               "--stdlib", STDLIB_ROOT], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("5/5 passed.", proc.stdout)

if __name__ == "__main__":
    unittest.main()
