---
id: MYLA-263
title: "The calling-convention glue as IR: partial applications, adapters, frame constructors, composition"
type: improvement
status: review
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

- [x] Partial applications, adapters, frame constructors and composition built as IR (`lower.my`), translated like any function; the three copies and the retain walks deleted; the by-value panics gone
- [x] An environment's routines found the same way on every target (wasm's `__env_routines` table, or a word in the environment), not as data placed before code
- [x] The portable runtime routines in `std.rt` or as IR, leaving each `runtime_*.my` only what is machine-specific: start, system-call stubs, thread start and state, signals, the jumps into frames
- [x] Measured on the benchmarks and the self-compile on x86-64 (the hand-written versions jump in place; the IR versions must too)

## Done so far (2026-11-06)

- **Partial applications' functions and the `__fnval` adapters are IR** (`partial_ir` in [[selfhost/lower.my]], emitted through `emit_routine` like the environments' routines): the holes as parameters, the environment as `ENV_WORD`; a filled argument loaded from it (an aggregate's address taken), a parameter passed by value given `retain` and its words, one passed owned `retainval`; the call made in place of the function (`become`) when its words fit where they came, else called. An adapter is a partial application with every argument a hole. x86-64's `gen_partial_function`, `emit_byval_fnval_thunk`, `thunk_call` and `push_value_words`, aarch64's `gen_partial_function_a64` and wasm32's `gen_partial_function_wasm` and their adapters went (495 lines out, 151 in); only an async function's adapter (a jump to `__new`) stays each backend's.
- Found on the way: the inliner inlined the call a `become` makes in place of the function, leaving the `become` without a call (the verifier's "become after no call"); `inline_calls` now leaves that call alone.
- The x86-64 thunk checks pass as before (a partial's `become` is `jmp myla_hop`); the parity, partial and function-value programs pass natively, interpreted, and on aarch64 and wasm32 (`scripts/test-target.py`: 15 of 15 suites on each).
- Measured against the commit before: closures 151.1 → 141.1 million instructions (−6.6 %: the hand-written x86-64 thunk pushed every word and popped it back, the IR's loads them into their registers), its time within noise; the self-compile unchanged (+17 thousand of 5.1 billion).
- **Async functions' frame constructors and composition are IR** (`frame_new_ir` and `compose_ir` in [[selfhost/lower.my]]). `myla_<f>__new` allocates the frame, zeroes the words it doesn't write next (one store each in a frame with up to 24 such words, else `std.rt.zero_words`), stores the frame function's code word and each parameter (an aggregate copied from its address, a value owning heap memory retained, the environment given `__func_retain`). `__compose_call` calls the first function value with the argument and becomes the second with its result. x86-64's `emit_frame_new`, aarch64's `emit_frame_new_a64`, wasm32's `emit_frame_new_wasm` and the three hand-written `__compose_call`s went, with `spill_args` and `SPILLED_ENV`, which only they used.
- Measured (callgrind) on a program spawning 100,000 child tasks of an async function with a list, a struct and an int parameter: `step__new` 47 → 39 instructions per call, a lambda's `__new` 38 → 32 (x86-64 zeroed the whole frame with `rep stosq`; the first IR version's `zero_words` loop cost 68 per frame, so the stores went inline). Composition: `__compose_call` 17 → 21 instructions per call; the IR computes the two function values' addresses (`env + 8`, `env + 24`) instead of folding them into the call, and keeps the environment in a frame cell instead of `%rbx`. Composition is rare; folding a constant offset into an indirect call's operand would be the fix, in x86-64's instruction selection. The self-compile (the same input, the compiler of 8d3b0bd against this one): 6,042.28 → 6,042.54 million instructions (+0.004 %).
- Still hand-written per backend: an async function's `__fnval` adapter (a jump to its `__new`), the environments' deep-copy dispatch and the portable runtime routines.

## Done (2026-11-06, second part)

- **An environment's routines are a record, the same on every target.** Word 0 of a capturing lambda's environment points at `[drop, clone, deep]` in the data: `myla_<lifted>_env_routines`, or `__env_plain_routines` (std.rt's `free`, and a plain cell's copies) when no capture owns heap memory. The native runtimes kept the two copies in the words before the drop function's code, and wasm32 searched a table (`__env_routines`); both went. `__func_drop` calls the record's first word, `__dclone_env` and `__deep_env` its second and third (0 without tasks).
- **An async function's `__fnval` adapter is IR** (`async_fnval_ir`): the words as parameters and the environment, a call to its `__new`, made in place (`become`). It took an sret word too many on wasm32 ("takes 2 words, called with 3"); it takes the parameters' words now.
- **The portable runtime routines left the runtimes.** In std.rt: `equal_bytes`, `func_retain`, `func_drop`, `deep_env`, `dclone_env` (the last three call through a code address: the new intrinsic `call_code`, [[docs/Architecture/IR.md]]). As IR in the lowering: `__set_io_errno`, `__set_run_status`, `__set_run_stderr` (stores to the runtime's variables, `rt_addr`), `__argv`, `__environ` (globals), `__task_cancelled` without tasks (`false`). Gone from all three runtimes with them: `__str_eq`, `__sqrt`, `__f64_bits`, `__f64_from_bits` (unused since [[MYLA-264]]), `__argv_of` and the deep-copy dispatch (`emit_deep_runtime`). What is left in each `runtime_*.my` is machine-specific: start, system calls, signals, thread start and state, panics, entering frames, and x86-64's `__copy_bytes` (`rep movsb`). The three runtimes: 775 → 597, 621 → 487 and 520 → 474 lines; the backends and the runtimes 434 lines out, 88 in; the lowering, std.rt and the IR 137 in.
- Found on the way: `await __wait_either(...)` in a program without tasks failed natively (the lowering asked for a frame); it is called directly now (`waits_without_tasks`). x86-64's first `call_code` loaded the argument over the code address when the code was the temporary in `%rax`; the code goes to `%r11` first.
- Tests: the burn suite (1031, OK), the bootstrap fixed point, and `scripts/test-target.py` on aarch64 and wasm32 (16 of 16 suites each, `async_function_values` added). One aarch64 run of step 1 failed `test_children_run_in_parallel`, which compares CPU and wall time; it ran beside a full x86-64 run and passed twice alone.
- **Measured** (callgrind, x86-64, against 0f01b6a, the commit before this task's first part): closures 151.1 → 141.1 million instructions (−6.6 %, the first part's adapters); ackermann, binary_trees, fannkuch, fib, game_of_life, mandelbrot, n_body, quicksort, sieve and string_build unchanged; word_freq 138.6 → 141.5 (+2.1 %). The self-compile 5,107.8 → 5,129.8 million (+0.43 %; the inputs differ by std.rt's new routines, as neither compiler reads the other's library). Both increases are `equal_bytes`: 58.5 → 78.7 million instructions in the self-compile, its tail compared a byte at a time with one instruction more than the assembly did.
- **A byte load straight into its register.** x86-64 loaded a temporary's value into `%rax` and moved it to the temporary's register; `fold_load` loaded it there directly, but only for `movq` and `leaq`. It takes `movl`, `movzbl` and `movzwl` too (into the register's 32-bit name) and the sign-extending loads, so `equal_bytes`'s byte compare is two loads and a `cmp`, as in the assembly. Measured against 0f01b6a again (the self-compile with each commit's stage-2 compiler): closures −8.9 %, fannkuch −2.4 %, game_of_life −1.5 %, quicksort −0.7 %, binary_trees −0.5 %, string_build −0.2 %, the rest unchanged but word_freq +1.5 % (138.6 → 140.6 million); the self-compile 5,107.8 → 5,123.6 million (+0.31 %, it was +0.43 %). `equal_bytes` is 73.0 million instructions there against the assembly's 58.5: its loops match the assembly's, instruction for instruction, but each call copies its three arguments to other registers and tests the word loop's bound first, about six instructions more a call. That is the register allocator's choice (the arguments' registers are scratch registers in the body); a four-byte step before the byte loop made word_freq's one- to three-letter keys slower (+0.8 %), so it isn't there.

