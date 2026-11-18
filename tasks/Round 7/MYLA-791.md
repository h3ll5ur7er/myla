---
id: MYLA-791
title: "R7-2 Lowering and ANF: `m.contains(k())` (H4), async place writes (H5, M11), aarch64 --checked big functions (M3), runtime label names (M5)"
type: bug
status: review
priority: high
labels: [lowering, native, round-7]
---
Work package of [[Project/Review-2026-11-17]], lane "Lowering and ANF" (section 5). Files: `selfhost/lower.my`, `selfhost/anf.my`, `selfhost/ir_a64.my`. The reproducers are in the review's bundle (`repro-r6/`, with a README per area); each fix turns its reproducer into a test that fails before it. No owner's decision. New tasks it files take ids 809–816.

- [x] **H4** (high, old): `m.contains(k())` where `k()` changes the map: `true true true` interpreted, `true false true` natively. `Lower.map_contains` takes the map before the key; the fix (`self.operand(cg, m, [k])`) was validated in a copy. `repro-r6/native/uaf_map_contains_*.my`. Reopens [[MYLA-543]]
- [x] **H5** (high, old, every runner): in async code a mutating method on a place loses its write when the call has an `await` and the receiver isn't a name or `name[literal]` (`g[i + 1].push(await f())`); `Norm.callee` hoists the receiver into a copy; 26 of 36 forms differ from their sync twin. Each mutating form against its sync twin (`repro-r6/native/async_place_writes.my`). Filed: [[MYLA-809]]
- [x] **M11**: `xs[::await one()]` has length 1 interpreted and is an internal error at build. `repro-r6/native/async_slice_step_await.my`
- [x] **M3**: aarch64 `--checked`: a function over about 1 MiB (5,000 statements) doesn't assemble (`fixup value out of range: b.vs`). `repro-r6/native/a64_checked_big_function.py`. Reopens [[MYLA-551]]
- [x] **M5**: a function named `segv` (or `win_ctrl` on Windows) doesn't assemble: `.Lsegv_ret` is the runtime's label (D196). `repro-r6/interp-harness/fn_named_segv.my`. Filed: [[MYLA-810]]
- [x] D193's error timing: `g[5].put(val(7))` reports the missing element before running the argument natively, after it interpreted
- [x] [[MYLA-576]]'s follow-up: three concurrent actor callers still walk the ready ring to 8 MiB

## What changed

