---
id: MYLA-552
title: "R10 Check time and the seeds: under 5 ms, code that doesn't depend on what was read, labels per function"
type: improvement
status: review
priority: medium
labels: [loader, performance, seed, bootstrap, round-6]
---
Work package R10 of [[Project/Review-2026-11-12]]. Files: `selfhost/loader.my`, `selfhost/astcache.my`, `selfhost/lower.my` (`find_kept_params`), `scripts/update-seed.sh`, `scripts/bootstrap.sh`. Follows [[MYLA-359]], [[MYLA-412]], [[MYLA-431]] and [[MYLA-432]]; after [[MYLA-545]], which shares the loader.

Measured on `547339a` (before round 5 in brackets): `myla check` of a hello world 21.2 M instructions and 6.1 ms (39.4 M, 8.7 ms); with std.io 37.0 M and 9.8 ms (101 M, 22.6 ms); with std.http 146 M and 35 ms (394 M, 97 ms). `build/myla` grew from 5.13 to 6.23 MB and `selfhost/embedded_std.my` from 2.33 to 3.12 MB.

- [x] [[MYLA-359]]'s last box: a hello world under 5 ms, or the reason it stays at 6 — the reason, measured: a third of it is the kernel's page faults on 4.1 MB of fresh heap; huge pages for the heap would bring it under 5 ms, a decision for the runtime, filed as [[MYLA-608]] (see "Check time")
- [x] **The generated code depends on which library bodies were read**: `find_kept_params` votes over the loaded bodies, so 13 of 109 programs build different code lazily and eagerly (their output is equal). Make the vote independent of what was read
- [x] A switch that reads every body eagerly, as an oracle for the lazy load (none exists; the review built a compiler for it)
- [x] `scripts/update-seed.sh` checks every `lib/std` module whole: all are lazy now, and `test_std_modules` only covers modules with cases
- [x] **A seed update still costs the pack about 2.9 MB** (908 KB and 2,019 KB): the labels renumber, so 197,956 lines differ where 40,108 do with `.L` labels normalised. Number the labels per function
- [x] `seed_compile` rewrites `selfhost/embedded_std.my` in the working tree while it runs; write it elsewhere, or restore it

## What changed

1. **The vote** ([[selfhost/codegen.my]] `find_kept_params`, where it lives, not `lower.my`): a function of `std` whose body may wait and that nothing called (`Checker.unmarked_std`, which the code generator already held for [[MYLA-432]]) neither votes nor keeps. Such a body is read only by the oracle, so a program's lazy build is unchanged (the compiler's own assembly is the same bytes before and after the change); what changes is that reading it no longer changes the build.
2. **The oracle** ([[selfhost/loader.my]] `eager_bodies`, `read_every_body`, `read_now`): with `MYLA_EAGER_BODIES=1` the loader reads every body it left for later before the check, through the same `LazyBodies.parse` the checker reads one with (so with the same node ids: a lambda's name is made of one), into its declaration; the checker still checks them only once called (D179), and a body that doesn't read stays left, for the checker to report where it is called. An environment variable, so every tool that loads a program has it without a flag.
3. **`update-seed.sh`** checks all 59 files of `lib/std` on their own (`myla check <module> --stdlib lib`, 0.9 s), not the seven implicit modules.
4. **`seed_compile`** ([[scripts/host.sh]]) compiles a copy of `selfhost/` with the empty `embedded_std.my`, in a temporary directory beside a link to `lib/`, by the same relative paths (the positions of runtime errors carry them); the working tree isn't touched.
5. **Labels per function** ([[selfhost/codegen.my]] `label`, `begin_labels`, `epilogue_label`, `str_name`, `position_label`; [[selfhost/ir_x86.my]] `emit_ir_at`, `fconst_label`): a function's blocks and branches are `.L<name>_<n>`, its positions' records `.L<name>_p<n>`, numbered from 1 in each function under its mangled name (D196; first built under six base-36 digits of the name's FNV-1a hash), its epilogue `.L<name>_ret`; a string literal is `.Lstr` and seven digits of its text's hash, a float constant `.Lfc` and its bits in hex. `emit_ir_at` opens a function's labels for x86-64 and aarch64 and closes them after; wasm32's code has no labels of its own (its strings' names change too). The few labels outside a function (the runtime's) are still counted.

## Decisions (proposals)

- **The vote leaves out the bodies nothing called**, rather than counting every body of the library always (which needs every body read: the lazy load undone) or only the functions that will be compiled (which needs the call graph before lowering). A body nothing called is never compiled, so its calls had no business voting.
- **The oracle reads the bodies through the lazy reader**, rather than parsing the library whole: a whole parse numbers the nodes otherwise, and lambdas are named by node ids, so the assembly couldn't be compared byte for byte; whether the lazy parse is the whole parse is what `test_selfhost_parser`'s `test_bodies_read_later_are_the_same` and `test_std_cache` check. **An environment variable** (`MYLA_EAGER_BODIES`) rather than a flag of `gen_main` and `myla` and a field of `LoadOptions`: it is a test's switch, and reaches the language server and the REPL too.
- **Label names** (the owner's decision, D196, 2026-11-13): "whatever a human user can comprehend best", so a function's labels are named by its mangled name (`.Lmain_3`, `.Lmain_p1`, `.Lmain_ret`; the epilogue was `.Lret_main`), not by six digits of its name's hash as first built. The alternatives were the hash (3.8 % more seed on x86-64, against 17 % for the names), the function's ordinal (renumbers whenever a function is added before) or the assembler's numeric local labels (`1:`, `jmp 1f`: a jump's direction must be known when it is written, and the cold paths go after the function). Strings stay named by their text's hash rather than per function (a seed's 3,557 strings are used 7,021 times, shared between functions).
- **Under 5 ms**: not built here; [[MYLA-608]] proposes an opt-in to huge pages for the toolchain's heap (the runtime lane's).

