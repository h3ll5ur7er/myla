---
id: MYLA-298
title: The backends' duplicated helpers, the WASI numbering in one place, stale comments
type: chore
status: review
priority: low
labels: [aarch64, wasm, cleanup]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]). Seven helpers are byte-identical modulo prefix in [[selfhost/ir_a64.my]] and [[selfhost/ir_wasm.my]] (`reachable`, `wrapped`, `has`, `is_float`, `is_char`, `starts`, `after`), and `reachable` exists a third time as `reachable_blocks` in `ir_x86.my`; the `icond`/`fcond` tables are near-identical. The WASI import numbers exist twice (`W_*` in `lib/std/platform_wasm.my`, `wasi_calls()` in `selfhost/runtime_wasm.my`; a burn test now checks they agree). Stale: `ir_a64.my:11` cites D119 (replaced by D130); the comment above `emit_fnval_thunk_a64` describes a hand-written adapter; [[Architecture/Native-backend]]'s aarch64 section says the adapter is written there (it is IR since [[MYLA-263]]), and its "Runtime helpers" table names seventeen assembly symbols that no longer exist. `tools/wasm/myla.mjs` turns every exception into `runtime error: …` where `run.mjs` rethrows non-traps; `tools/wasm/node_fs.mjs` opens `"a"` for create-without-truncate (latent).

- [x] One module for the shared helpers; the WASI numbers generated from one list; the comments and the two pages corrected; `myla.mjs` rethrows; `node_fs.mjs`'s open modes

## Evidence

- [[selfhost/ir_util.my]] holds what the backends shared: `reachable_blocks` (x86-64's, now also aarch64's and wasm32's), `wrapped` (with both copies' `#test` cases), `int_in`, `is_float_type`, `is_char_type`. `a64_starts`/`wasm_starts` and `a64_after`/`wasm_after` had no caller and are gone. The `icond`/`fcond` tables stay per backend: they name each machine's condition codes. (`a64_retain_at`, `wasm_retain_at` and the unused `PartialJob` imports had already gone with the review's patches.)
- The WASI import numbers: kept in two places, held together by the burn test added with the review, rather than generated.
- Comments: `ir_a64.my`'s header cites D130 (Myla's own convention, C's at a C boundary); the comment on `emit_fnval_thunk_a64` says the adapters are IR. [[Architecture/Native-backend]]'s aarch64 section already said so; its "Runtime helpers" table is rewritten from the compiler's own assembly (std.rt's functions by their Myla names, the seventeen `.set` aliases, the per-type IR routines `__drop_list_`, `__clone_map_`, `__dropb_`, `__walkd_`, `__walkr_`, the runtime file's `_start`, `__panic` and ten traps).
- `tools/wasm/myla.mjs` rethrows what isn't a trap, as `run.mjs` does. `tools/wasm/node_fs.mjs` opens a file created without truncating `O_WRONLY | O_CREAT`, not `"a"`: writing `XY` to a file holding `abcdef` gives `XYcdef` (with `"a"`, `abcdefXY`).
- `tests.burn.test_wasm`, `test_aarch64` and `test_selfhost_codegen`: 95 tests, OK.
