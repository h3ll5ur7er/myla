---
id: MYLA-294
title: "Hardening the optimisation passes: round caps, single definitions, hoist dominance, intrinsic operand kinds"
type: improvement
status: backlog
priority: medium
labels: [ir, optimisation, verifier]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]). None of these is reachable today (60 adversarial programs agreed with the interpreter), each is a silent miscompile waiting for the next pass:

- `widen_counters` stops its dataflow at 20 rounds and uses the partial state ([[selfhost/ranges.my]]); on hitting the cap it should give up (`return f0`)
- `ranges.my` keys facts by temporary, assuming each temporary is written once: true for today's lowering and inliner, false under `--ssa` moves or a pass reusing temporaries; an assertion in the verifier (`def_counts`) would pin it
- `only_reads_and_cows` relies on a loop being a contiguous emission range entered once ([[selfhost/hoist.my]]); a verifier check that a hoisted `cow`'s result dominates its uses would catch a later block reordering
- `clobber_kind` assumes no intrinsic but `unique`, `run_frame` and `call_code` uses `%r8`–`%r11` ([[selfhost/ir_x86.my]]); a comment on `emit_intr` listing each intrinsic's scratch registers
- the verifier checks an intrinsic's arity and result but not its operand kinds (a `cas64` on an `int32` temporary passes); cheap to add from `temps[]` ([[MYLA-264]])

- [ ] Each of the five, with a `#test` or a verifier case
