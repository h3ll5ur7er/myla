---
id: MYLA-29
title: Self-hosted compiler has no float support
type: feature
status: review
priority: medium
labels: [selfhost, floats]
---
`examples/floats.my` was the only example whose self-hosted output differed: every float line was dropped, and under the self-hosted `myla run` it segfaulted. The checker accepted float programs.

The root cause was in the AST, not only in codegen: `FloatLit(Option<str>)` kept the suffix but not the digits ([[selfhost/ast.my]]), so neither codegen nor [[selfhost/interp.my]] (which evaluated every float literal to `0.0`) could know the value.

## How

- **Literals**: `FloatLit(str, Option<str>)` keeps the lexeme. `selfhost/floatlit.my` turns it into the IEEE bits with integer arithmetic only (big integers, exact division, round half to even, subnormals, overflow to infinity), exactly as the Python toolchain does (`float(text)`, then single-precision rounding for a float32), so the compiler itself needs no float arithmetic.
- **Code generation** ([[selfhost/codegen.my]]): SSE2 arithmetic and comparisons (NaN unordered), negation by the sign bit, `%` through `__fmod`, conversions both ways (with the uint64 high-bit trick), float32 rounding after each operation, `print` and `format`/f-strings.
- **Runtime**: `__fmod`, `__float_to_str` and its helpers and tables, and `__char_to_str`, are embedded verbatim from the Python backend: `scripts/gen_selfhost_runtime.py` renders the Python code generator's text into a marked region of `codegen.my` (as a few string chunks, so it costs no code), and a unit test fails when the two drift apart.
- **Interpreter** ([[selfhost/interp.my]]): literal values (rebuilt exactly from the bits), float32 rounding, NaN-aware comparisons, float32 printed with 9 digits, uint64-to-float casts.

## Found on the way

The new tests found two bugs in the **Python** toolchain's float formatting, so in the reference implementation too:

- Dekker's split overflowed for operands above about 1.3e300 (the largest doubles, and tiny values multiplied by 10^300…10^308). Natively that printed garbage (`1.7976931348623157e308` as `241348968…`); the interpreter silently dropped the correction term, which made some values near 1e-288 fail to round-trip. `two_prod` now scales such an operand down by 2^64 and the other up (both exact).
- Below about 1e-292 the scaling collapsed a double-double into one double, so values such as `3.690843807971407e-302` didn't round-trip; the intermediate is now kept as a double-double.

Both fixed identically in `types.py` and the assembly runtime, and regenerated into the self-hosted compiler.

- [x] `FloatLit` carries the literal's value (the lexeme; its bits come from `floatlit.my`)
- [x] Codegen ports the Python float path: SSE2 arithmetic and comparisons, `as` conversions, `float32` rounding, `__fmod`, `__float_to_str` with the same power-of-ten tables ([[Architecture/Native-backend]])
- [x] `print`, `format` ([[MYLA-24]]) and the interpreter handle floats
- [x] `examples/floats.my` matches the oracle under stage3, and under the stage-3-built `myla run` and `myla test`
- [x] Tests: `tests/burn/test_selfhost_floatlit.py` (845 literals bit-identical to Python; a mutant without ties-to-even fails it), the parity program `floats_in_depth` (both backends), `floats.my` back in the self-hosted codegen and interpreter gates, `tests/unit/test_floats.py` round-trip over the whole double range and correctly rounded digits at the top of the range (both failed before the formatting fixes), and the runtime-sync unit test
- [x] Bootstrap fixed point holds (4,963,698 bytes; about 160 KB of that growth is the runtime's text kept as string data, which the self-hosted compiler writes as `.byte` lists)

Not covered then: integer literals of 2^63 and above in the self-hosted lexer, since fixed ([[MYLA-73]]).
