---
id: MYLA-125
title: Instruction selection follow-ups in the IR backend
type: improvement
status: review
priority: medium
labels: [ir, codegen, selfhost, performance]
---
Left over from [[MYLA-121]]; each measured on the compiler compiling itself and the stress programs, kept only if it pays.

- [x] A division or remainder by a constant other than 0 and −1 skips the zero and −1 tests (`emit_int_op`)
- [x] A value loaded into a temporary that lives in a register goes straight there (`load`, `load [%p + off]`), not through `%rax` and a held-back store, when the next instruction doesn't take it from `%rax`
- [x] Found on the way: a negative integer literal was a negation of a constant, so `x / -3` had no immediate divisor; the lowering makes it a constant

## How

- **Constant divisors** ([[selfhost/ir_x86.my]], `emit_int_op` in [[selfhost/codegen.my]]). A `/` or `%` whose divisor is an immediate other than `$0` and `$-1` loads it into `%rcx` and divides without testing for zero or −1; an unsigned one by a power of two (`power_of_two`) is `shrq` or `andq`.
- **Negative literals** ([[selfhost/lower.my]]). A `-` on an integer literal becomes the constant itself, an immediate where it fits.
- **Loads straight into registers.** When the held-back move `movq %rax, %R` of a temporary living in a register is flushed and the line before it is `movq X, %rax` or `leaq X, %rax` with X not reading `%rax`, that line loads into `%R` instead (`flush_temp`, `fold_load`). `load_temp` does the same when it takes a value read only once into another register. The two flushes after which `%rax` must still hold the value (`store_temp`, and `load_temp` taking a value read again) keep it there (`flush_temp_in_rax`).

## Evidence

- New tests first: `test_division_by_a_constant_tests_nothing` (signed and unsigned, a negative divisor, an unsigned power of two, against the interpreter; a divisor that may be 0 or −1 keeps both tests) and `test_loads_go_straight_into_registers` (no `movq X, %rax` and `movq %rax, %R` pair left in the compiled functions); both failed before.
- The same source (the compiler) compiled before and after: 2,610.6 → 2,558.2 million instructions compiling itself (−2.0%), binary 1,244,504 → 1,223,608 bytes (−1.7%); wall time, 20 alternating runs: median 0.885 → 0.862 s (best 0.787 → 0.783 s). The compiler had 6,612 such load-and-move pairs and 27 tested constant divisors.
- The stress programs, together with [[MYLA-126]]'s first step: 67,975.7 → 66,920.1 million instructions (−1.6%), from 0 to −2.5% each, none worse.
- Unit 595, integration 2, burn 741 (5 skipped) and the extension's 54 tests pass; the bootstrap reaches its byte-identical fixed point (5,157,378 bytes).
