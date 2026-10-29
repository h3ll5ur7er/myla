---
id: MYLA-124
title: Copies and throwaway lists in the self-hosted compiler's hot paths
type: improvement
status: review
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

- [x] `check` and the other token tests read the kind in place instead of copying the token
- [x] `alloc_temps`, `alloc_regs` and the verifier without a list per instruction
- [x] Measured on the compiler compiling itself
- [x] Found on the way: helper lookups and the exhaustiveness check's enum constructors (see How)

## How

None of it changes the compiler's output: the compiler before and after emits the same bytes for the same input.

- **Tokens** ([[selfhost/parser.my]]). `peek_kind` and `peek_kind_at` read a token's kind in place; `check`, `at_end`, `match1` and every `peek().kind` use them. `skip` moves past a token without copying it, for the 31 places that called `advance` and dropped the token.
- **Work stacks.** The verifier's and `reachable_blocks`' work lists, the lowering's scope, owner, temporary and loop stacks and the code generator's function and lambda worklists `pop` in place; the `drop_last_*` helpers that copied the whole list are gone.
- **The verifier** ([[selfhost/ir.my]]) applies an instruction's effect to its liveness list in place (`apply` returned a modified copy per instruction).
- **Reads and writes once** (`Touches` in [[selfhost/ir.my]]): every instruction's reads and writes are worked out once per function, into flat lists, for `use_counts`, `def_counts`, `alloc_temps` and `alloc_regs`, instead of `inst_uses` and `inst_defs` building two lists per instruction in each. `alloc_temps` rebuilds its list of live temporaries only when one ends.
- **Helpers by name** ([[selfhost/codegen.my]]). `register_walk`, `register_drop` and `register_clone`, called at every retain or drop of an aggregate, compared the type token of every queued helper with the new one (`register_walk` also worked out its own twice); `mono_token` was 7.8% of the self-compile. A map of the helpers asked for so far (`helper_seen`) replaces those searches.
- **Exhaustiveness** ([[selfhost/checker.my]]). `signature`, called at every step of the usefulness check, looked each variant of an enum up again by name (`enum_variant_payload`), quadratic in the variants; it walks them once.

## Evidence

On the compiler compiling itself, measured with the compiler at [[MYLA-122]] and after, both built by themselves, on the same input:

| Step | Instructions (million) |
| --- | --- |
| Before | 3,248.1 |
| Tokens, the verifier, `alloc_temps`' live list | 3,147.3 |
| Work stacks, reads and writes once | 3,030.7 |
| Helpers by name | 2,820.5 |
| Exhaustiveness | 2,564.2 (−21.1% in all) |

- Wall time, 30 alternating runs: best 0.920 → 0.741 s, median 0.993 → 0.796 s (−20%); peak 92 MB both.
- The output for the same input is byte-identical after each step.
- Unit 595, integration 2, burn 739 (5 skipped) and the extension's 54 tests pass after each step; the bootstrap reaches its byte-identical fixed point (5,246,891 bytes).
