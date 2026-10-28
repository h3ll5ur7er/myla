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

## How (walks out of line)

- **Why:** dropping or retaining an enum dispatched on its tag inline, at every site, and every `return` drops every owner. A `Type` local of the checker cost some 50 instructions per drop, and `cmpq $N, %rax`/`jne` pairs were the most frequent instructions after loads and stores.
- **Change:** `owned_walk` now calls `__walkd_<T>` (release) or `__walkr_<T>` (retain) with the value's address in `%rdi`, for an enum and for a struct or tuple with more than one member owning heap values. Each helper is emitted once, keeps the address in `%rbx` and walks inline (`owned_walk_inline`), calling the helpers of nested types in turn. The other walks stay inline.
- **Helpers:** `emit_drop_helpers` runs the drop, clone and walk worklists to a common fixed point (a helper of one kind can ask for one of another) and emits the builder's helpers last.
- **Registers:** a retain walk used to make no calls and keep every register but `%rax`; now it may call a helper. The map clone helper walked a slot's key and value from `%rcx`, so it now keeps the slot's address on the stack. The other callers walk from callee-saved registers or the frame.

## Evidence (walks out of line)

- **Measured:** the assembly shrinks by 28% (13.67 → 9.79 MB, below the old path's 10.46 MB), the binary by 24%, the peak by 22 MB, and the self-compile by 0.11 s. The compiler built this way reproduces its own output.
- **Tests:** the stress programs stay at 11 MB, and the codegen gate, the parity tests and the debug-information tests pass (181 tests).
