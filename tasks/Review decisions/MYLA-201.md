---
id: MYLA-201
title: "Decision: the end state of D71 (how many implementations a change needs)"
type: chore
status: todo
priority: high
labels: [decision, architecture, bootstrap]
---
From the October 2026 review ([[Project/Review-2026-10]], §11.1 and §13.1). Every semantic change lands in six places: the Python checker, interpreter and backend, and the self-hosted checker, interpreter and backend (`lower.my` + `codegen.my`). The Python backend is already behind on features, and an LLVM backend ([[MYLA-62]]) would make seven. D71 says the Python toolchain stays as the bootstrap and the oracle, but not how much of it has to keep up.

## Question

Which implementations does a new language or runtime feature have to reach, and what becomes of the Python backend?

## Options

- **A. Full parity, as today.** Every feature in all six; the Python backend compiles anything the self-hosted one does. Simple rule; the highest cost per feature, and seven with LLVM.
- **B. Freeze the Python backend as stage 0.** It compiles exactly what `selfhost/` and `tools/` use and nothing more; the self-hosted compiler's source may use a construct only once the Python backend has it. New features go into the two checkers, the two interpreters and the self-hosted backend (five, of which the interpreter pair is the oracle). Native parity tests run on the self-hosted backend only.
- **C. Replace stage 0 with a seed.** A released, pinned build of the compiler (or its generated assembly) bootstraps the next one, as Go and Rust do; the Python backend is deleted, the Python checker and interpreter stay as the oracle. Breaks D71's "a compiler not written in Myla" and needs a reproducible-seed story.
- **D. Bootstrap through the Python interpreter.** The Python interpreter runs the self-hosted compiler on itself; no Python backend. Almost certainly far too slow for 33,000 lines (would need measuring).

Either way, [[MYLA-181]] (one builtin table in the Python toolchain) and [[MYLA-185]] (a typed table of runtime helpers) are worth doing before LLVM: they cut the cost of each implementation.

## Recommendation

**B now, C reconsidered once the LLVM backend works.** B removes the implementation that is already behind from the critical path at no risk to the bootstrap, keeps D71's independent oracle, and needs only a written rule plus a gate that the Python backend still builds stage 1. Then [[MYLA-181]] and [[MYLA-185]] before [[MYLA-160]].

## Decision

*Open.* The owner's answer goes here and, once given, onto [[Project/Decisions]] as a numbered decision.

- [ ] Decided, and recorded on [[Project/Decisions]]
- [ ] The implementation tasks created or updated to match
