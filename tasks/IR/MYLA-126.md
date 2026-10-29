---
id: MYLA-126
title: Tail calls
type: feature
status: in-progress
priority: low
labels: [ir, codegen, selfhost, design]
---
A call whose result is returned at once could reuse the caller's frame. Wanted for recursion as the functional style's loop, mutual recursion, state machines and interpreters written as functions, continuation-passing code and Swift-style async functions (D85's pressure points), and inside the backend for partial-application thunks and `__compose_call`.

Where we stand (discussed with the IR's stability, D85):

- **Already possible in the backend:** a `call` whose result goes straight to `ret`, with no owner dropped in between and no more argument words than the caller has, can write its arguments into the caller's argument words, restore the callee-saved registers and `leave; jmp`. Recursion over scalars qualifies (`count_down(n - 1, acc + n)`); an aggregate result passes the caller's result pointer on.
- **Calling convention:** the caller pops the arguments it pushed (`addq $8n, %rsp`), so a tail call to a function with more argument words would overwrite the caller's frame. Callee-pops (`ret $8n`, LLVM's `tailcc`) lifts that; it touches every epilogue, the four call instructions of `ir_x86.my`, the partial-application and function-value thunks, `__compose_call`, `_start`'s call of `main` and the struct `eq` calls. The Python backend is unaffected (each backend emits its own runtime).
- **Ownership:** parameters are borrowed, so a value the caller owns and passes must outlive the call (`let t = s + "x"; return label(n - 1, t)` drops `t` after the call). A guarantee needs owned parameters ([[MYLA-127]]); owners that aren't passed can be dropped before the jump when no argument borrows from them.
- **IR:** a `tailcall` terminator (and one through a function value), additive under D85: its text form, the verifier's rule (no owning slot holds a value, as for `ret`) and the backend.
- **A guarantee** also needs a defined tail position (`return f(…)`, a returned `match`'s arms), probably an explicit marker so the checker can reject what it can't guarantee, and trampolines in both interpreters, which recurse natively (Python's recursion limit). Tail-called frames vanish from backtraces.

- [ ] Opportunistic tail calls in the backend (no owners alive, no more argument words); thunks and `__compose_call` jump
- [ ] Callee-pops calling convention
- [ ] With [[MYLA-127]]: the guarantee (tail position, marker, checker errors, interpreters)
