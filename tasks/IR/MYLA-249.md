---
id: MYLA-249
title: Float values in xmm registers
type: improvement
status: review
priority: high
labels: [backend, performance, floats, codegen]
---
Found by the benchmarks ([[MYLA-242]]): float code runs 4–6 times C's instructions, the largest instruction gap of the twelve programs (mandelbrot 4.3×, n-body 5.9× against C with Myla's semantics at gcc `-O2`). The register allocator ([[MYLA-121]], [[MYLA-134]]) gives float temporaries general-purpose registers. So every float operation moves both operands into `%xmm0`/`%xmm1` with `movq`, operates, and moves the result back: about five instructions and two register-file crossings where C has one `mulsd`.

- [x] Float temporaries and slots allocated in `%xmm` registers, a register class of their own in the linear scan; the operations take their operands where they are
- [ ] Constants from memory (`movsd .LC(%rip)`) or `xorpd` for 0.0, instead of `movabs` and a move
- [x] Saving and restoring across calls: every `%xmm` register is caller-saved in Myla's convention; a value whose interval holds a call keeps a general-purpose register (a callee-saved one survives the call)
- [x] Measured: mandelbrot and n-body ([[MYLA-242]]), and that the float formatting stays byte-identical to the interpreter

## Evidence

- **The test first.** `tests/burn/test_float_registers.py` looks at the code of the mandelbrot loop: at most 6 moves from a general-purpose into an `%xmm` register, at least 4 operations on `%xmm2`–`%xmm15`. Before the change it had 23 moves. A program of floats must print the same natively and interpreted: float32 rounding, NaN in comparisons and branches on either side, signed zeros, casts, `sqrt`, values across calls and loops.
- **Allocation.** A float temporary or variable slot whose interval holds no clobbering position gets one of `%xmm2`–`%xmm15` (`alloc_xmm`, a linear scan before the general-purpose one, a lighter value giving way to a heavier one). `%xmm0` and `%xmm1` stay scratch. Every call clobbers, so a value in an `%xmm` register is never live across one and needs no save; one that is keeps a general-purpose register.
- **Emission.**
  - Float arithmetic takes its operands where they are and computes into the destination's home.
  - A comparison does `ucomisd` on the homes; one that only a branch reads (`<`, `<=`, `>`, `>=`) jumps directly, NaN going to the false branch.
  - `sqrt` is one inline `sqrtsd`, as are `to_bits` and `from_bits` (a move), so none of them ends an interval.
  - A store into an `%xmm` slot moves from another `%xmm` register or through `%rax`, since a constant can't be moved into one directly.
  - Everything else (loads, stores to memory, casts, calls) works on `%xmm` homes unchanged, since `movq` moves between them and general-purpose registers or memory.
- **Measured** against the baseline ([[Development/Benchmarks]]):
  - mandelbrot 903 → 294 ms (3.1× as fast, 2.3× fewer instructions), now 1.22× C with Myla's semantics at gcc `-O2` (was 4.0×);
  - n-body 1,326 → 230 ms, most of it [[MYLA-248]]'s `sqrt`; its remaining gap is the list field accesses of its loop ([[MYLA-251]]).
  - test_math's 3,700 results stay bit-identical between the interpreter and native code.
- The bootstrap reaches its fixed point; the burn suite passes (892 tests).
