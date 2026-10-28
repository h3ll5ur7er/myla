---
id: MYLA-120
title: Instruction selection in the IR backend
type: improvement
status: in-progress
priority: medium
labels: [ir, codegen, selfhost, performance]
---
Part of [[MYLA-109]]. `ir_x86.my` loads every operand into a fixed register and leaves every result in `%rax`, so a comparison feeding a branch materialises a bool first (`cmp; setge; movzbq; testq; jz`), an immediate or a variable is loaded into `%rcx` before an operation that could read it directly, and an element's address takes three instructions where one addressing mode would do. On the compiler compiling itself, 21% of the emitted instructions are loads and stores of frame cells, and 1.4% `setcc`.

Each step is measured on the compiler compiling itself (callgrind's instruction count, which is exact, and the wall time), as [[MYLA-108]] did, and kept only if it pays.

- [x] A comparison whose only use is the branch ending its block becomes a compare and a conditional jump; a branch falls through to whichever successor comes next (3,502.6 → 3,287.5 million instructions, −6.1%; 1.00–1.05 → 0.93 s; assembly 6.06 → 5.93 MB)
- [x] Operands taken where they are: an immediate, a variable's slot or an argument word as the second operand of an operation or comparison (3,277.2 → 3,213.1 million instructions, −2.0%; assembly 5.92 → 5.86 MB); integers wrapped to their width in one instruction (3,287.5 → 3,277.2)
- [ ] Addressing modes: an element's or field's address folded into the load or store that uses it
- [ ] Small constants and zero (`xorl`), blocks nothing reaches
