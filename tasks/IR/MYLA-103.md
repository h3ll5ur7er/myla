---
id: MYLA-103
title: IR: data types, flags and scalar functions
type: feature
status: review
priority: high
labels: [ir, codegen, selfhost]
---
The first step of [[MYLA-67]] ([[Architecture/IR]], D79): the IR exists, prints, and carries scalar functions to assembly, with every other function still emitted by the current path.

- [x] `selfhost/ir.my`: `IrFunc`, blocks, instructions, operands, kinds; `render_func` (the text form of [[Architecture/IR]])
- [x] `selfhost/lower.my`: scalar functions (integer, float, `bool`, `char` locals and parameters, arithmetic with its traps, comparisons, casts, `if`/`while`/`for` over ranges, `break`/`continue`, calls of user functions with scalar arguments and results, `print` of scalars) → `IrFunc`; anything else is reported as unsupported
- [x] `selfhost/ir_x86.my`: `IrFunc` → assembly through the code generator's pools; `loc` → `.loc` with `-g`
- [x] `--ir`, `--ir-stats` and `--emit-ir` in `gen_main` (and `--ir` in `build/myla build`); the per-function fallback in `generate`
- [x] Tests: the codegen gate and the parity programs also run with `--ir`, with the same output; IR text for a few functions checked; `--ir-stats` shows how many functions of the corpus went through the IR

## How

- **The IR (`selfhost/ir.my`):** an `IrFunc` holds its slots (a parameter is a slot at its argument word, so it isn't copied), the type of each temporary, its blocks and the order lowering started them in (the emission order, the source order). Instructions are an enum (`Const`, `Str`, `Load`, `Store`, `Bin`, `Cmp`, `Un`, `Cast`, `Call`, `Print`, `Loc`, `Bind`, `Scope`), terminators another (`Jmp`, `Br`, `Ret`). `render_func` prints the text form.
- **Lowering (`selfhost/lower.my`):** a `Lower` struct builds the function. It takes the code generator as a borrowed parameter, since it only reads it (types, signatures, the substitution). Statements and expressions follow the old path's order of evaluation and its scopes. Anything outside the scalar subset sets the first reason and makes `lower_function` return `Err`.
- **Emission (`selfhost/ir_x86.my`):** an `impl CodeGen` block in its own module, so it shares the code generator's state (pools, runtime-error positions, debug information). Every temporary gets a frame slot. The operation sequences are the old path's own: `emit_int_op`, `emit_float_op`, `emit_cast`, `emit_unary` and `emit_print` were split out of `eval_binary`, `eval_binary_float`, `gen_cast`, `eval_unary` and `gen_print`.
- **Dispatch:** `gen_any_function` in `generate` tries the IR with `--ir` and falls back per function. `--ir-stats` and `--emit-ir` are in `gen_main`; `build --ir` is in `build/myla` (project mode too).

## Evidence

- **The old path is unchanged:** `gen_main` built from HEAD and from this change emit byte-identical assembly for the compiler itself (8,543,703 bytes), `hello` and `loops`.
- **A test program through the IR** (4 of 4 functions: arithmetic, a `for` loop, `while` with `break`/`continue`, `&&`/`||` on floats, casts, division, `print` of a literal) prints exactly what the interpreter prints.
- **`SelfHostedCodegenParityThroughIR`:** the corpus, runtime errors (with positions), module programs, stress programs and parity programs give the same results with `--ir`. The text form of a sample function matches. The examples and parity programs put 68 functions through the IR.
- **Mutation check:** a range loop comparing with `<=` instead of `<` fails the IR gate on `examples/loops.my` and `examples/semicolons.my`.
- **`build --ir`:** in `test_selfhost_cli.py`.
- **Coverage on the compiler:** 13 of 1,004 functions (the rest have aggregate or heap results or parameters, the next steps).
- **Written first:** the lowering and emission came before their tests; the tests then ran against them, and the mutation shows they catch a lowering bug.
