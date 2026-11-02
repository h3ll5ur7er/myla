---
id: MYLA-220
title: "`float` is float64"
type: feature
status: review
priority: medium
labels: [language, floats]
---
D102 ([[MYLA-203]]): the alias `float` means `float64`, and a float literal without a suffix is a `float64`; `float32` and `f32` stay.

- [x] The alias and the literal default in the checker(s)
- [x] Literal handling in the interpreter(s) and both backends (constants emitted as doubles)
- [x] The examples whose output changes, the error corpus, the parity programs
- [x] [[Language]] pages, the `myla` skill and `AGENTS.md` ("`float` is `float32`" goes)

Order: after [[MYLA-219]] this touches only the self-hosted toolchain (checker, interpreter, lowering) and the grammar; done before it, the Python checker and interpreter need it too. Using it in `selfhost/` itself needs a seed that knows it ([[MYLA-218]]).

## Evidence

- **The change.** `t_float()` in [[selfhost/checker.my]], the type of the alias and of an unsuffixed literal, is `float64`; the interpreter's canonical name for `float` follows. The interpreter, the lowering and the backend already handled both widths by type, so nothing else changed.
- **Test first.** `tests/burn/test_float64.py`: `0.1 + 0.2`, `1.0e40` in a `float`, a `float` parameter, `float32` and `f32` beside them, the 2^24 + 1 boundary for both widths, and `1.0 / 3.0`. The interpreter and native code print the same, a double's precision and range for the default and a single's for `float32`. Before the change the program didn't check (`half(3.0)` was a `float32`).
- **What changed with it.** No example's output changed, and nothing in the error corpus. The tests whose expectations embodied the old default:
  - `test_compiler_parity`: `float_arithmetic`'s unsuffixed `123.456` now prints `123.456`, not `123.456001`. Its output is pinned (`PINNED`), since the Python recording no longer holds.
  - `float32_overflow_gives_infinity` and unit program 45 test single-precision overflow, so they now name `float32`; their outputs are the recorded ones.
  - A new `float64_overflow_gives_infinity` covers the default.
  - The harness now compares every program's native output with the self-hosted interpreter (D101's reference) as well as with the recording or the pinned output.
  - `test_selfhost_checker`: snippet `unit_test_79` now reports `'int32' vs 'float64'`, pinned under `SUPERSEDED`.
  - `test_debug_info`: its programs test gdb's `float32` printer, so they name `float32`.
- **Docs.** [[Language/Types]], [[Language/Lexical-structure]], `AGENTS.md` and the myla skill (both copies). The burn suite passes, and the bootstrap reaches its fixed point with the new seed.

