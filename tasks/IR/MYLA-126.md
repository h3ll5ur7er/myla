---
id: MYLA-126
title: Tail calls
type: feature
status: done
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

- [x] Opportunistic tail calls in the backend (no owners alive, no more argument words); thunks and `__compose_call` jump (the adapter from the closure convention to a plain function, and `__compose_call`; partial-application thunks pass more words than they receive and wait for callee-pops)
- [x] Callee-pops calling convention; the owners nothing a tail call passes depends on dropped before the jump
- [x] With [[MYLA-127]]: the guarantee (tail position, marker, checker errors, interpreters): `become`, D87, [[MYLA-128]]. Partial-application thunks jump too since [[MYLA-130]]

## Step A: opportunistic tail calls

- **Which calls** (`tail_call_at` in [[selfhost/ir_x86.my]]): a `call` whose result the block's `ret` returns, followed only by `moved`, debug information, or the result stored into an owning slot that is then moved (a drop after it means something lives across the call); the callee takes no more argument words than the function was called with; no argument may hold an address in this frame (`frame_addresses`, a slot's address or one computed from it, worked out only for a function with a candidate); and not under `-g`, so backtraces keep their frames.
- **The jump** (`emit_tail_call`): the arguments are pushed as for a call, then popped into the function's own argument words (all pushed first, since an argument may be read from a word another overwrites), the saved registers restored (`restore_regs`), the frame left and `jmp myla_<callee>`. The caller pops the words it pushed, as always.
- **Thunks** ([[selfhost/codegen.my]]): `myla_<fn>__fnval` moves the arguments down over the environment word and jumps without a frame; `__compose_call` puts its second function's environment and argument into its own words and jumps.

Evidence:

- New test first: `test_calls_in_tail_position_reuse_the_frame` (ten million frames of a recursion, mutual recursion, a call through a function value and a composition; a struct passed by its address and a call followed by a drop stay calls) crashed with a stack overflow and passes.
- The compiler, which has 73 such calls, compiles itself in the same time (2,564.9 → 2,567.2 million instructions on the same input: finding the candidates costs about what the jumps save).
- Unit 595, integration 2, burn 742 (5 skipped) and the extension's 54 tests pass; the bootstrap reaches its byte-identical fixed point (5,177,196 bytes).

## Step B: the callee pops

- **Convention.** Every function compiled through the IR, the derived `eq` methods and the partial-application thunks pop the argument words their caller pushed (`ret $8n`, `ret_popping` in [[selfhost/codegen.my]]); calls no longer `addq` after themselves. The adapter from the closure convention moves the return address (and the result's address) up over the environment word and jumps, so the target's pop removes all its caller pushed. `__compose_call` jumps to its second function with its own two words.
- **Tail calls with any count** (`emit_tail_call`). The callee's m arguments go to the top of the n words the caller pushed and the return address right below them: popped into place when m ≤ n (the caller's `%rbp` restored from where it is moved), copied from the top down when m > n (they may overlap where they were pushed; the return address and the caller's `%rbp` are read into `%r10` and `%r11` first).
- **Drops before the jump** (`drops_after_free`). A drop after the call no longer rules a tail call out when no argument depends on the dropped slot: an argument read from it, through it, kept in it (a call's result in a statement's temporary), or read from a slot that owns nothing whatever was put into that slot depends on (a parameter's slot excepted); one taken from another block may depend on anything. Those drops are emitted before the jump.

Evidence:

- `test_calls_in_tail_position_reuse_the_frame` grew mutual recursion between functions of one and three arguments, ten million deep; `test_tail_calls_hand_over_owned_arguments` (with [[MYLA-127]]): a recursion threading a list a million deep (no copy of the list, constant stack), a string threaded through tail calls, an argument borrowed from a statement's temporary and one borrowed through a match's value, which stay calls. The second case of the latter was found by the bootstrap: a first version followed a borrowed slot no further and miscompiled the loader (a freed list read by `join`).
- The compiler has 167 tail jumps instead of 105; the stress programs, together with [[MYLA-127]]: 66,920.1 → 66,746.7 million instructions (−0.3%; partial application −5.8%, trait dispatch −4.4%, none worse).
- Unit 595, integration 2, burn 745 (5 skipped) and the extension's 54 tests pass; the bootstrap reaches its byte-identical fixed point (5,203,771 bytes).
