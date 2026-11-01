---
id: MYLA-119
title: Lookup tables instead of linear searches in the self-hosted compiler
type: improvement
status: done
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

- [x] Maps from name to index for functions, structs, enums, variants and string literals in `codegen.my` (and the checker's `func_idx`/`enum_idx`)
- [x] Measured on the compiler compiling itself, as [[MYLA-108]] does

## How

- **Code generator:** `new_codegen` builds maps from name to index for functions, structs and enums (the first of each name, as the searches found), sets of enum names, variant names and payload-less variant names, and an index of interned string literals that `string_label` keeps up. `sig_of`, `has_func`, `has_function`, `struct_info`, `enum_info`, `is_enum_name`, `is_variant_name`, `is_nullary_variant` and `str_index` look them up. The worklists' "done or queued" checks (`fn_done` plus a scan of the worklist, `lam_done`) became sets (`fn_seen`, `lam_seen`).
- **Checker:** `struct_map`, `enum_map`, `func_map` and `method_map` (`key\tname`) are kept by `add_struct`, `add_enum`, `add_function` and `add_method`, the only places those tables grow; `struct_idx`, `enum_idx`, `func_idx` and `method_sig` look them up.

## Evidence

- **Measured** (the compiler built by itself, compiling itself): 0.97 s, against about 1.9 s before, with the same peak, binary and assembly. The compiler built this way reproduces its own output. callgrind counts 3.3 billion instructions instead of 6.3; nothing takes more than 5% now (`enum_variant_payload` 4.7%, `__alloc` 4.5%, `__str_concat` 4.1%).
- **Tests:** the checker, codegen and interpreter gates pass.
