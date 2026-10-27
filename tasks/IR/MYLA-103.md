---
id: MYLA-103
title: IR: data types, flags and scalar functions
type: feature
status: in-progress
priority: high
labels: [ir, codegen, selfhost]
---
The first step of [[MYLA-67]] ([[Architecture/IR]], D79): the IR exists, prints, and carries scalar functions to assembly, with every other function still emitted by the current path.

- [ ] `selfhost/ir.my`: `IrFunc`, blocks, instructions, operands, kinds; `render_func` (the text form of [[Architecture/IR]])
- [ ] `selfhost/lower.my`: scalar functions (integer, float, `bool`, `char` locals and parameters, arithmetic with its traps, comparisons, casts, `if`/`while`/`for` over ranges, `break`/`continue`, calls of user functions with scalar arguments and results, `print` of scalars) → `IrFunc`; anything else is reported as unsupported
- [ ] `selfhost/ir_x86.my`: `IrFunc` → assembly through the code generator's pools; `loc` → `.loc` with `-g`
- [ ] `--ir`, `--ir-stats` and `--emit-ir` in `gen_main` (and `--ir` in `build/myla build`); the per-function fallback in `generate`
- [ ] Tests: the codegen gate and the parity programs also run with `--ir`, with the same output; IR text for a few functions checked; `--ir-stats` shows how many functions of the corpus went through the IR
