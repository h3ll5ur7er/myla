---
id: MYLA-791
title: "R7-2 Lowering and ANF: `m.contains(k())` (H4), async place writes (H5, M11), aarch64 --checked big functions (M3), runtime label names (M5)"
type: bug
status: todo
priority: high
labels: [lowering, native, round-7]
---
Work package of [[Project/Review-2026-11-17]], lane "Lowering and ANF" (section 5). Files: `selfhost/lower.my`, `selfhost/anf.my`, `selfhost/ir_a64.my`. The reproducers are in the review's bundle (`repro-r6/`, with a README per area); each fix turns its reproducer into a test that fails before it. No owner's decision. New tasks it files take ids 809–816.

- [ ] **H4** (high, old): `m.contains(k())` where `k()` changes the map: `true true true` interpreted, `true false true` natively. `Lower.map_contains` takes the map before the key; the fix (`self.operand(cg, m, [k])`) was validated in a copy. `repro-r6/native/uaf_map_contains_*.my`. Reopens [[MYLA-543]]
- [ ] **H5** (high, old, every runner): in async code a mutating method on a place loses its write when the call has an `await` and the receiver isn't a name or `name[literal]` (`g[i + 1].push(await f())`); `Norm.callee` hoists the receiver into a copy; 26 of 36 forms differ from their sync twin. Each mutating form against its sync twin (`repro-r6/native/async_place_writes.my`). File a task
- [ ] **M11**: `xs[::await one()]` has length 1 interpreted and is an internal error at build. `repro-r6/native/async_slice_step_await.my`
- [ ] **M3**: aarch64 `--checked`: a function over about 1 MiB (5,000 statements) doesn't assemble (`fixup value out of range: b.vs`). `repro-r6/native/a64_checked_big_function.py`. Reopens [[MYLA-551]]
- [ ] **M5**: a function named `segv` (or `win_ctrl` on Windows) doesn't assemble: `.Lsegv_ret` is the runtime's label (D196). `repro-r6/interp-harness/fn_named_segv.my`. File a task
- [ ] D193's error timing: `g[5].put(val(7))` reports the missing element before running the argument natively, after it interpreted
- [ ] [[MYLA-576]]'s follow-up: three concurrent actor callers still walk the ready ring to 8 MiB
