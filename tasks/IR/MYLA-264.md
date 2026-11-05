---
id: MYLA-264
title: "The IR as a contract: typed intrinsics and each operation's exact semantics"
type: improvement
status: backlog
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

- [ ] Intrinsics as a typed instruction (an enum, with arguments and result types), each with its semantics and, for the atomics, its ordering; the string prefixes gone; `RtPair` gone
- [ ] [[Architecture/IR]]: every instruction's exact semantics, written as the contract a backend implements, including the edge cases above; the x86-specific wording (`%rdi`, `%rax`) gone
- [ ] A conformance set: one program per operation and edge case, run on every target against the interpreter (grows from `test_aarch64.py`'s `PROGRAMS`)
- [ ] Float `%` through `std.rt`'s `fmod` on x86-64 too, if it costs nothing measurable
