---
id: MYLA-202
title: "Decision: keeping two interpreters, and which one retires first"
type: chore
status: review
priority: medium
labels: [decision, architecture, interpreter]
---
From the October 2026 review ([[Project/Review-2026-10]], §11.9). The self-hosted interpreter (`selfhost/interp.my`) is what users run (`build/myla run`, `test`, `repl`); the Python one is the semantics oracle the gates compare with. The review suggests that once the compiler stands alone (LLVM, a runtime in Myla), one of them is a duplicate to retire.

## Question

Do both interpreters stay, and if one goes, which one and when?

## Options

- **A. Keep both** (today). The Python interpreter is an independent oracle: most parity bugs of the last months were found by comparing the two. Cost: every semantic change twice.
- **B. Retire the self-hosted interpreter.** `run` and `test` compile and run natively (compiling a small program takes milliseconds). Loses the REPL as it is, and the in-browser interpreter the website plan needs ([[MYLA-158]], [[MYLA-159]]: the self-hosted toolchain compiled to wasm).
- **C. Retire the Python interpreter.** The self-hosted interpreter becomes the reference; the gates compare it with native code only. Loses the independent implementation; only possible once the Python toolchain is not needed for the bootstrap either ([[MYLA-201]], option C).

## Recommendation

**A for now; if one goes, it is the Python one, and only together with the rest of the Python toolchain.** The self-hosted interpreter has jobs no compiler replaces: the REPL, and Myla in the browser for the website. Revisit after the LLVM backend and the wasm target.

## Decision

**Follows from D101** ([[MYLA-201]]): the Python interpreter goes with the rest of the Python toolchain ([[MYLA-219]]), option C; the self-hosted interpreter stays (the REPL, Myla in the browser) and becomes the reference the gates compare native code with.

- [x] Decided, and recorded on [[Project/Decisions]]
- [x] The implementation tasks created or updated to match
