# Reflection 2026-11: what two new backends taught

In November 2026 Myla gained two backends beside x86-64 Linux: Linux on aarch64 ([[MYLA-163]]) and wasm32 on WASI with the checker and interpreter in a web page ([[MYLA-158]], D125, D126). This page steps back from the proofs of concept and asks what they taught about the IR, the platform interface and the language, and what to do before the next target. The [[Project/Review-2026-10]] did the same for the whole project a month earlier.

It rests on a reading of every task (open and done) and every wiki page, including [[Archive]], and on measurements and checks made for it, marked **[measured]**.

[TOC]

## In one paragraph

The architecture held. The IR, the ownership expansion before the backend and the runtime in Myla let each new target cost about 1,500 lines of translation and 500–600 of hand-written runtime, with no change to the front end, the lowering or the ownership rules. All four runners (the interpreter, x86-64, aarch64, wasm) agree byte for byte on every example. The compiler built for each target reproduces the x86-64 build's output, including its own fixed point (checked by hand; CI checks one example). What did not hold is the boundary around the IR:
- **Backend glue outside the IR:** the code around function values and frames is written three times.
- **Runtime calls by string:** 19 operations are recognised by name in each backend, and their meaning is unwritten.
- **Text as the interface:** the generated output is GAS/ELF text, which wasm had to rewrite.
- **Linux shapes in the platform interface:** errno numbers, records and mode bits that another system has to fake.
- **Machine facts written as language rules:** six register words, the low 8 bits of an exit code, Linux errno numbers, `PIPE_BUF`.

The next step is therefore not a fifth target. It is to specify, consolidate and verify, so that a fifth target costs translation only.

## What held

- **The IR boundary.** Neither backend needed a change to `lower.my`, `ownership.my`, `ir.my` or the verifier. `expand_ownership` hands every backend plain loads, counts and calls (`ownership.my`), and the per-type routines (drop, clone, walks, deep copies, derived equality, environments) are IR functions every backend translates for free.
- **The runtime in Myla** ([[MYLA-162]], D117). `std.rt` (2,398 lines) is shared. The hand-written remainder per target is `runtime_x86.my` (774 lines), `runtime_a64.my` (623) and `runtime_wasm.my` (519). **[measured]**
- **Determinism by construction.**
  - Float formatting is Myla code (`std.num`, `std.rt`), so it is byte-identical everywhere.
  - Maps iterate in insertion order (D105).
  - On one worker, scheduling follows a defined order (D110), which is wasm's only order.
  - The integer edge cases agree in all four runners: `MIN / -1` gives MIN, `MIN % -1` gives 0, for int32 and int64. **[measured]**
  - The compiler built for aarch64 (under qemu) and for wasm (under Node) compiled the compiler byte for byte as the x86-64 build does, for both targets. This was checked by hand once; the tests compile only `examples/maps.my`.
- **Simple first, measured.**
  - aarch64 keeps every temporary in a frame cell, and wasm uses a dispatch loop per function. Each was written in about a day.
  - Under Node, wasm runs fib 1.9×, binary trees 2.7× and string building 2.4× the x86-64 build's time. **[measured]**
  - aarch64 has no meaningful number: qemu's timing isn't hardware's.
- **Decisions the targets confirmed:**
  - D118: the standard library carried in memory is what makes a target without a file system work.
  - D120: widths map one to one onto `ldrb`/`strb` and `i32.load8_u`.
  - D59: saturating casts are native on aarch64 (`fcvtzs`) and wasm (`trunc_sat`).
  - D110: the one-worker order is a conformant order.
  - D124: the poller maps onto `poll_oneoff`.
  - D87: `become` is `return_call` on wasm.
- **Differential testing works:**
  - The aarch64 runs exposed a cancel race in `std.rt` that also existed on x86-64, in about 1 run of 60. It was fixed for every target.
  - The wasm runs exposed a crash in Node's own WASI.
  - Front-end-only features (D104's sugar) and std code in Myla (`std.math`'s fdlibm port) cost nothing per target.

## The IR

