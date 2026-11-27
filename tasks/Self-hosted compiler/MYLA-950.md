---
id: MYLA-950
title: "Native float32 arithmetic goes through float64 and back on every operation"
type: improvement
status: todo
priority: medium
labels: [performance, native, numerics, images]
---
Found by [[MYLA-968]] and [[MYLA-959]]: each float32 operation is done in float64 and converted back (`cvtss2sd` / `cvtsd2ss` round trips), so float32 code is slower than the same in float64; std.draw's rasteriser went faster and more exact by accumulating in float64, and std.image's `to_f32` of 4096×4096 RGBA takes 1.4 s, a loop by hand as long. std.imgproc, std.vector32 and std.matrix32 compute in float32 (D201, D313).

- [ ] A small benchmark first: a float32 and a float64 dot product and a 3×3 convolution, natively on x86-64 and aarch64
- [ ] `addss`/`mulss`/`subss`/`divss`/`sqrtss` (and aarch64's single-precision forms) for float32 operands, the result rounded once as IEEE single requires, bit-identical to the interpreter
- [ ] Measured again
