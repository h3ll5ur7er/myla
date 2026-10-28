---
id: MYLA-124
title: Copies and throwaway lists in the self-hosted compiler's hot paths
type: improvement
status: backlog
priority: low
labels: [selfhost, performance]
---
Found while measuring [[MYLA-122]]: after the backend leaves out the retain and release of copies of fixed variables, the biggest reference-counting costs left on the compiler compiling itself come from what its own code copies (callgrind, inclusive cost of the calls into the walk and drop helpers):

| Caller | Helper | Calls | Instructions |
| --- | --- | --- | --- |
| `Parser.peek` | `__walkr_tokens$Token` | 2.2 million | 28.8 million |
| `Parser.check` | `__walkd_tokens$Token` | 1.2 million | 26.3 million |
| `ir.apply` (the verifier) | `__clone_list_.bool` | 20 thousand | 23.4 million |
| `CodeGen.alloc_temps` | `__drop_list_.i32` | 1.4 million | 22.4 million |
| `CodeGen.alloc_regs` | `__drop_list_.i32` | 0.6 million | 10.7 million |

`peek` returns a copy of a token (retained), which `check` only compares and drops; `alloc_temps` builds a new list per instruction; the verifier copies its liveness list per instruction.

- [ ] `check` and the other token tests read the kind in place instead of copying the token
- [ ] `alloc_temps`, `alloc_regs` and the verifier without a list per instruction
- [ ] Measured on the compiler compiling itself
