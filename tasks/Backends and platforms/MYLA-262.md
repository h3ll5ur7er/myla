---
id: MYLA-262
title: "A target description and one backend interface"
type: improvement
status: backlog
priority: high
labels: [backend, platforms, architecture]
---
Found by [[Project/Reflection-2026-11]]. The target is chosen today by:
- two booleans on `CodeGen` (`a64`, `wasm`), with three-way if-chains in `generate`;
- target strings compared in `driver.my`, `gen_main.my`, `main.my` and `loader.my`;
- a default `"x86_64-linux"` hard-coded in `main.my`.

`codegen.my` (4,626 lines) is also still partly the x86-64 backend. It holds the x86 instruction sequences `ir_x86.my` uses (`emit_int_op`, `emit_cast`, `emit_copy`, `emit_sb_build`, …), the x86 walks (`owned_walk`), `trap`, `tv` (`%fs:`), `REG_WORDS`, `arg_reg` and `spilled_word`, and debug information written against `%rbp`.

- [ ] A `Target` record:
  - architecture, operating system, object format;
  - word and pointer size (D122's description);
  - argument registers, the environment's register;
  - the symbol prefix (`_` on Mach-O);
  - how thread state is reached;
  - its assembler and linker commands;
  - its platform module.

  One list of targets; one `match` choosing the emitter. The default target is the host's.
- [ ] The x86-64 code out of `codegen.my` into `ir_x86.my` (or an `x86` module), so `codegen.my` is the target-neutral monomorphizer and pools; behaviour unchanged, the bootstrap's fixed point the proof
- [ ] A missing tool (clang, ld.lld, wasm-ld) named in the error, not left to `/usr/bin/env`; [[Getting started]] listing each target's tools
- [ ] How a non-x86-64 host bootstraps (D101: cross-compiling, or a seed of its own)
