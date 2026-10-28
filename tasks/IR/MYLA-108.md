---
id: MYLA-108
title: IR: optimisations
type: feature
status: review
priority: medium
labels: [ir, codegen, selfhost]
---
Step 6 of [[MYLA-67]] ([[Architecture/IR]]): each optimisation a separate change, measured on the compiler compiling itself (time, binary size, peak memory) and checked by the verifier and the gates.

- [x] Retain and release walks out of line (a helper per aggregate type instead of the walk at every site)
- [x] A temporary read right after it is computed taken from `%rax` (its store held back, and dropped when nothing else reads it)
- [x] Constants and addresses recomputed where they are read; call arguments pushed from their slots
- [x] A variable's value read where it is used, when nothing in between can write a slot
- [x] Frame slot reuse: temporaries whose lives don't overlap share a cell, next to `%rbp`
- [x] Retain/drop pairs that cancel: a new value (a call's result, a literal, a concatenation) moved out of its temporary into the place it is stored
- [x] Retain/drop pairs that cancel for a copy never written: not done (see below)
- [x] Scalars in registers (a simple allocator over temporaries): tried, measured, not kept (see below)
- [x] Copy elision for aggregate results: a call's result, struct, tuple or enum built straight into a new variable or the caller's storage
- [x] Dead functions after monomorphization

## Measurements

The compiler built by itself, compiling itself (`selfhost/gen_main.my`), best of three; the peak is the compiler's own.

| Change | Time | Peak | Binary | Assembly |
| --- | --- | --- | --- | --- |
| The old path (63b1621) | 3.80 s | 128 MB | 2.39 MB | 10.46 MB |
| The IR, old path deleted ([[MYLA-107]]) | 2.37 s | 135 MB | 3.36 MB | 13.67 MB |
| Walks out of line | 2.26 s | 113 MB | 2.54 MB | 9.79 MB |
| Temporaries in `%rax` | 2.08 s | 108 MB | 2.21 MB | 8.67 MB |
| Constants and addresses recomputed | 2.00 s | 97 MB | 1.83 MB | 7.30 MB |
| Variables read where used | 2.01 s | 95 MB | 1.72 MB | 6.91 MB |
| New values moved, not retained and dropped | 1.84 s | 93 MB | 1.59 MB | 6.32 MB |
| Only reachable functions emitted | 1.72 s | 91 MB | 1.49 MB | 5.91 MB |
| Aggregates built in place | see below | 90 MB | 1.46 MB | 5.83 MB |
| Temporaries share frame cells | see below | 89 MB | 1.39 MB | 5.82 MB |

Times vary by about ±0.1 s between runs on this machine; the last rows' times are within that. Measured after the last row, alternating runs on an idle machine: a median of 2.02 s and a best of 1.87 s, against 3.80 s for the old path.

## How (walks out of line)

- **Why:** dropping or retaining an enum dispatched on its tag inline, at every site, and every `return` drops every owner. A `Type` local of the checker cost some 50 instructions per drop, and `cmpq $N, %rax`/`jne` pairs were the most frequent instructions after loads and stores.
- **Change:** `owned_walk` now calls `__walkd_<T>` (release) or `__walkr_<T>` (retain) with the value's address in `%rdi`, for an enum and for a struct or tuple with more than one member owning heap values. Each helper is emitted once, keeps the address in `%rbx` and walks inline (`owned_walk_inline`), calling the helpers of nested types in turn. The other walks stay inline.
- **Helpers:** `emit_drop_helpers` runs the drop, clone and walk worklists to a common fixed point (a helper of one kind can ask for one of another) and emits the builder's helpers last.
- **Registers:** a retain walk used to make no calls and keep every register but `%rax`; now it may call a helper. The map clone helper walked a slot's key and value from `%rcx`, so it now keeps the slot's address on the stack. The other callers walk from callee-saved registers or the frame.

## Evidence (walks out of line)

- **Measured:** the assembly shrinks by 28% (13.67 → 9.79 MB, below the old path's 10.46 MB), the binary by 24%, the peak by 22 MB, and the self-compile by 0.11 s. The compiler built this way reproduces its own output.
- **Tests:** the stress programs stay at 11 MB, and the codegen gate, the parity tests and the debug-information tests pass (181 tests).

## How (temporaries in `%rax`)

- **Why:** every temporary went to its own frame slot and back. After the walk helpers, loads and stores of temporaries were 37% of the compiler's instructions, and 28,326 times a store was followed by the load of the same temporary into `%rax`.
- **Use counts:** `inst_uses` and `term_uses` (in `ir.my`) list the temporaries each instruction and terminator reads, one entry per operand, exactly what the backend loads. `use_counts` totals them per function, before `emit_ir_at` emits it.
- **Emission:** `store_temp` holds its store back (`pend_store`); `emit` and `raw` write it out before any other line. If the next line is `load_temp` of the same temporary, the value is taken from `%rax` (or moved to the register asked for), and the store is written only if the temporary is read again later. A temporary nothing reads is never stored. Any label, jump or other instruction in between writes the store first, so every other path still finds the value in its slot.

## Evidence (temporaries in `%rax`)

- **Measured:** 0.18 s faster, the binary 13% smaller (2.54 → 2.21 MB), the assembly 11% smaller (9.79 → 8.67 MB), and the peak 5 MB lower. The compiler built this way reproduces its own output.
- **Tests:** `inst_uses` has its own `#test` cases; the stress programs stay at 11 MB; the codegen gate, the parity tests and the debug-information tests pass (181 tests).

## How (constants and addresses recomputed)

- **Why:** a constant, a string's or symbol's address, or a slot's address went into a temporary's slot and came back, and a call argument was loaded and then pushed (`movq …, %rax` then `pushq %rax`, 14,362 times).
- **Change:** `remat_texts` finds the temporaries written once, by `const`, `str`, `label` or `addr`. Such a temporary gets no slot traffic: `load_temp` emits its defining instruction straight into the register asked for. A wrapped integer constant carries its final value (`wrapped`, as `wrap` leaves it). `push_temp` pushes an argument straight from its slot.
- **Definitions:** a temporary can be written in more than one block (the result of `&&`/`||` is `const 1` on one path and `const 0` on the other). `inst_defs` and `def_counts` find those, and they keep their slots. The first version missed this: the compiler built with it couldn't read its own modules (every such result was the last constant), while every stress program still passed. The new parity program `logical_results_as_values` keeps `&&`/`||` results as values; it fails with the bug put back.

## Evidence (constants and addresses recomputed)

- **Measured:** 0.08 s faster, the binary 17% smaller (2.21 → 1.83 MB), the assembly 16% smaller (8.67 → 7.30 MB), and the peak 11 MB lower. The compiler built this way reproduces its own output.
- **Tests:** `inst_defs` has `#test` cases; the stress programs stay at 11 MB; the codegen gate, the parity tests and the debug-information tests pass (182 tests).

## How (variables read where used)

- **Why:** the most frequent pair left was a variable read into a temporary that went to its slot (`load a; load b; op` reads `a` before `b`), 14,474 times.
- **Change:** a `load $s` whose reads all follow in the same block, with only instructions in between that write no slot (`writes_no_slot`: constants, addresses, loads, arithmetic, comparisons, casts, element addresses, checks, debug markers), is read from the variable where it is used (`reads_before_writes`); the `load` itself emits nothing. A call argument read that way is pushed straight from the variable (`temp_src`).
- **A slip:** the first version kept emitting the `load` as well, which made everything larger and slower. Comparing the two builds' instruction counts showed it.

## Evidence (variables read where used)

- **Measured:** the binary 6% smaller (1.83 → 1.72 MB), the assembly 5% smaller (7.30 → 6.91 MB), the peak 2 MB lower, and the time unchanged (the analysis costs about what it saves). The compiler built this way reproduces its own output.
- **Tests:** the stress programs stay at 11 MB, and the codegen gate, the parity tests and the debug-information tests pass.

## How (new values moved)

- **Profile first:** callgrind on the self-compile (addresses mapped to the nearest symbol, since the labels aren't typed as functions) puts most of the time in the compiler's own linear lookups: `sig_of` 7.7%, `is_enum_name` 6.3%, `has_func` 5.3%, `str_index` 3.6%, `struct_info` 1.9%. Those are source changes, not IR ones ([[MYLA-119]]). Of what the IR emits, the reference counting stood out: `let s = f()` retained the call's result into `s` and then released the statement's temporary.
- **Change:** the lowering records which owning slot holds each temporary (`holder`: the value stored into it, read from it, or its address). A value bound for a place (`let`, an assignment, a member or element store, `push`, a map insert, `return`, a match's result, a box, an environment) is taken when its holder is still one of an open statement's temporaries (`take`): the slot hands its references over (`moved`), and neither the retain nor the drop is emitted. `stage` uses such a temporary as the staged value itself. An assignment of a new aggregate to a variable needs no staged copy, as it can't share the old value.

## Evidence (new values moved)

- **Measured:** 13% faster (2.11 → 1.84 s, the earlier row's 2.01 s re-measured as 2.11 s on an idle machine), the binary 8% smaller, the assembly 9% smaller, the peak 2 MB lower. The compiler built this way reproduces its own output.
- **Mutation:** a `take` that doesn't hand the slot over (so it is still dropped) crashes or garbles three stress programs.
- **Tests:** the stress programs stay at 11 MB; the codegen gate, the parity tests and the debug-information tests pass (182 tests).

## How (only reachable functions emitted)

- **Change:** `generate` seeds the worklist with the entry point alone, not with every non-generic function. `take_ir` queues what each emitted function reaches: its direct calls (`call`, `call … sret`), the functions it makes values of, and its partial applications' targets (`request_plain`); generic instances were already queued this way. There is no dynamic dispatch to miss: trait calls are monomorphized.
- **Note:** an unreachable function is still type-checked, but no longer lowered or verified.

## Evidence (only reachable functions emitted)

- **Measured:** 0.12 s faster (less to lower and emit), the binary 6% smaller, the assembly 6% smaller (`examples/methods.my`: 42,335 → 40,718 bytes). The compiler built this way reproduces its own output.
- **Test:** `test_only_reachable_functions_are_emitted` (a function never used is left out; ones called, made values of or applied partially are emitted and run). The build before the change emits the unused function.
- **Tests:** the stress programs stay at 11 MB; the codegen gate, the parity tests, the debug-information tests and the CLI tests pass (192 tests).

## How (aggregates built in place)

- **Change:** `let x = …` and `return …` offer a destination to the aggregate they evaluate (`into`: the new variable's slot, or the function's result storage). `addr` takes it for the outermost expression only, clearing it first so no part of the expression sees it. A struct, tuple or enum literal is then built in that slot (`build_slot`, `built`), and a direct call writes its result there (`call … sret`). Neither the copy nor a temporary is emitted.
- **Telling a value built in place:** the first version marked "the destination was used" with one flag. In `let t = match o { Some(x) => x, None => { return Err(…) } }`, the nested `return` built its `Err` in place and set the flag, so the `let` never stored `t`; the verifier rejected the function (`drop of $34 (t), which holds no value`) when the compiler compiled itself. Now the address each in-place build returns is marked (`placed`), and the `let` or `return` checks its own value's address. The parity program `aggregates_built_in_place` covers this; with a shared flag again, the verifier rejects it.

## Evidence (aggregates built in place)

- **Measured:** the binary 2% smaller (1.49 → 1.46 MB), the assembly 1% smaller, the peak 1 MB lower; the time is within the noise (taken while another test run used the machine). The compiler built this way reproduces its own output.
- **Tests:** the stress programs stay at 11 MB; the codegen gate, the parity tests and the debug-information tests pass (184 tests).

## How (temporaries share frame cells)

- **Why:** every temporary had a cell of its own, so frames were large (median 400 bytes, largest 21,664), and two thirds of the frame accesses (60,847 of 91,597) needed a 4-byte offset instead of a 1-byte one.
- **Change:** `alloc_temps` gives a cell only to a temporary that is stored (not recomputed, read at least once). One read and written within a single block gets a cell from its first write to its last read; a linear scan in emission order frees the cell only after the instruction of that last read, which may still write its own result. One living in several blocks (a `&&` result, say) keeps a cell of its own, which is safe around loops. The cells come first below `%rbp`, then the slots, so `layout_slots` runs twice: once to decide what is recomputed, once after the cells are counted.

## Evidence (temporaries share frame cells)

- **Measured:** the median frame shrinks from 400 to 144 bytes (largest 21,664 → 8,752), and 1-byte offsets now cover 61% of frame accesses instead of 34%. The binary is 5% smaller (1.46 → 1.39 MB) and the peak 1 MB lower; the assembly text barely changes (shorter numbers). The compiler built this way reproduces its own output.
- **Tests:** the stress programs stay at 11 MB; the codegen gate, the parity tests and the debug-information tests pass.

## Tried and not kept: scalar locals in registers

- **Tried:** the four most-used locals of a function that are 8 bytes, own nothing and whose address is never taken lived in `%r12`–`%r15`, saved to the frame in the prologue and restored before `leave`, and not used under `-g`. A check of the emitted code confirmed that every routine writing `%r12`–`%r15` saves them first.
- **Measured** (alternating runs on an idle machine): the self-compile median went from 2.02 to 2.10 s (min 1.87 against 1.88 s), within the noise. One loop-heavy stress program got 9% faster (0.57 → 0.52 s) and another 9% slower (1.07 → 1.17 s), and the binary grew from 1.39 to 1.40 MB. The temporaries already travel in `%rax` (see above), and the compiler's locals are mostly aggregates or values that own heap memory. So it isn't kept. A real register allocator over temporaries and locals, with liveness across blocks, belongs with [[MYLA-109]]'s later backend work.

## Not done: retain/drop for a copy never written

`let ys = xs` retains, and the scope's end releases; leaving both out is only safe while neither variable is written (copy-on-write would otherwise change the copy in place) and the copy doesn't outlive the original. That needs an alias and liveness analysis over the scope, for a pair (`incq` and one release call) that the profile doesn't show among the costs. New values, the common case, are moved already (above). This goes to [[MYLA-109]] with the allocator.

## Where the time goes now

callgrind on the self-compile puts most of the remaining time in the compiler's own linear lookups (`sig_of`, `is_enum_name`, `has_func`, string interning), not in the code the IR emits: [[MYLA-119]].
