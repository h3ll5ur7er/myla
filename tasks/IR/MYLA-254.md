---
id: MYLA-254
title: "The IR's open points: addresses, widths, sizes per target, SSA"
type: design
status: in-progress
priority: medium
labels: [ir, backend, design, wasm]
---
Part of [[MYLA-160]], de-risking D117: the IR's known pressure points that a second backend and the optimisations of D117 (3) run into ([[Architecture/IR]], "Stability"). Each answer changes what the IR is, so each is a decision for the owner. Four questions, with options and a recommendation each.

## 1. Memory widths

**Today:** every load and store moves 8 bytes (`load`, `store`, `loadat`, `storeat`, `elem`), but a string's byte (`load8`). So every list element and struct field takes 8 bytes: the sieve's 40 million flags peak at 817 MB against C's 40 MB ([[MYLA-247]]).

- **A. A width on the memory instructions:** 1, 2, 4 or 8 bytes, zero- or sign-extended on load (and `float32`). Temporaries stay one class of 8-byte values; only memory gets narrow.
- **B. New narrow instructions beside `load8`,** the 8-byte ones unchanged.

**Recommendation: A.** One rule instead of a family. It maps directly onto every target (`movzbl`/`movb` on x86-64, `ldrb`/`strb` on aarch64, `i32.load8_u`/`i32.store8` on wasm). It unblocks packed list elements ([[MYLA-247]]) and later packed struct fields. The verifier and the text form show the width.

## 2. Addresses

**Today:** an address is a `uint64` temporary (`Type.TInt(64, false)` appears 59 times in [[selfhost/lower.my]]). x86-64 doesn't mind.

- **A. A pointer kind for temporaries:** the result of `addr`, `offset`, `elem`, `str`, `label` and a load of a pointer field; arithmetic on it only through `offset`, which the verifier checks.
- **B. Integers as now;** each backend works out which temporaries are addresses.

**Recommendation: A.**
- On wasm32 an address is an `i32` while an `int64` stays an `i64`, so the backend has to know which is which.
- The optimisations of D117 (3) need it to tell what may alias (a pointer into a list against an integer).
- The marking happens in the lowering, which already knows; B would re-derive it in every backend.

## 3. Sizes per target

**Today:** sizes, field offsets, element strides and the cell layouts are constants of the lowering, computed for 8-byte pointers (`CodeGen.size` and friends; a list's length at 0, capacity at 8, elements from 16), as are the runtime's and the backend's.

wasm's 64-bit memory shipped in Chrome 133 and Firefox 134 but not Safari, and is slower by design: a bounds check on every access, which a 32-bit memory avoids with guard pages. SpiderMonkey's team advises it only beyond 4 GB. So wasm means 32-bit addresses.

- **A. The lowering takes a target description** (pointer size and alignment): sizes, offsets and cell layouts computed from it, one IR per target. The runtime in Myla ([[MYLA-162]]) is compiled per target anyway.
- **B. 8-byte layouts everywhere and wasm's 64-bit memory:** one lowering, but slower on wasm and absent in Safari.
- **C. Symbolic sizes in the IR,** resolved by each backend: one IR for all targets, but every offset becomes an expression and constant folding moves to the backends.

**Recommendation: A.**
- The sizes are already computed in one place, and the lowering runs per program anyway.
- The work is moving the scattered constants (cell headers, frame headers, the runtime's offsets) behind the description.
- C buys sharing an IR between targets, which nothing needs, since a build is for one target.

## 4. SSA

**Today:** three-address code, deliberately not SSA (D79): a temporary may be assigned more than once, and locals live in slots. The optimisations D117 (3) plans would all rather see each value defined once:
- hoisting copy-on-write and bounds checks out of loops ([[MYLA-251]]);
- propagating constants and copies;
- keeping a parameter in the register it came in ([[MYLA-250]]'s follow-up).

- **A. SSA in the IR, with block parameters instead of phi nodes** (as Cranelift, MLIR and Swift's SIL do). A pass after the lowering promotes scalar slots that own nothing and whose address isn't taken (mem2reg); owning and aggregate slots stay slots, so the ownership verifier keeps working as it does. Block parameters map onto wasm's locals and onto the register allocator's moves at edges.
- **B. SSA only inside an optimisation pass,** converted back to today's form for the backends.
- **C. No SSA:** dataflow analyses over slots and temporaries as they are.

**Recommendation: A, after a prototype.**
- It is the largest of the four changes: the lowering's multiply-assigned temporaries, a dominance check in the verifier, the backend's allocator on block parameters.
- The prototype is a mem2reg pass on today's IR, which measures how many slots, loads and stores vanish in the self-compile and the benchmarks before the IR's form changes.
- B pays for SSA without letting the backends and the allocator profit. C makes each optimisation track every slot's writes itself.

## Order

1. Widths (small; unblocks [[MYLA-247]], the sieve's memory).
2. The pointer kind.
3. The target description (before the first 32-bit backend).
4. The SSA prototype, then the decision on its form.

Each step goes through the bootstrap and the gates. The remaining pressure points stay as they are until something needs them: one class of temporaries (SIMD, 128-bit), calls that never end a block (unwinding), monomorphic code.

Sources on wasm's 64-bit memory: [SpiderMonkey, "Is Memory64 actually worth using?"](https://spidermonkey.dev/blog/2025/01/15/is-memory64-actually-worth-using.html), [web-features: Memory64](https://web-platform-dx.github.io/web-features-explorer/features/wasm-memory64).

## Decided (2026-11-03)

The owner took the four recommendations: D120 (memory widths), D121 (a pointer kind), D122 (sizes from a target description), D123 (SSA with block parameters, after a prototype). The work goes in the order above:

- [x] Widths on the memory instructions; packed list elements ([[MYLA-247]])
- [x] The pointer kind: `Type.TPtr`, a kind of the IR's temporaries only (the language never names it), for the 43 address temporaries and slots of the lowering (frames, environments, element, slot and member addresses, allocations, labels, boxes, map slots); indices, lengths and a task's state word stay integers. The verifier rejects arithmetic on an address but `offset` (a `#test` in [[selfhost/ir.my]]); the debug information shows one as a number. 905 tests pass; the bootstrap reaches its fixed point; the generated code is the same.
- [ ] The target description
- [ ] The mem2reg prototype and its measurements; then SSA with block parameters