1. **Calling-convention glue lives beside the IR, three times.** Four pieces are written per backend: partial applications' functions, function-value adapters (`__fnval`), async frame constructors (`__new`), and retain walks re-implementing `Plain.act`. So are composition and the executor's entry points.

   | Piece | x86-64 | aarch64 | wasm |
   |---|---|---|---|
   | Partial application | `codegen.my` | `ir_a64.my` | `ir_wasm.my` |
   | `__fnval` (by-value parameters) | done | panics | panics |
   | `__new` | `ir_x86.my` | `ir_a64.my` | `ir_wasm.my` |
   | Retain walk | `codegen.retain` | `a64_retain_at` | `wasm_retain_at` |
   | Executor entry points | `runtime_x86.my` | `runtime_a64.my` | `runtime_wasm.my` |

   The IR already has what these need (`ENV_WORD`, indirect calls, `become`, `frame`). Built as IR, as the environments' routines already are, they would exist once and the two panics would go. → [[MYLA-263]]

2. **Runtime operations are strings with unwritten semantics.**
   - `Inst.Rt(name)` carries 19 operations that every backend recognises by name: `__cas64`, `__xchg64`, `__fetch_add64`, `__rc_inc`, `__rc_dec` and their atomic variants, `__cow:<clone>`, `__rt_addr:<sym>`, `__rt_waddr:`, `__run_frame`, `__sqrt`, `__f64_round`, `__rotl`, `__bsr64`, `__pause` and others. **[measured]**
   - Nothing states their memory ordering (x86-64's are full barriers by nature; aarch64 needs acquire/release) or their exact results.
   - `ir.my` still describes `rt` in x86-64 registers.
   - `RtPair` exists for one fallback that both new backends panic on.
   - → [[MYLA-264]]
3. **Each backend re-derives what an operation means.** Division by zero, `MIN / -1` (x86 faults, wasm traps, aarch64 wraps), shift masking for 8- and 16-bit types, wrapping, float→integer saturation, float32 rounding and float `%` (x87 `fprem` on x86-64, `std.rt`'s `fmod` elsewhere) are each written three times from the language pages. The IR page lists instructions but not their exact semantics. That page should be the contract a backend implements, with a conformance program per operation. The aarch64 test programs are a start. → [[MYLA-264]]
4. **Layout facts sit in the x86-64 backend or as constants.**
   - `FRAME_HEADER`, `slots_at` and `frame_size` are in `ir_x86.my`, and the other two backends import them from there.
   - `FRAME_*` sits in `lower.my`.
   - The list and map headers (`16 + i * stride`), 8-byte words and 16-byte function values (D49) are numbers in the code.
   - D122's target description doesn't exist. D126 keeps wasm on 8-byte words, so nothing breaks yet, but every target-dependent number is still scattered.
   - → [[MYLA-185]], [[MYLA-262]], [[MYLA-260]]
5. **Text is the interface between the backend and the platform.** `assemble_source` writes GAS/ELF text for every target: sections, `.quad` records, `.set` aliases, a fixed `.bss` list, `.note.GNU-stack`. x86-64 and aarch64 keep an environment's deep copies as data in front of its drop function. wasm has to re-parse the text: about 290 lines resolve aliases, rewrite pointer words and size every data label, and a table replaces the data next to code. Mach-O and COFF would hit the same assumptions. → [[MYLA-269]]
6. **D119 and the code disagree.** D119 says each target's C convention, the environment in a static-chain register or "an extra first parameter on wasm". What was built:
   - **wasm:** every signature is `(i64…) -> i64`, and the environment goes through a memory word, `myla_env`, which also stands in the way of threads on wasm.
   - **aarch64:** floats travel in x registers, and an aggregate result's address is the first word, not x8.
   - **x86-64:** floats are still in general-purpose registers.
   - **The checker:** `become`'s limit is a fixed six words (`checker.my`), which is x86-64's register count. Win64 has four.

   Either Myla keeps one internal convention per target and uses the C convention only at C boundaries ([[MYLA-166]], [[MYLA-241]]), or the backends move to D119 as written. That is a decision. → [[MYLA-272]]
7. **D85's pressure points have nearly all been hit.**
   - Slots in the frame: D90.
   - One thread: D92.
   - Sizes per target: D122 and D126.
   - Untyped addresses: D121.
   - One class of temporaries: D120, [[MYLA-249]].
   - Not SSA: D123.
   - Only "calls never end a block" still holds, because failures can't be caught (D97); it also spares wasm the exception-handling proposal.

   The IR page's "Stability" and "Decisions" sections still describe the October state. They now say so and point to this page.
8. **Register allocation is x86-64's alone.** `alloc_regs`, rematerialisation and live ranges (about 800 lines in `ir_x86.my`) are tied to x86-64's register file. aarch64 runs with no allocator at all. [[MYLA-257]] was planned as the allocator both share; it is now the main performance lever for every target but x86-64.

## The platform interface

1. **The seam worked; its contents speak Linux.**
   - `std.platform` let the aarch64 port be mostly numbers: `platform.my` and `platform_aarch64.my` differ in 136 diff lines, 63 of them outside the system-call table. **[measured]**
   - The interface's records are Linux's. wasm had to translate everything into them:
     - WASI's directory records are rewritten as `getdents64` records;
     - mode bits are invented from file types;
     - WASI's errnos become Linux numbers;
     - `getcwd` comes from `PWD`;
     - the poller emulates epoll on `poll_oneoff`;
     - `park` and `unpark` do nothing.
   - Each future target would translate into Linux shapes too, unless the interface speaks Myla's: a file kind, directory entries, an error cause, an "unsupported" answer. → [[MYLA-265]]
2. **Two near-copies of the Linux layer.** x86-64 has the same `*at`, `pipe2`, `dup3`, `ppoll` and `epoll_pwait` calls aarch64 uses. One Linux layer with a table of system-call numbers per architecture would do, plus a test that every platform module offers the same functions. → [[MYLA-265]]
3. **Picking code per target is a file substitution.** The loader's `for_target` replaces the text of `std/platform.my`. That was the smallest working form. A real way to choose declarations per target ([[MYLA-245]]) is now needed by std, by macOS and Windows, and by programs that want to know what their target can do.
4. **`__syscall` doubles as wasm's import dispatcher.** On wasm, `__syscall(n, args, …)` means "call WASI import number `n` with the words at `args`". It is a hand-made FFI that typed `extern` imports would replace, and it is the natural starting point for [[MYLA-166]].
5. **The hand-written runtime per target is larger than it needs to be.** Machine-specific in it:
   - the program's start;
   - system-call stubs;
   - thread start and thread-local state;
   - signal handling;
   - the jumps into frames.

   Portable, but written three times:
   - composition;
   - the environments' deep-copy dispatch;
   - `__str_eq`, `__equal_bytes`, `__copy_bytes`;
   - the function values' counts.

   → [[MYLA-263]], [[MYLA-264]]
6. **The host is part of the platform.**
   - Node 22's own WASI crashed when memory grew, so the project now carries a WASI shim of its own (`tools/wasm/`).
   - wasm-ld places the shadow stack above the static data, so a deep overflow of the shadow stack would overwrite data silently. **[measured]** The stack starts at 8,409,808 and grows down toward data at 1,024.
   - An engine trap under `run.mjs` reports `wasm trap: …` with exit 134, not `runtime error: stack overflow` with exit 1.
   - → [[MYLA-261]]
7. **Memory ordering was argued for x86-64 only.** The executor's protocols use `lock cmpxchg`, `xchg` and `lock or`, and their correctness was argued from x86-64's strong ordering: publish-then-check, the remote-free list, the actor lock word, `__exec_seq`. aarch64 uses `ldaxr`/`stlxr` loops, tested under qemu. qemu on an x86-64 host doesn't reorder memory, so a missing barrier could not show. → [[MYLA-267]]

## The language

1. **Machine facts written as language rules.**
   - `become` accepts six stack-free words: System V's registers.
   - `exit` keeps the low 8 bits: POSIX's wait status.
   - `IoError.Other` carries Linux errno numbers, which programs can print.
   - `ExitStatus.Signaled` is a Unix concept.
   - A line of output stays whole up to `PIPE_BUF`, Linux's 4 KiB.
   - Files are created 0644, and a removed directory is told apart by errno 21.
   - `std.fs.remove_dir_all` relies on Linux's unlink giving EISDIR for a directory; macOS gives EPERM.
2. **Capabilities differ per target, and the specification is silent.**
   - wasm has no processes: `run` gives `Other(38)`.
   - It has one worker: `MYLA_THREADS` is ignored.
   - Input can't suspend, so async reads block.
   - Its stack depth depends on the engine.
   - Its memory is at most 4 GiB and never shrinks.
   - Its working directory is `PWD`.

   No page says which targets have what, how a missing capability shows (an `Unsupported` cause?), or how a program can ask. → [[MYLA-266]]
3. **Determinism gaps found:**
   - **NaN bits.** `to_bits(0.0 / 0.0)` gives 0xFFF8… on x86-64 and wasm, but 0x7FF8… on aarch64. wasm follows its host's CPU, so it would differ again on an ARM host. **[measured]** `print` shows `nan` either way, but `std.math`'s `to_bits` and `copysign` expose the difference, against std.math's promise of bit-identical results. The language must either make NaNs canonical or say that a computed NaN's sign and payload are unspecified.
   - **Stack overflow** reports differently on wasm (above).
   - **Output order** differs between one worker and many. That is allowed (D110), but nothing warns that programs tested on one worker may meet another order natively.
4. **Integer semantics held, but are stated only implicitly.** `MIN / -1` and `MIN % -1` follow from "overflow wraps" and appear explicitly only on [[Architecture/Native-backend]]. Every new backend rediscovered them. They belong on [[Language/Expressions-and-operators]] (done with this page).
5. **The concurrency model held.** One worker is a conformant implementation, thanks to D110. On one worker the deep copies at task boundaries and the atomic counts are pure overhead. Whether an implementation may skip them per target is unrecorded.
6. **Prefer what costs nothing per target.** Sugar resolved in the front end, and library code in Myla over a few primitives (std.math's model), cost no backend work. A feature that needs new runtime machinery costs it per target.

## Documentation and the board

- The wiki still presented Myla as an x86-64 Linux language in many places:
  - Home, Architecture (pipeline, "no register allocator", "not built yet: other platforms");
  - Getting started (no `--target`);
  - Language ("D1–D116", one native backend);
  - Concurrency ("no sleep yet");
  - Standard library ("raw Linux system calls");
  - Known issues ("x86-64 Linux is the only target");
  - Roadmap;
  - Native backend (a "Strategy" from the Python backend, worker stacks "without a guard page").

  Those statements are corrected with this page.
- **Decisions.** Several rows are partly superseded without a mark: D2, D26 (shift error), D29, D67 ("no threads"), D82(2), D85(4)/(5), D86(5) and D87(3) (callee pops), D108 (LLVM), and D117(4) against D125(2) (clang and wasm-ld are LLVM's tools). Marking them is the owner's call. → [[MYLA-273]]
- **The board.**
  - 57 tasks wait in review; about 40 look finished.
  - MYLA-161 and MYLA-167 (LLVM) are abandoned.
  - Six tasks use types the board doesn't define (`design`, `test`).
  - The "Python toolchain" epic holds tasks that aren't Python's.
  - Closing or retyping is the owner's; the task changes made with this page are listed at the end.

## What to do before the next target

In this order, each a task:

1. **Fix what is unsafe or wrong now.** The wasm shadow stack below the data (`--stack-first`), and wasm's trap reports matching native ones ([[MYLA-261]]).
2. **Specify:**
   - the IR's operations and intrinsics as a contract, with conformance programs ([[MYLA-264]]);
   - the targets' capabilities, and the edge cases above, on the language pages ([[MYLA-266]]), which needs decisions on NaNs, error numbering and the `become` rule;
   - the convention question ([[MYLA-272]]).
3. **Consolidate:**
   - a target description instead of flags ([[MYLA-262]]);
   - the glue as IR ([[MYLA-263]]);
   - one layout module ([[MYLA-185]]);
   - the platform interface in Myla's terms, with one Linux layer ([[MYLA-265]]);
   - an object model instead of GAS text ([[MYLA-269]]).
4. **Verify:**
   - every suite per target, a full self-compile per target in CI, and a missing tool failing CI instead of skipping silently ([[MYLA-268]]);
   - memory ordering on arm64 hardware ([[MYLA-267]]);
   - benchmarks on the new targets ([[MYLA-270]]).
5. **Then performance and reach:** the shared register allocator ([[MYLA-257]]), the stackifier and binary writer for wasm ([[MYLA-158]]), macOS and Windows ([[MYLA-164]], [[MYLA-165]]).

## Decisions this needs from the owner

- **NaNs:** canonical, or a computed NaN's bits unspecified ([[MYLA-266]]).
- **Program-visible errors:** `IoError` and `SpawnError` as causes (D113's enum, [[MYLA-190]]) instead of raw errnos, including an "unsupported on this target" cause.
- **`become`'s word limit:** a language rule (a number of words for every target) or a per-target one; Win64 has four registers.
- **D119:** Myla's own convention per target with the C convention only at C boundaries, or D119 as written ([[MYLA-272]]).
- **Capabilities:** how a program learns what its target can do: code per target ([[MYLA-245]]), a query, or only errors.
- **Superseded decisions:** whether to mark the superseded parts on [[Project/Decisions]] ([[MYLA-273]]).
- **One worker:** whether an implementation may skip deep copies and atomic counts on one worker.

## Changes made with this page

**New tasks**, all in backlog:

| Task | What | Priority |
|---|---|---|
| [[MYLA-261]] | wasm: the shadow stack below the data, traps reported as native ones are | high (bug) |
| [[MYLA-262]] | A target description and one backend interface; `codegen.my` target-neutral | high |
| [[MYLA-263]] | The calling-convention glue as IR | high |
| [[MYLA-264]] | The IR as a contract: typed intrinsics, each operation's semantics, conformance programs | high |
| [[MYLA-265]] | The platform interface in Myla's terms, one Linux layer | high |
| [[MYLA-266]] | Targets and capabilities in the language's specification (needs decisions) | high |
| [[MYLA-267]] | The runtime's memory ordering on weakly ordered CPUs | high |
| [[MYLA-268]] | Every suite on every target; CI failing on missing tools | medium |
| [[MYLA-269]] | An object model instead of GAS text | medium |
| [[MYLA-270]] | Benchmarks on wasm and aarch64 hardware | medium |
| [[MYLA-271]] | Map remove without rebuilding the table (replaces [[MYLA-151]]) | low |
| [[MYLA-272]] | D119 against what the backends do (a decision) | medium |
| [[MYLA-273]] | Mark the superseded parts of decisions (the owner's call) | low |
| [[MYLA-274]] | A non-reentrant actor method kind (split off [[MYLA-171]]) | low |

**Updated tasks:**
- [[MYLA-160]] in review: the IR's open points (D120–D123, D126), the first backends and modularity ticked.
- [[MYLA-62]]: its "done when" items ticked, the plan after the first two targets added.
- [[MYLA-162]]: the reactor ticked.
- [[MYLA-185]]: current locations, a layout module for every backend, priority raised to medium.
- [[MYLA-181]]: retitled for the self-hosted side, tied to [[MYLA-264]].
- [[MYLA-164]] and [[MYLA-165]]: what macOS and Windows need beyond the Linux targets.
- [[MYLA-166]]: D119's state, wasm's `__syscall` as a first FFI.
- Notes added to [[MYLA-245]], [[MYLA-257]], [[MYLA-158]], [[MYLA-190]], [[MYLA-250]], [[MYLA-251]], [[MYLA-253]], [[MYLA-259]] and [[MYLA-151]].
- Last items ticked: [[MYLA-172]] (documented) and [[MYLA-184]] (the three places agree).

**Wiki pages corrected:** [[Home]], [[Architecture]], [[Architecture/IR]], [[Architecture/Native-backend]], [[Architecture/Self-hosted-compiler]], [[Getting started]], [[Language]], [[Language/Concurrency]], [[Language/Expressions-and-operators]], [[Language/Standard-library]], [[Development/Conventions]], [[Development/Debugging]], [[Development/Testing]], [[Project]], [[Project/Roadmap]], [[Project/Known-issues]], and the README.
