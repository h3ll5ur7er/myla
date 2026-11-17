---
id: MYLA-796
title: "R7-7 Numerics: matrix shapes (H11), inverse (M7), sinh/tanh/log10 accuracy (M6), the implicit std.float's cost (M4), float printing (M17)"
type: bug
status: todo
priority: high
labels: [numerics, round-7]
---
Work package of [[Project/Review-2026-11-17]], lane "Numerics" (section 5). Files: `lib/std/matrix*.my`, `vector*.my`, `quaternion*.my`, `lib/std/float.my`, `math.my`, `fmt.my` (float printing), and the checker's registration of `std.float`'s methods only where decision 4 needs it. The reproducers are in the review's bundle (`repro-r6/`, with a README per area); each fix turns its reproducer into a test that fails before it. The owner's decisions it builds as the review recommends: 4 (lazy std.float). New tasks it files take ids 849–856.

- [ ] **H11** (high, new): `json.decode<Matrix>` of `{"rows":65536,"cols":65536,"data":[]}` traps where checked and gives a matrix with no data in a plain build; `matrix(65536, 65536, [])` and `identity(46341)` the same (D184). `repro-r6/library/json_matrix_shape_overflow.my`, `matrix_shape_overflow.my`. Reopens [[MYLA-587]], whose box "`#test` cases on every value-returning function" is false (matrix 10 of 120, quaternion 3 of 29)
- [ ] **M7**: `Mat4.inverse` of an exactly singular integer matrix is `Some` with elements of -4.5e15; `Mat2`/`Mat3` of the identity times 1e-200 give `None`. `mat_inverse_singular.my`
- [ ] **M6**: `sinh` up to 73,870 ulps and `tanh` 32,380 from libm; `(-0.0).tanh()` is `+0.0`; `710.0.sinh()` is `inf`. Old: `math.log10(0.999999)` is off (the page promises 1 ulp). `float_sinh_tanh_accuracy.my`, `math_log10_near_one.my`. Reopens [[MYLA-585]]
- [ ] **M4** (new): the implicit `std.float` adds 4.6 M instructions (22 percent) to every `myla check` and about 5 M to every run by importing `std.math`. Decision 4: register its methods lazily (load `std.math` only when a float method is called); [[MYLA-793]] adds the guard test
- [ ] **M17** (old): a random-exponent float takes 6.5 M instructions to print. `float_print_slow.my`. File a task
- [ ] Low: `Matrix.col(3)` of a 2×3 prints `[]`; `NaN.clamp(0, 1)` is 1; vector `Format` ignores its spec; `json.encode` of a NaN vector is `[null,null]`, which doesn't decode; `normalized()` of `(1e200, 1e200, 0)` is zero; [[MYLA-586]]'s `cannot hash NaN` points into `std/hash.my`; [[MYLA-550]]'s note that the new modules are where D184 fails now
