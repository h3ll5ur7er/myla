---
id: MYLA-107
title: IR: the default, and the old path removed
type: feature
status: in-progress
priority: medium
labels: [ir, codegen, selfhost]
---
Step 5 of [[MYLA-67]] ([[Architecture/IR]]).

- [x] `--ir-stats` on the compiler, the language server and the CLI: every function through the IR
- [ ] `--ir` the default; the bootstrap's fixed point; the burn suite
- [ ] The old emission code deleted from `selfhost/codegen.my`; [[Architecture/Self-hosted-compiler]] and [[Architecture/Native-backend]] updated

## How (part 1: the default)

- `new_codegen` starts with `use_ir` on. `enable_ir` now only asks for the IR's text (`--emit-ir`); gen_main and `build/myla build` still accept `--ir`, which changes nothing. The verifier's fallback stays until the old path is deleted.
- A gate test checks that the compiler's output without flags is its output with `--ir`.

## Evidence (part 1)

- **Coverage:** `--ir-stats` reports none by the old path for the compiler (1,124 functions with its lambdas), the CLI (1,459), the language server (949), the interpreter (797) and the checker (508).
