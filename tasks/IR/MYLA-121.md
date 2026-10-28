---
id: MYLA-121
title: Register allocation in the IR backend
type: improvement
status: done
priority: medium
labels: [ir, codegen, selfhost, performance]
---
Part of [[MYLA-109]], after [[MYLA-120]]. Temporaries live in frame cells and travel in `%rax` (MYLA-108); a value used again later, or a variable read often (`self`), is reloaded from the frame every time. A first try, the four most-used scalar locals in `%r12`–`%r15`, didn't pay off ([[MYLA-108]]); with operands read where they are ([[MYLA-120]]) a register can be read directly instead of moved to `%rax` first.

Before: on the compiler compiling itself, 54% of the executed instructions are in user code, and frame loads and stores are 16% of all of them (1.5% a frame load whose value is then used as an address, which a register removes outright).

- [x] Liveness of temporaries and scalar slots across blocks (shared with [[MYLA-122]])
- [x] Temporaries and scalar locals and parameters whose address isn't taken in callee-saved registers (`%rbx`, `%r12`–`%r15`), by linear scan over the liveness intervals, saved in the prologue; not under `-g`
- [x] Measured on the compiler compiling itself and on the stress programs

## How

All in [[selfhost/ir_x86.my]]; the IR is unchanged.

- **Candidates.** The temporaries that would get a frame cell (not recomputed, read at least once) and the slots of 8 bytes that own nothing and that only `load` and `store` touch (no `addr`, `drop`, `init` or `moved`), parameters included.
- **Intervals.** `alloc_regs` numbers the reachable instructions in emission order and collects what each reads and writes once (flat arrays). A temporary read where it is used (`temp_src`) counts as a read of its variable there. A value used in one block only, written before it is read, spans its first to last position; the others go through `live_spans`, a backward dataflow over 64-bit sets per block, and are stretched over every block they are live into or out of. One interval per value, no holes.
- **Linear scan.** By start position over `%rbx` and `%r12`–`%r15`. A register is free again at the position of its value's last read (an instruction reads its operands before it writes its result). When none is free, the holder with the least weight (reads and writes, ×10 per loop around them, up to 1,000; `loop_depths` counts the back jumps around a block) gives way to a heavier value. A register whose values weigh less than `REG_MIN_USE` (12) isn't worth its save and restore: its values go back to frame cells.
- **Prologue and epilogue.** The registers used are saved below the slots and restored before `leave`; a parameter in a register is loaded from its argument word. Every routine of the runtime and every inline sequence using these registers already saves them.
- **Emission.** `load_temp`, `store_temp` (its held-back store becomes a `movq` into the register), `push_temp` and `second_operand` use the register. `reg_of` gives the register holding a temporary right now (its own, or its variable's; none while its store is still held back), so a load or store through it, an offset, `incq` of a reference count, a test and the first operand of a compare and branch use it directly. Stores take an immediate or a register as their source (`value_operand`).
- **Operands swapped.** A commutative operation or a comparison whose second operand is still in `%rax` takes that one first (`swap_operands`, `swapped_cmp`), so it isn't stored and reloaded.
- **Cheaper `remat_texts`.** The definition counts are computed once per function and the texts only for the constants and addresses defined once, which paid for part of the allocator's own cost.

## Evidence

- New test first: `test_scalars_live_in_callee_saved_registers` (a loop, recursion keeping a value across a call, a method reading `self` in a loop with a call inside) failed with the loops reading and writing frame cells and passes with the frame touched only to save and restore the registers and to read the parameters; it also checks that every routine of the program saves `%rbx` and `%r12`–`%r15` before writing them.
- The same source (the compiler) compiled without and with registers: 3,318.5 → 3,299.4 million instructions compiling itself (−0.6%; most frame loads and stores become register moves, one instruction each), binary 1,336,888 → 1,242,680 bytes (−7.0%); wall time, 30 alternating runs: best 1.003 → 0.960 s, median 1.046 → 1.012 s.
- The compiler before (MYLA-120) and after, built by themselves, compiling the same source: 3,198.3 → 3,299.4 million instructions (+3.2%: the allocator's own work), but best 0.961 → 0.929 s, median 1.033 → 1.013 s; binary 1,301,504 → 1,242,680 bytes. The allocator alone cost 9.5%, then 6.4% after flattening it; `remat_texts` gave part of it back.
- The stress programs, same source without and with registers, 8 alternating runs each: sum of the medians 10.73 → 10.45 s (−2.6%); lists −25%, closures −14%, `?` after a staged value −12%, maps −7%, the others within ±4% (the map removal stress, +8% at first, is equal over 40 runs: best 0.074 → 0.071 s).
- `REG_MIN_USE`: 1, 4, 12 and 40 gave 3,380.6, 3,361.1, 3,306.9 and 3,283.5 million instructions; 4 and 12 ran equally fast (medians 1.035 and 1.041 s), 40 slower (1.061 s).
- Unit 595, integration 2, burn 737 (5 skipped) and the extension's 54 tests pass; the bootstrap reaches its byte-identical fixed point (5,264,716 bytes, from 5,463,803).

Not done here: a division by a constant still tests its divisor for zero and −1; a value loaded into a register-held temporary still passes through `%rax`.
