---
id: MYLA-210
title: "Decision: frame layout by liveness, its approach and timing"
type: chore
status: todo
priority: medium
labels: [decision, selfhost, backend]
---
From the October 2026 review ([[Project/Review-2026-10]], §13.2). Every IR slot gets a frame cell of its own (`layout_slots` in `ir_x86.my`): `Interp.eval` has a 2.5 KB frame, `eval_name_call` 3.7 KB, and the self-hosted interpreter needs about 25 KB of native stack per Myla call, which is why it stops at 2,500 calls ([[MYLA-182]]). It also enlarges every async frame on the heap ([[MYLA-133]]'s memory bound). Implementation task: [[MYLA-183]].

## Question

How do slots share frame cells, and is it worth doing before LLVM?

## Options

- **A. By scope.** Slots of disjoint lexical scopes and of different `match` arms share cells; computed from the block structure the IR already has. Simple, structural, most of the gain on big dispatch functions.
- **B. By liveness.** A liveness analysis on the IR and interval colouring of slots. Smallest frames; more code, and it has to respect drop points and the slots that live across suspensions of frame functions.
- **C. Leave it to LLVM.** LLVM's stack colouring does B for free from `alloca`s and lifetime markers; the assembly backend stays as it is.

## Recommendation

**A now.** The assembly backend stays the default and the bootstrap's backend whatever the LLVM decision ([[MYLA-160]]), and `build/myla`'s interpreter is compiled by it, so the gain lands where users feel it (deeper recursion in `run`, `test`, `repl`, smaller async frames). B only if measurements after A still show a problem.

## Decision

*Open.* The owner's answer goes here and, once given, onto [[Project/Decisions]] as a numbered decision.

- [ ] Decided, and recorded on [[Project/Decisions]]
- [ ] The implementation tasks created or updated to match
