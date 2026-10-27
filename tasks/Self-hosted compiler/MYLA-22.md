---
id: MYLA-22
title: Self-hosted runtime never frees memory
type: bug
status: review
priority: high
labels: [selfhost, runtime, memory]
---
`__free` started with `ret`, so the size-class free-list code after it was dead ([[selfhost/codegen.my]]). It was disabled in "self-hosting part 5" (83cd293), probably to get past a use-after-free during bring-up.

Consequences were: every reference count and copy-on-write was bookkeeping only; memory was never reused (compiling the compiler peaked at 359 MB); and it hid real reference-counting bugs.

## What was wrong underneath

- **Closure environments** had no drop function: captures were stored without a retain, and `__func_drop` freed the cell without releasing them. With `free` on, a closure whose captured list's last other owner went away read freed memory (the probe programs trapped). Compositions (`f >> g`) and partial applications had the same layout problem; partial applications didn't retain filled list arguments either.
- **`?` released nothing** on failure: `gen_try` jumped straight to the epilogue instead of releasing the function's owners, so `STRESS_TRY_SRC` leaked 233 MB and the staged-value stress program ([[MYLA-4]]) ran out of the 4 GiB arena. The `?` operand's temporaries were not released on success either (`collect_expr_temps` had no `Try` case).
- **`__free` clobbered `%rsi`, `%r8`, `%rcx`**, which drop sequences keep live across calls that end in `__free` (the Python runtime's `__free` clobbers only `%rax`).
- **Capture slots** were sized as members (a recursive enum: an 8-byte pointer) but filled inline, so capturing a recursive-enum variable overran the next capture. The Python backend had the same bug (segfault); fixed in both.
- **`__list_clone`** was shallow, but only dead code (`eval_owned`, `clone_in_rax`) called it; removed. Copy-on-write uses the per-type `__clone_list_*` / `__clone_map_*` helpers, which retain what they share.

## Fix

In [[selfhost/codegen.my]]: `__free` is live and preserves every register but `%rax`; environments are `[drop fn][payload…]` like the Python backend's ([[Architecture/Native-backend]]), with per-lambda and per-partial `_env_drop` functions and a runtime `__compose_env_drop`; captures and filled arguments are retained; `__func_drop` tail-calls the drop function; the `?` failure path retains the escaping error, releases the operand's temporaries and calls `emit_return_drops`.

- [x] Find what broke when `free` was live: a temporary debug build poisoned every freed cell (`0xDEADBEEF…`); bootstrap, the self-hosted gates and every example under the self-hosted CLI stayed clean, but targeted probes of closures crashed. The final code was swept the same way: bootstrap fixed point, the seven self-hosted gates, `myla run` and `myla test` on every example (except `floats.my`, [[MYLA-29]]) all clean
- [x] Fix capture retain/drop and the other unsound paths, matching the Python backend's ownership rules
- [x] Remove the `ret`; the fixpoint still holds; peak memory of a self-compile drops: 359 MB → 163 MB, and it got faster (1.43 s → 1.32 s, best of 5)
- [x] Port the arena-reclaim stress tests to the self-hosted backend: `test_stress_programs_reclaim_memory` in `tests/burn/test_selfhost_codegen.py` runs all eleven with a 30 MB peak bound. Without `free` they need 34 MB to over 4 GiB (all eleven subtests fail), with it 8 to 18 MB
- [x] `?` releases the function's owners on its early return
- [x] Tests first: `closure_environments_own_their_captures` (parity and self-hosted; also caught the capture-slot overrun in the Python backend)

Cost: the compiler's assembly grew from 4.49 MB to 4.72 MB (+5%), mostly from the inline releases on each `?` failure path (the Python backend emits the same); sharing cleanup code between exits is a job for the mid-level IR ([[MYLA-67]]).
