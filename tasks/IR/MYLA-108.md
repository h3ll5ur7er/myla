---
id: MYLA-108
title: IR: optimisations
type: feature
status: in-progress
priority: medium
labels: [ir, codegen, selfhost]
---
Step 6 of [[MYLA-67]] ([[Architecture/IR]]): each optimisation a separate change, measured on the compiler compiling itself (time, binary size, peak memory) and checked by the verifier and the gates.

- [x] Retain and release walks out of line (a helper per aggregate type instead of the walk at every site)
- [x] A temporary read right after it is computed taken from `%rax` (its store held back, and dropped when nothing else reads it)
- [x] Constants and addresses recomputed where they are read; call arguments pushed from their slots
- [x] A variable's value read where it is used, when nothing in between can write a slot
- [ ] Frame slot reuse
- [ ] Retain/drop pairs that cancel (a list copied and never written)
- [ ] Scalars in registers (a simple allocator over temporaries)
- [ ] Copy elision for aggregate results
- [ ] Dead functions after monomorphization

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
