---
id: MYLA-120
title: Instruction selection in the IR backend
type: improvement
status: review
priority: medium
labels: [ir, codegen, selfhost, performance]
---
Part of [[MYLA-109]]. `ir_x86.my` loads every operand into a fixed register and leaves every result in `%rax`, so a comparison feeding a branch materialises a bool first (`cmp; setge; movzbq; testq; jz`), an immediate or a variable is loaded into `%rcx` before an operation that could read it directly, and an element's address takes three instructions where one addressing mode would do. On the compiler compiling itself, 21% of the emitted instructions are loads and stores of frame cells, and 1.4% `setcc`.

Each step is measured on the compiler compiling itself (callgrind's instruction count, which is exact, and the wall time), as [[MYLA-108]] did, and kept only if it pays.

- [x] A comparison whose only use is the branch ending its block becomes a compare and a conditional jump; a branch falls through to whichever successor comes next (3,502.6 → 3,287.5 million instructions, −6.1%; 1.00–1.05 → 0.93 s; assembly 6.06 → 5.93 MB)
- [x] Operands taken where they are: an immediate, a variable's slot or an argument word as the second operand of an operation or comparison (3,277.2 → 3,213.1 million instructions, −2.0%; assembly 5.92 → 5.86 MB); integers wrapped to their width in one instruction (3,287.5 → 3,277.2)
- [x] Addressing modes: an element's or field's address folded into the load or store that uses it (3,213.1 → 3,152.7 million instructions, −1.9%; assembly 5.86 → 5.65 MB)
- [x] Small constants and zero, blocks nothing reaches (3,152.7 → 3,124.7 million instructions; assembly 5.65 → 5.46 MB; peak 92 → 87 MB). Zero stays a `movq $0`: `xorl` is shorter but writes the flags, and constants are recomputed between a comparison and its jump

## How

All in [[selfhost/ir_x86.my]] and the shared emitters of [[selfhost/codegen.my]]; the IR is unchanged.

- **Compare and branch.** `fused_compare` finds a block ending in an integer `cmp` whose result only the block's `br` reads; the loop leaves the `cmp` out and `emit_compare_branch` emits `cmpq` and `j<cond>` (`jump_cond`, `negated_cond`), jumping to whichever successor isn't emitted next. A plain `br` likewise jumps with `jnz` when its false successor comes next. Float comparisons keep their `setcc` sequence (the parity flag for NaN).
- **Wrapping.** `wrap` re-canonicalises an 8-, 16- or 32-bit result with one `movs`/`movz` instruction instead of a shift pair or a mask.
- **Operands.** `second_operand` gives `emit_int_op` its second operand for `+ - * & | ^` and the comparisons (`takes_operand`): an immediate for a constant that fits 32 bits (`temp_imm`, filled by `remat_texts`), the variable's slot a temporary was read from (`temp_src`), or the temporary's cell, which holds its value once `%rax` is loaded (no store is held back then); else `%rcx` as before.
- **Addresses.** A `load` or `store` through a slot's address uses the frame offset directly (`temp_frame`); `emit_elem_addr` is one `leaq` with a scaled index (`elem_operand`, a multiplication first for other strides), and `emit_elem_load` folds an element's address into the `load` or `load8` right after it. An integer constant that fits 32 bits loads with `movq $v` (`int_const_text`) instead of `movabsq`.
- **Unreachable blocks.** `reachable_blocks` walks the terminators from the entry; a block it doesn't reach gets no label or code, only its `scope` and `bind` (so the debug scopes stay nested), and fall-through goes to the next block with code.

## Evidence

- New test first: `test_a_comparison_feeding_a_branch_is_a_conditional_jump` (signed, unsigned, char and bool conditions, a `while`, and a comparison kept as a bool) failed with 7 `setcc` in the function and passes with 1. Mutation check: jumping on the condition instead of its negation fails it and most of the corpus.
- The codegen gate (corpus, parity and stress programs, diagnostics), the debug-information tests (gdb) and the bootstrap's fixed point pass after each step.
- The same source (the compiler) compiled by the code generator before and after: 3,554.8 → 3,124.7 million instructions compiling itself (−12.1%), binary 1,460,976 → 1,300,568 bytes (−11.0%); wall time, alternating runs: best 1.061 → 1.043 s, median 1.223 → 1.120 s.
- The stress programs, same comparison: 0 to 16% fewer instructions each (lists −15.8%, a match's result −12.7%, `?` −7.0%, maps −1.2%; the allocator stress is unchanged).
- On the last commit: unit 595, integration 2, burn 736 (5 skipped) and the extension's 54 tests pass; the bootstrap reaches its byte-identical fixed point (5,463,803 bytes).
