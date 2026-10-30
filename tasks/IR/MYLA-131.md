---
id: MYLA-131
title: Aggregate parameters by value (D88)
type: feature
status: done
priority: medium
labels: [codegen, selfhost, ownership, design]
---
Today a struct, tuple, enum or function value is passed as the address of the caller's storage, borrowed (both native backends, [[Architecture/Native-backend#calling-convention]]). Two consequences:

- **`become` can't pass an aggregate its function made** (D87): `become step(State.Running(n + 1))`, `become walk(Pos { x: p.x + 1, y: p.y })`. The storage would be in the frame the jump leaves. The workaround is to pass the fields as scalars. A state machine whose state is an enum is the case that hurts most.
- **Every read of a parameter's member goes through the pointer:** one more load, and a `let` of the whole value copies it out.

## What the compiler's own code passes

`selfhost/gen_main.my` has 2,501 parameters:

- 1,425 aggregates: 470 `var self` receivers (they stay pointers), 152 `self`, 443 structs, 341 enums, 17 function values, 2 tuples.
- Of the 955 that aren't `var self`, 920 own heap memory.
- By size: 111 have 8–16 bytes, 230 have 24–48, 264 have 56–64, and 348 are over 64 (the code generator's and the checker's state as `self`, ASTs).

So passing every aggregate by value would copy (and retain) a lot. Passing by value has to be chosen where it pays.

## Options

1. **By value where a `become` hands one over** (as D87 does for heap values):
   - The checker records the parameters a `become` passes a struct, tuple, enum or type-parameter value to, and drops the rule that such a value be (a part of) a parameter for a function or method callee.
   - Both backends pass those parameters by value: the aggregate's words go into the argument words, owned by the callee, which drops what they hold at its end. Every caller of that function copies, and retains what the copy holds; the adapters from the closure convention and partial applications do the same.
   - Only functions a `become` targets this way pay, and they were written for it.
   - The copy into the outgoing words is taken before the jump, so D87's rule against passing a part of `self` to a `var self` method could go too.
2. **Option 1, plus small aggregates by value everywhere** (at most two words, e.g. `Option<int>`, a two-field struct), chosen by the compiler as D86 chooses owned heap parameters, kept only where it measures faster. Without heap members it saves the pointer load. With them, the retain and drop may cost more than they save. That needs the measurement first.
3. **Leave it** (no D88): `become` keeps the restriction, documented with the workaround.

## Decision

D88: option 1. Function values keep the rule, and D87's rule against passing a part of `self` to a `var self` method goes.

- [x] D88 recorded, the Statements page and D87 updated
- [x] Checkers (Python and self-hosted): no "(a part of) a parameter" rule for an aggregate passed to a function or method; aggregates recorded in the handovers; the `var self` part rule removed; the error corpus adjusted
- [x] Self-hosted backend: by-value parameters (argument words of their size, owned slot, dropped at the end), callers copy and retain, the `__fnval` adapter and partial thunks copy, `become` passes them
- [x] Python backend: the same
- [x] Tests: parity programs (a state machine with an enum state, a struct built per step, a part of `self` to a `var self` method), deep runs in both native backends, the ordinary calls of such functions

## Questions besides (as discussed)

- **Function values:** their convention is fixed by their type, so the callee's choice can't change it. Calling through one keeps passing pointers, and `become` through one keeps the rule (recommended), unless every function value took aggregates by value, which would make every closure call copy.
- **Size:** option 1 copies whatever size the value has; a large struct costs its size per `become`. A limit would make the checker depend on layout, so none is recommended.
- **`var self`:** stays a pointer; `become` still calls a `var self` method only on `self`.
- **The Python backend** implements it too, as for D87.

## Evidence

- The parity program `become_passes_aggregates_by_value` (an enum state machine, a struct per step with and without heap members, a tuple, a type parameter, a part of `self` to a `var self` method, the same functions called directly, through a function value and a partial application) prints the same in both interpreters and both native backends; before D88 the checkers rejected its five `become`s.
- A million deep (`test_become_runs_a_million_deep`, `test_become_passes_aggregates_by_value`) both native backends, with and without `-g`, print what the self-hosted interpreter prints. A chain copying a struct with a growing string 50,000 times stays at a 10 MB peak (kept, the copies would take over 1 GiB).
- Compiling itself, the compiler emits the same code and runs 0.04% more instructions (2,777,231,244 → 2,778,384,004; a first version hashed function names for every argument and cost 0.23%).
- Unit 595, integration 2, burn 765 (5 skipped) and the extension's 54 tests pass; the bootstrap reaches its byte-identical fixed point (5,333,932 bytes).
- Found on the way: [[MYLA-132]] (an explicit call of a derived `eq` doesn't lower in the self-hosted backend).
