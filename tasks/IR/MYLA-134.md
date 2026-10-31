---
id: MYLA-134
title: Caller-saved registers for values no call comes between
type: feature
status: done
priority: medium
labels: [codegen, selfhost, performance]
---
After [[MYLA-133]]: the self-compile is bound by memory traffic, mostly the frame cells of the generated code. [[MYLA-121]]'s allocator gives values only %rbx and %r12-%r15, which a function saves and restores, so a value that would fit in a register but isn't worth a save stays in the frame.

- [x] The allocator also hands out %r8-%r11 to a value whose interval contains no position that calls something (a function, a runtime helper, a retain or drop walk, a float `%`) or uses those registers itself (`clobbers`, counted per position in `cpre`); they take precedence, and need no save
- [x] Tried and left out: %rsi and %rdi as well (clobbered by a copy too): no measurable gain, and 10 million more instructions compiling itself
- [x] Test: `test_scalars_live_in_callee_saved_registers` checks that a loop without calls lives in %r8-%r11 without saves, and one calling a function keeps its values in the callee-saved registers

## Evidence

- A compute-bound program (Collatz up to 300,000, a sieve of 5,000,000, a 220×220 integer matrix product) built by the compiler: user time best 0.445 → 0.396 s, median 0.467 → 0.411 s (−11%, alternating 20 runs), the same instructions (1,630,952,106 → 1,629,151,889): loads and stores of the frame became register moves.
- Compiling itself: 2,534,799,383 → 2,500,822,382 instructions (−1.3%); executed frame loads 189.7 → 154.2 million (−19%), frame stores 94.5 → 56.8 million (−40%); the compiler 1.0% smaller; user time unchanged within the noise (alternating 30 runs: best 0.728 / 0.729 s), as its time goes elsewhere ([[MYLA-133]]).
- All 125 parity programs print the same as before.
- Unit 595, integration 2, burn 768 (5 skipped) and the extension's 54 tests pass; the bootstrap reaches its byte-identical fixed point (5,309,629 bytes, from 5,342,845).
