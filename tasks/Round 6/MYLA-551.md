---
id: MYLA-551
title: "R9 `--checked` arithmetic: the traps out of line"
type: improvement
status: review
priority: medium
labels: [codegen, x86-64, aarch64, overflow, performance, round-6]
---
Work package R9 of [[Project/Review-2026-11-12]]. Files: `selfhost/ir_x86.my`, `selfhost/ir_a64.my`. Follows [[MYLA-430]], which is right on 26,155 boundary cases and brought `hot1` from 156 M to 34 M instructions (16 M plain).

By time, a checked int64 loop is still five times slower on x86-64 (user seconds at low load, `repro-r5/native/hot1.my`, `hot4.my`):

| Loop | Plain | Checked | Checked before MYLA-430 |
| --- | --- | --- | --- |
| `hot1` (`*`) | 0.12 | 0.62 | 1.03 |
| `hot4` (`+` and `-` only) | 0.12 | 0.60 to 0.69 | 0.63 to 0.67 |

Each check is a `jno` over an inline `call __trap_overflow`, five taken branches an iteration. The same loop written by hand with `jo` to a trap after the loop takes 0.22 s against 0.55 s (`cold.s` against `inl.s`).

- [x] `jo` (and aarch64's `b.vs`) to a cold block at the function's end, one per trap site or one per function with the position passed
- [x] No range check at run time for a constant shift amount (`mov $1; cmp $0x40; jb`)
- [x] Measured by time on hardware, not only by instructions; the row in Known issues updated

## What changed

- **x86-64** (`selfhost/ir_x86.my`): a checked build's `overflow` and `shift` checks (the 64-bit `fits` with its `check` and operation, `emit_checked_op` and `emit_fits_check`; a comparison and its `check`, `emit_compare_check`, for the narrow types, `-x`, the minimum by -1 and a shift's count; a lone `check`) are one `jcc` to a stub after the function's `ret` (`cold_trap`, `emit_cold_traps`): `jo`, `jc`, or the comparison's negated condition, where it was a `jno` over `leaq pos; call __trap_overflow`. The stub is the `leaq` of the position and the `call`, one per kind and position in the function; under -g it carries the position's `.loc`, so gdb's backtrace from the trap shows the line (checked: `myla_f (a=…) at ov.my:2`). The other traps (bounds, keys, division) are unchanged, and so is a plain build.
- **aarch64** (`selfhost/ir_a64.my`): `a64_checked` takes `fits`, `check` and the operation as one: `adds`/`subs` and `b.vs` (`b.cs`, `b.cc` unsigned), `mul` with `smulh`/`umulh` and `b.ne`, then the result stored, where it was the operation, `cset`, a store, a load, `cbnz` over the trap and the operation again; a comparison and its `check` are `cmp` and `b.<negated>`; a lone `check` is `cbz`. The stubs follow the `ret` (`a64_cold_trap`). It now counts the temporaries' uses (`use_counts`), to know a `check` is the only reader.
- **Constant shifts** (`selfhost/lower.my`, `checked_arith`, eight lines, outside this lane's files): a count that is a constant below the width checks nothing, on every target (wasm32 too). A constant count outside the range is a type error already, so no constant count reaches run time.
- `selfhost/codegen.my`: the two fields that hold a function's stubs (`cold_traps`, `cold_keys`).

### Per site, not per function (the choice the first box left open)

Measured by hand on this machine (the review's `hot1` loop, written as the compiler would; user seconds, best of 9): a stub per site, `jo .Ltrap_k` with the `leaq` in the stub, **0.22 s**; one stub per function with the position loaded before each `jo` (`leaq pos, %rsi; jo .Ltrap`), **0.32 s**, slower than the inline trap's 0.25 s, as the `leaq` is on the hot path. The per-site stub costs about the inline trap's bytes (a 6-byte `jo` when far, then 12 bytes of stub, against `jno` 2 + `leaq` 7 + `call` 5), and sites sharing a kind and position share a stub.

## Evidence

- **Failing first.** `test_overflow.test_the_traps_are_out_of_line` (new: the checked `main` of the `hot1` loop has its four `__trap_overflow` calls after `.Lret_main:` and no `__trap_shift`; it runs right interpreted and natively) failed at the base (`'__trap_shift' unexpectedly found in …jno .L296 / leaq .Lpos4(%rip), %rsi / call __trap_overflow…`); `test_64_bit_checks_take_the_flags` now asks for `jo`/`jc` (x86-64) and `b.vs`/`b.cc`/`b.ne` (aarch64), which the base doesn't emit. Both pass now, natively, on aarch64 (qemu) and wasm32 (Node). The messages and positions are byte-identical: `test_overflow` (46 tests, positions compared), `test_generated_widths`, `test_generated_extremes`, `test_formats_checked` pass natively and on aarch64, the first and third on wasm32 too.
- **Time, this machine's x86-64** (Intel Xeon @ 2.10 GHz, user seconds, best and median of 9, at load 0.8 to 1.6; the review's figures were on another machine):

| Loop (2·10^8 iterations) | Plain | Checked, base | Checked, now |
| --- | --- | --- | --- |
| `hot1` (`s += i * 3 - (i >> 1)`) | 0.11 / 0.11 | 0.25 / 0.26 | **0.215 / 0.22** |
| `hot4` (`s += i + 3 - (i >> 1)`) | 0.10 / 0.10 | 0.25 / 0.27 | **0.22 / 0.22** |

  The review's hand-written `cold.s` (out-of-line traps, no shift check) takes 0.22 s here and its `inl.s` 0.26 s: the compiler now matches the hand-written loop. What is left of the factor two is the four `jo` an iteration (a `jo` doesn't fuse with the `add` before it, and the branch ports are shared with the loop's own branch); fewer checks would need checks merged, not moved.
- **Instructions.** x86-64 (valgrind, `hot1s`/`hot4s`, 2·10^6 iterations): checked 34.0 M → **28.0 M** (17 → 14 an iteration), plain 16.0 M before and after. aarch64 under qemu-user, which counts instructions only (its time says nothing about hardware; one instruction a block, each block's execution logged, the difference of 10^4 and 2·10^4 iterations): `hot1` checked 90 → **57** an iteration, `hot4` 88 → **55**, plain 51 before and after.
- **The benchmarks** (13, checked, callgrind at `profile_size`, ASLR off, least of 3): the same instructions (geometric mean 0.9996 of the base's; most exactly 12 fewer; the rest move by up to ±0.6 % from run to run, as the plain builds do), as their checks are mostly `int32` ones, whose compare and jump are as many instructions as before; the not-taken jump replaces a taken one. By time (median of 5, a shared machine): ackermann 0.443 → 0.393 s, fib 0.130 → 0.107 s, fannkuch 0.416 → 0.375 s, game_of_life 1.256 → 1.158 s, the rest within noise.
- **A plain build is unchanged**: the 13 benchmarks' plain assembly is byte for byte the base compiler's; the base compiler (the seed, `build/stage0`) compiles the new compiler to exactly `stage3.s` (24,189,090 bytes, as before); self-compile time 1.85/1.90 s (base) against 1.89/1.97 s (now), best/median of 5, within the machine's noise.
- **A checked compiler**: built `--checked` by the base 2,261,116 bytes of text, now 2,265,518 (+0.19 %: far `jo` are 6 bytes); it compiles itself to `stage3.s` byte for byte, in 1.87/1.98 s against the base's 1.93/1.96 s (best/median of 5). The compiler built `--checked --target aarch64-linux` compiles, under qemu, `examples/maps.my` for both targets and the whole compiler for x86-64 to the x86-64 compiler's assembly byte for byte (33.9 s).
- **The parity programs, checked**: all 225 programs of `test_compiler_parity` built `--checked` print and exit as their plain build does, natively and on aarch64 (qemu): 0 differ.
- **Bootstrap**: byte-identical fixed point (24,189,090 bytes).
- **Suites**: `scripts/test.sh fast` (874 tests) OK; `test_generated_widths`, `test_generated_extremes`, `test_formats_checked`, `test_debug_info`, `test_test_native`, `test_compiler_parity`, `test_selfhost_codegen`, `test_aarch64`, `test_selfhost_cases`, `test_error_corpus` (770 tests) OK but `test_children_run_in_parallel`, the known timing test, at load 8 on 4 cores (cpu 1.15 s against wall 0.80 s); `scripts/test-target.py aarch64-linux` with `test_overflow`, `test_ir_contract`, `test_generated_widths`, `test_formats_checked`, `test_generated_extremes`, `test_error_corpus` and `wasm32-wasi` with `test_overflow`, `test_generated_widths`, `test_formats_checked` pass. The full `scripts/test.sh` (1,613 tests, 1,870 s): only `test_children_run_in_parallel` fails, which needs idle cores (alone afterwards at load 5 on 4 cores: cpu 1.12 s against wall 1.00 s); a plain build's code being byte for byte the base's, the change can't reach it.

