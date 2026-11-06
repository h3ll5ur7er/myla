---
id: MYLA-263
title: "The calling-convention glue as IR: partial applications, adapters, frame constructors, composition"
type: improvement
status: in-progress
priority: high
labels: [ir, backend, architecture]
---
Found by [[Project/Reflection-2026-11]]. These are written by hand once per backend, beside the IR:
- partial applications' functions;
- the function-value adapters (`__fnval`, by-value parameters included);
- async functions' frame constructors (`__new`, D90);
- the retain walks they use (re-implementations of `ownership.my`'s `Plain.act`);
- composition (`__compose_call`);
- the environments' deep-copy dispatch (`__deep_env`, `__dclone_env`);
- the function values' counts.

| Piece | x86-64 | aarch64 | wasm |
|---|---|---|---|
| Partial application | `codegen.my` | `ir_a64.my` | `ir_wasm.my` |
| `__fnval` with a by-value parameter | done | panics | panics |
| `__new` | `ir_x86.my` | `ir_a64.my` | `ir_wasm.my` |
| Executor entry points | `runtime_x86.my` | `runtime_a64.my` | `runtime_wasm.my` |

The IR has what they need (`ENV_WORD`, indirect calls, `become`, `frame`), and the environments' drop, clone and deep routines are IR functions already (`env_drop_ir`, `env_deep_ir`). The same is true of the portable routines each runtime repeats (`__str_eq`, `__equal_bytes`, `__copy_bytes`'s loop, `__func_retain`/`__func_drop`).

- [ ] Partial applications, adapters, frame constructors and composition built as IR (`lower.my`), translated like any function; the three copies and the retain walks deleted; the by-value panics gone
- [ ] An environment's routines found the same way on every target (wasm's `__env_routines` table, or a word in the environment), not as data placed before code
- [ ] The portable runtime routines in `std.rt` or as IR, leaving each `runtime_*.my` only what is machine-specific: start, system-call stubs, thread start and state, signals, the jumps into frames
- [ ] Measured on the benchmarks and the self-compile on x86-64 (the hand-written versions jump in place; the IR versions must too)

## Done so far (2026-11-06)

- **Partial applications' functions and the `__fnval` adapters are IR** (`partial_ir` in [[selfhost/lower.my]], emitted through `emit_routine` like the environments' routines): the holes as parameters, the environment as `ENV_WORD`; a filled argument loaded from it (an aggregate's address taken), a parameter passed by value given `retain` and its words, one passed owned `retainval`; the call made in place of the function (`become`) when its words fit where they came, else called. An adapter is a partial application with every argument a hole. x86-64's `gen_partial_function`, `emit_byval_fnval_thunk`, `thunk_call` and `push_value_words`, aarch64's `gen_partial_function_a64` and wasm32's `gen_partial_function_wasm` and their adapters went (495 lines out, 151 in); only an async function's adapter (a jump to `__new`) stays each backend's.
- Found on the way: the inliner inlined the call a `become` makes in place of the function, leaving the `become` without a call (the verifier's "become after no call"); `inline_calls` now leaves that call alone.
- The x86-64 thunk checks pass as before (a partial's `become` is `jmp myla_hop`); the parity, partial and function-value programs pass natively, interpreted, and on aarch64 and wasm32 (`scripts/test-target.py`: 15 of 15 suites on each).
- Measured against the commit before: closures 151.1 → 141.1 million instructions (−6.6 %: the hand-written x86-64 thunk pushed every word and popped it back, the IR's loads them into their registers), its time within noise; the self-compile unchanged (+17 thousand of 5.1 billion).
- Still hand-written per backend: async functions' frame constructors (`__new`), composition (`__compose_call`), the environments' deep-copy dispatch and the portable runtime routines.