## Check time

Callgrind (`MYLA_THREADS=1`, `build/myla check`, embedded library) at `dafd287` (the base, round 6's waves 1 and 2) and after:

| Program | base | after |
| --- | --- | --- |
| hello world, no import | 20,690,138 | 20,694,728 |
| hello world with std.io | 37,065,479 | 37,070,069 |
| hello world importing std.http | 146,649,441 | 146,654,031 |

(+4,590 instructions: the environment variable looked up once per load, 0.02 %.) CPU time, 200 runs a round, two rounds, the two alternating (the kernel counts it per tick, so only a sum over many runs means anything; the figures include about 1 ms of starting the process from the shell): base 6.50 and 6.60 ms per run, after 6.45 and 6.55.

Where a hello world's check goes (after): 20.7 M instructions, of which the loader 7.8 M (decoding the carried parse of the seven implicit modules 3.1 M, renaming their declarations 2.3 M, the table of bodies left 0.8 M) and the checker 12.8 M (`resolve_impls` registering their methods 5.0 M, the bodies checked 2.7 M, `collect_globals` 1.1 M, `synthesize_derives` 1.0 M); the leaves `__copy_bytes` 2.2 M (lists of large structs growing: `register_method`, `add_method`, `add_function`, `LazyTable.add_fun`, the renamer), the allocator 1.2 M, maps 2.9 M. And the kernel: the check touches 4.1 MB of fresh heap (2.3 MB by the end of loading, the rest checking: `/proc/<pid>/smaps` under gdb), a minor fault per 4 KB page, 1,109 faults (a program that does nothing: 13), about 2.1 ms of system time of the 6.3. That is why it stays near 6: the instructions alone take about 4 ms. With `madvise(MADV_HUGEPAGE)` on the heap's chunks (an experiment, not committed) the faults go to 90 and the check to 5.30 and 5.25 ms per run against 6.30 and 6.00 on the same measure, under 5 without the process's start; but every program with tasks then zeroes a 2 MiB page per worker at its start (0.2 ms, 0.40 → 0.60 ms for one that does nothing). Hence [[MYLA-608]]. The loader's own share left (decode and rename) would need the carried parse to be the renamed declarations, which the bodies read later still need the renamer for: not attempted.

## Evidence

- **The oracle and the vote, tests first**: `tests/burn/test_lazy_std.py`'s new `EagerOracle` builds the 227 parity programs on x86-64 and aarch64, and `selfhost/main.my`, with and without `MYLA_EAGER_BODIES=1` and compares the assembly. Before the vote's change it failed on both targets, `['packed_byte_lists.my'] != []` (the program's `bytes_of` built with a parameter owned or not, depending on whether the library's uncalled bodies voted); after, OK (9 tests, 37 s). Through a scratch driver also wasm32: 0 of 227 differ. The compiler's own assembly (`selfhost/main.my`) is the same bytes lazily before and after the change. The loader's cases 168/168 (`eager_bodies`, `read_every_body` new).
- **`update-seed.sh`'s check**: its loop, run on its own against a copy of `lib/` with an uncalled ill-typed function appended to `std/text.my`, stops with `FAIL: lib/std/text.my doesn't check as a whole`; the seven modules it checked before don't include std.text. On `lib/` it passes, 0.9 s.
- **`seed_compile`**: the old and the new one with the same compiler write the same bytes for both targets, and `selfhost/embedded_std.my`'s hash is the same before and after each (it is never written now).
- **Labels, test first**: `tests/burn/test_label_names.py` (new) builds a program, and the program with a branch, a string and an index more in one function: with the compiler before, 36 of the other 90 functions' text changed on x86-64 and 39 of 92 on aarch64; after, none (and each function's labels share one prefix, a string's label is its hash, `1.5` is `.Lfc3ff8000000000000`). New cases: `label_prefix`, `label_prefixes` (two names whose six digits agree get two prefixes, one emitted again its own), `str_name`, `begin_labels`, `fnv1a` ×2, `base36` ×2; `string_label`'s case follows. `myla test selfhost/codegen.my` 369/369, `ir_x86.my` 71/71, `ir_a64.my` 16/16, `runtime_wasm.my` 11/11.
- **The same code but for the names**: `selfhost/main.my`, `examples/hello.my` and `examples/maps.my` compiled by the compilers before and after, the labels renamed by their first appearance, are the same text on x86-64 and aarch64 (68,589 and 68,896 labels in the compiler's).
- **A small change's seed update, before and after**: the last change of wave 2 (`a9c8c8c..dafd287` in `selfhost/` and `lib/`: 34 lines in `term.my`, `codegen.my`, `interp.my`, `repl.my`), its seeds with and without it, each from a bootstrap of those sources with the labels as before and per function:

| | lines that differ | what the second costs a pack holding the first (`git gc --aggressive`) | the seed |
| --- | --- | --- | --- |
| x86-64, before | 5,146 | 35,571 bytes | 11,051,030 bytes |
| x86-64, after | 728 | 4,117 bytes | 11,469,329 bytes |
| aarch64, before | 8,001 | 66,051 bytes | 25,201,828 bytes |
| aarch64, after | 1,863 | 7,514 bytes | 25,791,979 bytes |

  What is left of the 728 lines is the code that changed (the list of runtime functions in `codegen.my`, its registers).
- **Seeds and the fixed point**: `scripts/bootstrap.sh` byte-identical (24,910,192 bytes); then the seeds `seed_compile` writes put in `bootstrap/` (locally, discarded after with `git checkout -- bootstrap/ selfhost/embedded_std.my`): `scripts/check-seed.sh` says both are the current compiler (from stage 0 of the new x86-64 seed), `scripts/bootstrap.sh` from it reaches the fixed point, and the aarch64 bootstrap from the new aarch64 seed under qemu (`MYLA_ARCH=aarch64 … MYLA_RUN=qemu-aarch64`) too (39,292,870 bytes).
- **Suites**: `tests.burn.test_float_registers`, `test_label_names`, `test_debug_info`, `test_selfhost_codegen`, `test_wasm`, `test_loop_overhead`, `test_register_args`, `test_aarch64`, `test_vscode_debugger` OK after the label regexes of four of them followed the names (`\.L\d+` → `\.L[0-9a-z]{6}_\d+`, `\.Lfc\d+` → the bits).
- **Before reporting**: `scripts/test.sh fast` 895 tests OK (3 skipped); `scripts/test.sh` (all) 1,651 tests OK (342 skipped), 26.5 min. `test_lazy_std` moves to the slow suites (the oracle builds 450 programs twice, 37 s).
