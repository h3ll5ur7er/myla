---
id: MYLA-266
title: "Targets and capabilities in the language's specification"
type: chore
status: backlog
priority: high
labels: [language, docs, platforms, design]
---
Found by [[Project/Reflection-2026-11]]. The language and standard-library pages describe one native target, and several of their rules are machine facts.

**Machine facts written as language rules:**
- `become`'s six free words (System V's registers; Win64 has four);
- `exit`'s low 8 bits (POSIX);
- `IoError.Other` carrying Linux errnos;
- `ExitStatus.Signaled`;
- `PIPE_BUF` for whole lines;
- file modes 0644;
- `remove_dir_all` relying on Linux's EISDIR.

**Capabilities vary by target, and nothing says how.** wasm has no processes (`run` gives `Other(38)`), one worker (`MYLA_THREADS` is ignored), input that can't suspend, a stack depth that depends on the engine, at most 4 GiB of memory, and `PWD` as the working directory.

**Determinism gaps:**
- `to_bits(0.0 / 0.0)` gives 0xFFF8… on x86-64 and wasm, but 0x7FF8… on aarch64 (measured). wasm follows its host's CPU.
- `MIN / -1` and `MIN % -1` are stated only on [[Architecture/Native-backend]].
- Stack overflow has no row in the runtime-error table.

Decisions for the owner first:
- [ ] **NaNs:** canonical (every computed NaN made `0x7FF8000000000000` where its bits can be seen), or a computed NaN's sign and payload unspecified
- [ ] **Errors programs see:** `IoError` and `SpawnError` as causes (D113), including "unsupported", instead of raw errno numbers
- [ ] **`become`'s word limit:** one number for every target, or per target
- [ ] **Capabilities:** how a program learns what its target can do (code per target, [[MYLA-245]]; a query; errors only), and the minimum stack depth a program may rely on

Then the pages:
- [ ] A page `Language/Targets` (new): each target's capabilities (processes, workers, suspending input, file modes and links, paths and the working directory, exit codes, stack depth, memory, how traps are reported)
- [ ] [[Language/Expressions-and-operators]]: `MIN / -1` and `MIN % -1` (done with the reflection); NaNs once decided
- [ ] [[Language/Attributes-and-testing]]: stack overflow and an invalid `as char` in the runtime-error table
- [ ] [[Language/Statements]]: `become`'s rule stated in the language's terms
- [ ] [[Language/Standard-library]] and [[Language/Concurrency]]: what differs per target
