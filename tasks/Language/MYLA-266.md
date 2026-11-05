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
- [x] A page [[Language/Targets]] (2026-11-05): each target's capabilities (processes, workers, suspending input, file modes and links, paths and the working directory, exit codes, stack depth, memory, how traps are reported)
- [ ] [[Language/Expressions-and-operators]]: `MIN / -1` and `MIN % -1` (done with the reflection); NaNs once decided
- [ ] [[Language/Attributes-and-testing]]: stack overflow and an invalid `as char` in the runtime-error table
- [ ] [[Language/Statements]]: `become`'s rule stated in the language's terms
- [ ] [[Language/Standard-library]] and [[Language/Concurrency]]: what differs per target

## Decided (2026-11-05)

The owner chose the recommendations:
- **D128:** NaNs are canonical where their bits can be seen.
- **D129:** errors are portable causes, with `Unsupported`.
- **D131:** `become` passes six words freely on every target.
- **D132:** capabilities show as errors at run time and as code per target at compile time.
- **D133:** one worker may skip the deep copies and atomic counts.

- [x] **NaNs:** D128
- [x] **Errors programs see:** D129 ([[MYLA-190]])
- [x] **`become`'s word limit:** D131
- [x] **Capabilities:** D132

Then the work:
- [x] D128 in `std.math`: `to_bits`, `copysign` and the other sign and payload readers see `0x7FF8000000000000` for every NaN. A test that `copysign(1.0, 0.0 / 0.0)` is `1` on every target (today -1 on x86-64, 1 on aarch64).
  - **How:** `to_bits` returns the canonical NaN for any NaN, and `copysign` reads `s`'s sign through it. Inside, std.math computes with `raw_bits` and `with_sign`, whose results reach a program only through `to_bits` again.
  - **Test:** `nan_bits` in `test_aarch64`'s programs, which `test_wasm` uses too, checks that the aarch64 and wasm builds print what the x86-64 build prints. Before the change the first two lines differed (x86-64: `18444492273895866368 9221120237041090560 …` and `-1 1 …`; aarch64: the other way round). After it, all lines agree.
  - **`#test` cases** on `to_bits` and `copysign`.
  - **Cost:** none. A program of 3 million `sin`, `exp` and `ln` calls runs 2,289,132,366 instructions before and after (callgrind). A first version that canonicalised inside std.math too was 34% slower.
- [ ] D133 on wasm32: plain counts for actor handles, no deep copies at task boundaries, measured
