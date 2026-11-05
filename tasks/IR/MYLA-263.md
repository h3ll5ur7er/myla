---
id: MYLA-263
title: "The calling-convention glue as IR: partial applications, adapters, frame constructors, composition"
type: improvement
status: backlog
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
