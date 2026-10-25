---
id: MYLA-36
title: Rust native backend silently miscompiles common code
type: bug
status: done
priority: high
labels: [rust, codegen, parity]
---
The Cranelift backend in `rust/crates/myla-codegen/src/lib.rs` produces wrong results without any error. Each line was confirmed by building and running it (interpreter output → native output):

- [ ] `fun sq(x: int) -> int { x * x }` → 49 → **0**: `lower_block` drops a block's tail value, and the "fall-through safety: return zero" path returns 0
- [ ] `let v = if c { 1 } else { 2 }` → 1 → **0**: `if` and blocks always lower to `iconst 0`
- [ ] `print(0xff)`, `print(12u8)` → 255, 12 → **0, 0**: `myla_int_literal` trims trailing letters (eating hex digits), and the suffix parse falls back to `unwrap_or(0)`
- [ ] `2147483647 + 1` → -2147483648 → 2147483648: every integer is an I64; unsigned types use signed division, shifts and compares
- [ ] `false && side()` calls `side()`: `&&`/`||` lower to `band`/`bor`, with no short circuit
- [ ] `1.5f32 + 0.1f32` → `1.600000023841858` → `1.6`: `float32` is treated as `float64`
- [ ] `print(10.0)` → `10.0` → `1e+01`: the C runtime's shortest-`%g` formatter differs from the interpreter
- [ ] `1 / 0` → runtime error → SIGILL (exit 132)

## Done when

- [ ] Every item above is fixed or makes the build fail with a clear "not supported" error
- [ ] `tests/cli.rs` runs the native/interpreter differential over every example the backend accepts, not 3 hand-picked ones ([[MYLA-45]])

**Closed without a fix:** the Rust edition was removed from the repository ([[MYLA-70]]); its code is in git history (commit `043acb9`). See [[Architecture/Rust-edition]].