- **H4** ([[MYLA-543]]): `Lower.map_contains` keeps the map while a key that may replace it is computed (`operand`).
- **H5** ([[MYLA-809]]) and **M11**, in [[selfhost/anf.my]], so for both runners: a place (`is_place`: a variable, its fields and elements at any depth, any index but a slice) keeps its variable and fields when a method's call or an assignment awaits; only its indices are evaluated, left to right, into temporaries when something after them awaits (`Norm.place`, from `callee` and the assignment); an assignment whose target awaits computes its value first. An index's values are a slice's bounds and step and what a `^n` counts (`index_values`, `with_index_values`), never the `a:b` or the `^n` as a value.
- **M3** ([[MYLA-551]]): `a64_island` in [[selfhost/ir_a64.my]] (`CodeGen.cold_from` in [[selfhost/codegen.my]]).
- **M5** ([[MYLA-810]]): the runtime's `.Lsegv_ret` and `.Lwin_ctrl_ret` are `.Lsegv_done` and `.Lwin_ctrl_done` ([[selfhost/runtime_x86.my]], [[selfhost/runtime_a64.my]]), and a test keeps every other label out of a function's form.
- **D193's timing**: a `var self` method of a program or of std (`insert`, a builder's `append`) on a place whose last element may be missing, with an argument that does something (`quiet_operand` is false: a call, arithmetic, an index), takes the held path (`args_before_place`): the indices held, the elements before the last index read (`held_receiver`), the arguments, then the place. `g[5].put(val(7))` prints `value 7` before the error, as interpreted; `gg[5][0].put(val(7))` reports `gg[5]` first, as interpreted.
- **[[MYLA-576]]'s follow-up**: std.rt's `queue_took` (and its callers `exec_find`, `exec_steal`, which pass the worker) copies a queue of at most 256 frames whose oldest drifted 1,024 slots or more from its ring's start back to it.
- Found on the way: [[MYLA-811]], `g[^at(1)].push(9)` wrote `g[0]` natively (`held_index`, and `fixed_receiver`'s `^n`).

## Proposals

Accepted by the owner on 2026-11-18 as D268.

D193's corner, which D193 doesn't settle: when is a missing element of a method's receiver reported? Built (recommended): **as the interpreter does, the place's last element after the arguments, the elements before it when the place is taken** — what `myla run` already did, as a `var self` method reads its receiver's value after its arguments (MYLA-74), and as a builtin `push` already did on both runners; native code changes only where an argument does something an error would hide. Alternatives: (a) every element after the arguments, as an assignment `gg[5][0] = val(7)` does (the interpreter's `place_of` would settle nothing before the arguments: another lane's file); (b) every element before the arguments, native code's old order (the interpreter would check the last step when it takes the place). Proposed row: "A method call on a place takes its indices and keys, then the elements before its last index, then runs its arguments, then finds the element at the last index: a missing one is reported there, after the arguments (`g[5].put(val(7))` runs `val(7)` first)."

## Evidence

Each item's test failed at the base (`fe30af6`) and passes after; the details are in [[MYLA-543]] (H4), [[MYLA-809]] (H5, M11), [[MYLA-551]] (M3), [[MYLA-810]] (M5) and [[MYLA-811]].

- **H4**: parity program `contains_keeps_its_map_while_the_key_replaces_it`: natively `true false false false 1` before, `true false true false 50` after (the interpreter's).
- **H5, M11**: `tests/burn/test_async_place_writes.py` (new, 47 forms against their sync twin): 31 `DIFFERENT` and an `index out of bounds` interpreted before, and `can't be lowered to the IR` at build; 47 `same` after, interpreted and on x86-64, aarch64, wasm32 and Windows (Wine) (`scripts/test-target.py`). The review's `async_slice_step_await.my`: `3 1`, then an error, before; `3 3 3` after, on every runner.
- **M3**: `test_overflow.test_a_function_past_a_branchs_reach_builds_checked` (new): 5,000 checked statements build for aarch64 and print `5003`, then `integer overflow` at 4:11, as interpreted; before, `fixup value out of range b.vs`.
- **M5**: `test_label_names`, two new tests: `.Lsegv_ret` (and `.Lwin_ctrl_ret` on Windows) found before, none after; `segv` and `win_ctrl` as a program's functions build on x86-64, aarch64 and Windows and print `21`, `2` natively, under qemu and Wine.
- **D193's timing**: `test_compiler_parity.test_a_missing_receiver_element_is_reported_after_the_arguments` (new, four programs among `RUNTIME_ERRORS`): `index 5` alone natively before, `index 5`, `value 7` after, as interpreted; a key and a builder's element likewise; an inner element (`gg[5][0]`) still reported first on both runners. Of 16 forms tried by hand, 8 differed before, none after.
- **MYLA-576's follow-up**: `test_selfhost_codegen.test_actor_calls_from_outside_run_in_bounded_memory`, now with three callers at once: `7804 kB more resident` on one worker before, under 1 MiB after, natively, on aarch64 and on wasm32. The review's program (`MYLA_THREADS=1`, 10^6 calls): `after 3 callers: VmRSS 8280 kB` before, `104 kB` after (four workers: `184 kB`).
- **The cost**: the compiler's own `stage3.s` 29,400,321 → 29,409,234 bytes (+0.03 %, the held paths of D193's timing); its self-compile time best of 3 3.05 s (base) against 3.08 s (this branch), at load 3, within the machine's noise. A function smaller than 800 KB has the same aarch64 code as before.
- **Bootstrap**: byte-identical fixed point (29,409,234 bytes); `scripts/check-seed.sh` passes with `selfhost/embedded_std.my` committed. No seed change: nothing new to the seed.
- **Suites**: `scripts/test.sh fast` 1,029 tests OK; `test_compiler_parity`, `test_selfhost_codegen`, `test_selfhost_cases`, `test_generated_writes`, `test_generated_reads`, `test_error_corpus`, `test_test_native`, `test_selfhost_interp` (756 tests) OK but `test_children_run_in_parallel`, the known timing test, at load 20 (alone afterwards: OK); `scripts/test-target.py` aarch64-linux and wasm32-wasi with `test_compiler_parity`, `test_selfhost_codegen`, `test_generated_writes`, `test_label_names`, and the three targets with `test_async_place_writes` and `test_overflow`: all pass but the same timing test on aarch64 (alone: OK); the cases of `selfhost/anf.my` (21) and `selfhost/lower.my` (159). The full `scripts/test.sh` (1,800 tests, 1,774 s): only `test_children_run_in_parallel` fails (alone afterwards at load 6.5: OK).
