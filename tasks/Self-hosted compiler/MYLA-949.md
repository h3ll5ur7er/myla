---
id: MYLA-949
title: "`list.filled` pushes one element at a time: allocating an image costs as much as a pass over it"
type: improvement
status: todo
priority: medium
labels: [performance, native, stdlib, images]
---
Found by [[MYLA-942]] and [[MYLA-933]]. std.list's `filled(n, v)` pushes `n` times, about 60 instructions an element natively; `filled` of 67 million `float32`s takes 0.48 s. Every `image.new`, every output buffer of std.imgproc and std.draw, and every decoder's pixel buffer starts there.

- [ ] Measured first: `filled` of 64 MB of `uint8`, `float32` and `int64`, natively and interpreted
- [ ] One allocation of the final size and a fill (a byte fill for zero and for one-byte elements, a word loop otherwise), through a builtin or a primitive as D64 allows, in the interpreter too
- [ ] Measured again, and `image.new` with it
