---
id: MYLA-119
title: Lookup tables instead of linear searches in the self-hosted compiler
type: improvement
status: backlog
priority: medium
labels: [selfhost, performance]
---
Profiling the self-hosted compiler compiling itself ([[MYLA-108]], callgrind) puts much of its time in linear searches over lists of records rather than in the code the IR emits:

| Function | Share |
| --- | --- |
| `CodeGen.sig_of` | 7.7% |
| `CodeGen.is_enum_name` | 6.3% |
| `CodeGen.has_func` | 5.3% |
| `CodeGen.str_index` (string literal interning) | 3.6% |
| `CodeGen.is_nullary_variant` | 2.5% |
| `Checker.enum_variant_payload`, `Checker.method_sig` | 2.5%, 2.4% |
| `CodeGen.has_function`, `CodeGen.struct_info` | 2.0%, 1.9% |

`__str_eq` (6.3%) is mostly their name comparisons.

- [ ] Maps from name to index for functions, structs, enums, variants and string literals in `codegen.my` (and the checker's `func_idx`/`enum_idx`)
- [ ] Measured on the compiler compiling itself, as [[MYLA-108]] does
