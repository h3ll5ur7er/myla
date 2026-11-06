---
id: MYLA-298
title: The backends' duplicated helpers, the WASI numbering in one place, stale comments
type: chore
status: backlog
priority: low
labels: [aarch64, wasm, cleanup]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]). Seven helpers are byte-identical modulo prefix in [[selfhost/ir_a64.my]] and [[selfhost/ir_wasm.my]] (`reachable`, `wrapped`, `has`, `is_float`, `is_char`, `starts`, `after`), and `reachable` exists a third time as `reachable_blocks` in `ir_x86.my`; the `icond`/`fcond` tables are near-identical. The WASI import numbers exist twice (`W_*` in `lib/std/platform_wasm.my`, `wasi_calls()` in `selfhost/runtime_wasm.my`; a burn test now checks they agree). Stale: `ir_a64.my:11` cites D119 (replaced by D130); the comment above `emit_fnval_thunk_a64` describes a hand-written adapter; [[Architecture/Native-backend]]'s aarch64 section says the adapter is written there (it is IR since [[MYLA-263]]), and its "Runtime helpers" table names seventeen assembly symbols that no longer exist. `tools/wasm/myla.mjs` turns every exception into `runtime error: …` where `run.mjs` rethrows non-traps; `tools/wasm/node_fs.mjs` opens `"a"` for create-without-truncate (latent).

- [ ] One module for the shared helpers; the WASI numbers generated from one list; the comments and the two pages corrected; `myla.mjs` rethrows; `node_fs.mjs`'s open modes
