---
id: MYLA-294
title: "Hardening the optimisation passes: round caps, single definitions, hoist dominance, intrinsic operand kinds"
type: improvement
status: done
priority: medium
labels: [ir, optimisation, verifier]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]). None of these is reachable today (60 adversarial programs agreed with the interpreter), each is a silent miscompile waiting for the next pass:

- `widen_counters` stops its dataflow at 20 rounds and uses the partial state ([[selfhost/ranges.my]]); on hitting the cap it should give up (`return f0`)
- `ranges.my` keys facts by temporary, assuming each temporary is written once: true for today's lowering and inliner, false under `--ssa` moves or a pass reusing temporaries; an assertion in the verifier (`def_counts`) would pin it
- `only_reads_and_cows` relies on a loop being a contiguous emission range entered once ([[selfhost/hoist.my]]); a verifier check that a hoisted `cow`'s result dominates its uses would catch a later block reordering
- `clobber_kind` assumes no intrinsic but `unique`, `run_frame` and `call_code` uses `%r8`–`%r11` ([[selfhost/ir_x86.my]]); a comment on `emit_intr` listing each intrinsic's scratch registers
- the verifier checks an intrinsic's arity and result but not its operand kinds (a `cas64` on an `int32` temporary passes); cheap to add from `temps[]` ([[MYLA-264]])

- [x] Each of the five, with a `#test` or a verifier case

## Evidence

- `widen_counters` ([[selfhost/ranges.my]]): a dataflow still changing after 20 rounds gives the function back unchanged (`if changed { return f0 }`) instead of using a partial state.
- Single definitions: `widen_counters` keys a fact only by a temporary written once (`def_counts`): a load's slot, a constant 1, a comparison's result; a temporary written twice takes no part, so another pass or `--ssa`'s moves can't make a fact wrong. `widens_counting_loop` (`#test`, a `while i < n { i += 1 }` built as IR): widened, and not when the step's loaded temporary is written a second time, which without the guard it would have been.
- `hoist_loop` ([[selfhost/hoist.my]]): the single-entry check (the head entered from one block outside the range, no other block entered from outside) is what makes the hoisted `cow` come before every use it renames in any block order; a block of the cycle emitted outside the range is a predecessor from outside, which it refuses. Written down there; no check added, as the existing one covers the reordering the review feared.
- `emit_intr` ([[selfhost/ir_x86.my]]) lists each intrinsic's scratch registers: none outside `%rax`, `%rcx`, `%rdx`, `%xmm0` (which the allocator doesn't hand out) but `run_frame`'s and `call_code`'s `%rdi` and `%r11`, which call and count as clobbering (`clobber_kind` 2, three `#test` cases).
- The verifier ([[selfhost/ir.my]]) checks an atomic's operand kinds: every operand of `cas64`, `xchg64`, `fetch_add64`, `load_acq64`, `store_rel64` a 64-bit word (an address or a 64-bit integer); `L0: intr load_acq64 takes 64-bit words, given %t0 (str)` (`#test`). The verifier runs on every function compiled, so the bootstrap is its test on real code. `test_func`'s own `#test` expectation was stale (it lacked the third temporary) and is fixed: `myla test selfhost/ir.my` 118 of 118.
