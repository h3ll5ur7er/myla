---
id: MYLA-176
title: float32 overflow crashes the interpreter where native code prints inf
type: bug
status: review
priority: medium
labels: [interpreter, floats]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). `fun main() { print(1e38 * 10.0) }`: `python3 myla.py run` dies with `OverflowError: float too large to pack with f format` in `round_float` ([[src/myla/types.py]]), native code prints `inf`. Any float32 operation whose float64 result is outside the float32 range does the same; the self-hosted interpreter should be checked too.

- [x] `round_float` returns the signed infinity instead of raising
- [x] A parity program (`1e38 * 10.0`, `-1e38 * 10.0`, a float32 literal that rounds to infinity) in `test_compiler_parity.py` and `tests/unit/test_floats.py`

## Evidence

- `1e38 * 10.0`, `-1e38 * 10.0` and a float32 annotated `3.5e38` print `inf`, `-inf`, `inf` in both interpreters and both backends (the interpreter raised `OverflowError` before); `3.4028235e38` stays the largest finite value. Parity program `float32_overflow_gives_infinity`, unit test `test_float32_overflow_gives_infinity`.
- Unit 622, integration 2, burn 826 (5 skipped) and the extension's 54 tests pass on commit 12f6e94; the bootstrap reaches its byte-identical fixed point (6,153,392 bytes).
