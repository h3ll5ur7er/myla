---
id: MYLA-176
title: float32 overflow crashes the interpreter where native code prints inf
type: bug
status: todo
priority: medium
labels: [interpreter, floats]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). `fun main() { print(1e38 * 10.0) }`: `python3 myla.py run` dies with `OverflowError: float too large to pack with f format` in `round_float` ([[src/myla/types.py]]), native code prints `inf`. Any float32 operation whose float64 result is outside the float32 range does the same; the self-hosted interpreter should be checked too.

- [ ] `round_float` returns the signed infinity instead of raising
- [ ] A parity program (`1e38 * 10.0`, `-1e38 * 10.0`, a float32 literal that rounds to infinity) in `test_compiler_parity.py` and `tests/unit/test_floats.py`
