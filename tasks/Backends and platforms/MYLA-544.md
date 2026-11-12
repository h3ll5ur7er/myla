---
id: MYLA-544
title: Integers of at most 32 bits divide with the 32-bit instruction on x86-64
type: improvement
status: review
priority: medium
labels: [performance, x86-64]
---
Found by [[MYLA-543]]: `/` and `%` on `int` (and every narrower type) were a 64-bit division (`cqo; idivq %rcx`), which is two or more times slower than the 32-bit one on many processors. benchLANG's primes workload, bound by the divider, took Myla 1.16 s where most compiled languages tie at 0.69 s.

Done means: operands of at most 32 bits divide with `idivl`/`divl`, with the same results as before (truncation, the minimum by -1 wrapping, a zero divisor's runtime error), the bootstrap's fixed point, a new seed, and the measurement before and after.

- [x] Test first: `test_narrow_integers_divide_in_32_bits` (results at the edges, and the instruction per type)
- [x] `emit_divide` in [[selfhost/codegen.my]]: `cltd; idivl %ecx` then `cltq` or `movslq %edx, %rax`; `xorl %edx, %edx; divl %ecx`; 64-bit operands as before
- [x] The whole burn suite
- [x] benchLANG run again ([[Development/Benchmarks]])
- [x] New seed (`scripts/update-seed.sh`)

Not in this task: aarch64 (`sdiv`/`udiv` on `x` registers) and wasm (`i64.div_s`) still divide in 64 bits; the divisor's tests for 0 and -1 stay, also where a loop's divisor is plainly positive.

## Evidence

- The test before the change: `AssertionError: 'idivl %ecx' not found` in `myla_s32` (`cqo; idivq %rcx`), with the program's output already as expected; after it: passes.
- `scripts/bootstrap.sh`: "OK: byte-identical fixpoint reached".
- `scripts/test.sh all`: "Ran 1548 tests … OK (skipped=365)".
- The same `benchmarks/benchlang/bench.my`, compiled by the compiler before and after, pinned to one CPU of one machine, twice each: primes 1.600 s and 1.583 s before, 1.001 s and 0.991 s after; strings 1.69/1.75 s before, 1.53/1.62 s after; the other workloads within the noise.
- benchLANG run again ([[Development/Benchmarks]]): Myla's primes at 1.07 times C's (1.67 before), its total at 2.79 times C's (3.23 before).
