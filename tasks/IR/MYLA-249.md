---
id: MYLA-249
title: Float values in xmm registers
type: improvement
status: backlog
priority: high
labels: [backend, performance, floats, codegen]
---
Found by the benchmarks ([[MYLA-242]]): float code runs 4–6 times C's instructions, the largest instruction gap of the twelve programs (mandelbrot 4.3×, n-body 5.9× against C with Myla's semantics at gcc `-O2`). The register allocator ([[MYLA-121]], [[MYLA-134]]) gives float temporaries general-purpose registers. So every float operation moves both operands into `%xmm0`/`%xmm1` with `movq`, operates, and moves the result back: about five instructions and two register-file crossings where C has one `mulsd`.

- [ ] Float temporaries and slots allocated in `%xmm` registers, a register class of their own in the linear scan; the operations take their operands where they are
- [ ] Constants from memory (`movsd .LC(%rip)`) or `xorpd` for 0.0, instead of `movabs` and a move
- [ ] Saving and restoring across calls: every `%xmm` register is caller-saved in Myla's convention, so spills around calls count in the interval weights
- [ ] Measured: mandelbrot and n-body ([[MYLA-242]]), and that the float formatting stays byte-identical to the interpreter
