---
id: MYLA-587
title: std.vector, std.matrix and std.quaternion
type: feature
status: todo
priority: high
labels: [stdlib, numerics, graphics]
---
The numeric toolbox that `std.jpeg`, `std.imgproc`, `std.ai` and the planned GUI system will build on. The owner's shape (2026-11-13): the common fixed sizes as their own types, plus a slower generic type of any size whose dimensions are checked at run time.

- `std.vector`: `Vec2`, `Vec3`, `Vec4` (structs `{ x, y[, z[, w]] }`), and `Vector`, any length (`[float]` inside; a size mismatch is a runtime error that names both sizes).
- `std.matrix`: `Mat2`, `Mat3`, `Mat4`, and `Matrix`, any `rows × cols` (one flat list inside; shapes checked at run time).
- `std.quaternion`: `Quat` (from axis and angle, from Euler angles, to `Mat3`/`Mat4`, `slerp`, rotating a `Vec3`).
- Operators wherever they read naturally, through [[MYLA-584]]: `+ -` between same-sized values, `*` and `/` by a scalar on either side, `Mat * Vec`, `Mat * Mat`, `Quat * Quat`, `Quat * Vec3`, unary `-`, and the compound forms (`pos += vel * dt`). Named methods for the rest: `dot`, `cross`, `length`, `length_squared`, `normalized`, `distance`, `lerp`, `transpose`, `determinant`, `inverse` (an `Option`), `identity`, the 3D transforms (`translation`, `rotation_*`, `scaling`, `look_at`, `perspective`, `orthographic`).
- `#derive(Eq, Hash)` (with [[MYLA-586]]), `impl Format` (`f"{v}"` as `(1, 2, 3)`), `#derive(Json)` where it fits.

Depends on [[MYLA-584]] (operators between different types) and [[MYLA-585]] (float methods). Building it first with methods only would give the library an API to rewrite.

## Open questions for the owner

- [ ] Element type: `float64` only (Myla's `float`); also `float32` variants for graphics and GPU upload (`Vec3f`/`Mat4f`, or `Vec3<T>` generic with `T: Float`, which needs a numeric trait and spells `Vec3<float>` everywhere since type parameters have no defaults)
- [ ] Matrix storage and multiplication convention: column-major and column vectors (OpenGL, glam, most GPU APIs) or row-major
- [ ] Construction: Myla has no static functions, so `vector.vec3(1.0, 2.0, 3.0)`, the struct literal after `from std.vector import Vec3`, and `Vec3.zero()` through a trait with functions without `self` (D172), say `Zero`/`One`/`Identity` in a small `std.num`-level trait module
- [ ] Indexing `v[0]` and `m[r, c]` needs an `Index` trait (an open question in [[MYLA-584]]); until then `v.at(i)`, `m.at(r, c)`

## Steps

- [ ] The open questions decided
- [ ] `lib/std/vector.my`, `matrix.my`, `quaternion.my` with `#test` cases on every value-returning function; a burn test interpreted and natively; benchmarks of `Mat4 * Mat4` and `Vector` dot products (`std.bench`) against the same loops by hand
- [ ] An example in `examples/` (a small 3D transform pipeline), registered in the example tests
- [ ] Docs: one Standard-library page per module, the skill's `reference/stdlib.md`
