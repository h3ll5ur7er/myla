---
id: MYLA-107
title: IR: the default, and the old path removed
type: feature
status: done
priority: medium
labels: [ir, codegen, selfhost]
---
Step 5 of [[MYLA-67]] ([[Architecture/IR]]).

- [x] `--ir-stats` on the compiler, the language server and the CLI: every function through the IR
- [x] `--ir` the default; the bootstrap's fixed point; the burn suite
- [x] The old emission code deleted from `selfhost/codegen.my`; [[Architecture/Self-hosted-compiler]] and [[Architecture/Native-backend]] updated

## How (part 1: the default)

- `new_codegen` starts with `use_ir` on. `enable_ir` now only asks for the IR's text (`--emit-ir`); gen_main and `build/myla build` still accept `--ir`, which changes nothing. The verifier's fallback stays until the old path is deleted.
- A gate test checks that the compiler's output without flags is its output with `--ir`.

## Evidence (part 1)

- **Coverage:** `--ir-stats` reports none by the old path for the compiler (1,124 functions with its lambdas), the CLI (1,459), the language server (949), the interpreter (797) and the checker (508).
- **Suites:** unit 567, integration 2, burn 730 (5 skipped), extension 54/54. The bootstrap reaches a byte-identical fixed point at 15,149,587 bytes: its compiler is now itself built through the IR, against 10,454,359 before (the unoptimised IR keeps every temporary in memory; [[MYLA-108]]). The CLI binary grows from 2.4 to 4.7 MB.

## How (part 2: the old path deleted)

- **Code generator:** `gen_any_function` and `gen_any_lambda` lower, verify (`take_ir`) and emit; a function that can't be lowered or doesn't verify is an internal error (a panic naming it), no longer a fallback. `gen_function` and `gen_lambda_function` are gone, with everything only they reached: 135 functions and 21 fields of `CodeGen`, about 2,800 lines (8,352 → 5,460 lines in `codegen.my`). A receiver-aware call graph over the self-hosted sources found them. What stays: the worklists, layouts, the retain/drop/copy-on-write walks, the shared instruction sequences, the thunks, the drop and clone helpers, DWARF and the runtime.
- **Flags:** `gen_main`'s `--ir` and `--ir-stats`, the CLI's `build --ir` and the IR bookkeeping (`use_ir`, `ir_done`, `ir_skipped`, `ir_stats`) are gone; `--emit-ir` stays (`keep_ir_text`).
- **Tests:** the `--ir` variants of the codegen gate and of the self-hosted debug-information tests, the coverage counts and `build --ir`'s test are gone, since every compile now goes through the IR; the IR text form's test moved to the gate itself.

## Evidence (part 2)

- **Output:** the trimmed compiler emits byte for byte what the IR-default build emitted, on `selfhost/gen_main.my` and `examples/methods.my`.
- **Tests:** the codegen gate, the debug-information tests and the CLI tests pass (50 tests).
- **Suites:** unit 567, integration 2, burn 704 (5 skipped), extension 54/54; the bootstrap reaches a byte-identical fixed point at 13,673,473 bytes.
- **Measured** (the compiler built by itself, compiling itself; best of three): the old path at 63b1621 took 3.80 s with a 128 MB peak, a 2.39 MB binary and 10.46 MB of assembly. Through the IR it takes 2.37 s with a 135 MB peak, a 3.36 MB binary and 13.67 MB of assembly. It is faster, but larger until [[MYLA-108]].
