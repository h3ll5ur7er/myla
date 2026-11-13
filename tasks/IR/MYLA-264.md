---
id: MYLA-264
title: "The IR as a contract: typed intrinsics and each operation's exact semantics"
type: improvement
status: done
priority: high
labels: [ir, backend, design]
---
Found by [[Project/Reflection-2026-11]].

**Runtime operations are strings.** `Inst.Rt(name)` carries 19 operations that each backend recognises by name:
- atomics: `__cas64`, `__xchg64`, `__fetch_add64`, `__pause`;
- counts: `__rc_inc`, `__rc_dec`, `__rc_inc_atomic`, `__rc_dec_atomic`;
- encoded ones: `__cow:<clone>`, `__rt_addr:<sym>`, `__rt_waddr:<sym>`;
- `__run_frame`;
- math and bits: `__sqrt`, `__f64_round`, `__f64_bits`, `__f64_from_bits`, `__rotl`, `__bsr64`;
- and others.

Their memory ordering (x86-64's are full barriers by nature; aarch64 needs acquire/release) and their exact results are written nowhere. `ir.my` describes `rt` in x86-64 registers. `RtPair` exists for one fallback (`lower.my`, when `std$rt$map_put_slot` is missing) that the new backends panic on.

**Each backend re-derives what an operation means:**
- a zero divisor;
- `MIN / -1` and `MIN % -1` (x86 faults, wasm traps, aarch64 wraps);
- shift masking for 8- and 16-bit types;
- wrapping and the canonical form of a temporary;
- float→integer saturation (D59);
- float32 rounding;
- float `%`: x87 `fprem` on x86-64, `std.rt`'s `fmod` elsewhere, two implementations of one operation.

- [x] Intrinsics as a typed instruction (an enum, with arguments and result types), each with its semantics and, for the atomics, its ordering; the string prefixes gone; `RtPair` gone
- [x] [[Architecture/IR]]: every instruction's exact semantics, written as the contract a backend implements, including the edge cases above; the x86-specific wording (`%rdi`, `%rax`) gone
- [x] A conformance set: one program per operation and edge case, run on every target against the interpreter (grows from `test_aarch64.py`'s `PROGRAMS`)
- [ ] Float `%` through `std.rt`'s `fmod` on x86-64 too, if it costs nothing measurable (dropped: it costs measurably, 0.054 against 0.115 s for 5 million `%`, so x86-64 keeps `fprem`; see "Done" below)

## Done (2026-11-06)

- **`intr`**: `Inst.Intr(dst, Intrinsic, args)` in [[selfhost/ir.my]]. `Intrinsic` has the 20 operations every backend did in place by name: `sqrt`, `f64_round`, `f64_bits`, `f64_from_bits`, `rotl`, `bsr64`, `cas64`, `xchg64`, `fetch_add64`, `load_acq64`, `store_rel64`, `pause`, the four counts, `run_frame`, and the three whose payload was in the string, `unique <clone>` (was `__cow:<clone>`), `rt_addr <sym>` and `rt_waddr <sym>`. Each variant's comment is its contract, its ordering included. `intrinsic_arity`/`intrinsic_gives` give its shape, which `verify` checks. `rt` now only calls a runtime routine. The lowering builds an intrinsic from a std.rt primitive's name (`primitive_intrinsic`, `rt_inst`); `ownership.my` builds the counts and `unique` directly.
- Each backend translates it in one `match` (`emit_intr`, `a64_intr`, `wasm_intr`); x86-64's other readers of the names (the fused compare-and-branch, the atomics' operands, the runtime variable's operand, the call costs, the pure instructions) match the enum. `rt_internal`, `rt_cow` and the name parsing went.
- **`RtPair` gone**, with the fallback that emitted it: `map_put` called `__map_set_slot` when std.rt's `map_put_slot` was missing, but std.rt is always loaded and no runtime defines that routine any more.
- **The contract**: [[Architecture/IR]]'s "What each instruction means": values and canonical form, integer and float arithmetic (the zero divisor, the minimum by -1, shift masking, `fmod`), comparisons, negation, casts (D59's saturation), memory, calls, `rt`, each intrinsic with its ordering, traps. The `rt` text no longer names x86-64 registers.
- **The conformance set**: [[tests/burn/test_ir_contract.py]], one program over those edge cases with its output written down, run in the interpreter and natively, and on aarch64 and wasm32 by `scripts/test-target.py` (now in `_targets.SUITES`). Each value was checked by hand against the contract (`-100i8 << 9` is 56: the count 1, the result wrapped; `sqrt(-0)` is -0; `16777216f32 + 1` is 16777216; a NaN cast to `int16` is 0).
- **Evidence that nothing changed in what is generated**: the compiler before and after builds every example for every target (96 binaries) and the whole compiler for each of the three targets, byte for byte the same.
- **Float `%` on x86-64 stays x87's `fprem`**: through std.rt's `fmod` it costs measurably. 5 million `x % 3.25` take 0.054 s with `fprem` against 0.115 to 0.126 s through `fmod`, three runs each. Both give the same values (the conformance program's `%` cases pass on every target), and every NaN reads as the canonical one (D128), so the two implementations can't be told apart.
- Not done here: `ir.my`'s `test_func #1` `#test` case fails before and after this change (a temporary's list), unrelated.
