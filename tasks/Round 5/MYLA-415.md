---
id: MYLA-415
title: "P2 Lowering and native runtime copies"
type: bug
status: todo
priority: high
labels: [lowering, runtime, memory-safety, round-5]
---
Work package P2 of [[Project/Review-2026-11-09]] (wave A1), with round 4's additions from [[Project/Review-2026-11-10]]. Files: `selfhost/lower.my`, `selfhost/codegen*.my` where needed, the deep-copy and drop routines of `lib/std/rt.my` (P5 owns its notifier and timer section, in wave A2). Reopens [[MYLA-313]] and [[MYLA-367]]'s native half.

- [x] H2: an actor method that stores a list, map or string argument (`deep_param` passes a loaded slot as an address)
- [x] H3: `__deepb_` of a shared recursive enum handed to a child task, and a child returning one
- [x] H4: evaluate the key, index and argument before making the container unique: `m.remove(k())`, `m[k()] = v`, `xs[f()] = v`, `sb.append(…)`; audit every `Inst.Cow` site
- [x] M3: no same-cell shortcut for `==` on lists unless the element's `==` is built in and reflexive (NaN, a user `eq`)
- [x] M2, the native half: `method_instance` for the arithmetic traits (`impl<T: Add> Add for Box<T>` links)
- [x] M15: values nested through closures release within a bounded stack (wasm32 at 3,000 levels, aarch64 at 30,000); the deep copy between tasks doesn't recurse
- [x] H5: an instantiation depth limit for polymorphic recursion, a compile error instead of a build that never ends
- [x] D183: native runtime errors carry the interpreter's texts with their values (`map key 5 not found`, the index and length)
- [x] Z3 (with [[MYLA-416]]'s marker): `CodeGen.sig_of`'s fallback on `funcs[0]` goes; a file without `main` is a clean error for `myla build`; compiling an unread body is an internal error (that last part is [[MYLA-416]]'s marker: `sig_of` of an unknown name is an internal error here)
- [x] [[MYLA-384]]'s follow-up: the build hang of P2 (covered by H5)
- [x] Tests: key and index expressions with side effects on their container; actors storing every heap type; recursive enums across tasks; on x86-64 and aarch64 (and wasm32)

## What changed

- **H2** (`deep_param`): an owned argument that isn't held inline (a string, list or map passed owned, MYLA-127) is the cell itself in its slot; the deep copy got the cell as the address to read through. It gets the slot's address now.
- **H3**: a recursive enum held in a slot, a frame or an environment is its cell's *contents*, inline, as `__walkr_` reads it. `__deepw_<E>` read the tag as a box (`deep_walk_ir` now walks the contents for every enum), and a joined child's recursive-enum result was released by `drop T [p]`, which releases a member's box (`join_task` calls the contents walk, `TaskSlot.walk`).
- **H4** (with a fix found by `test_std_modules`: a local computed first in a match arm's expression belonged to the enclosing scope and was set on one path only; it is the statement's temporary now): a key, index or argument that may change or copy the container's variable (`settled_operand`: a method call on it or given it, a block, a lambda, an `await`; calls of functions, `len`, `contains`, `get`, `get_or` are settled) is computed before the container is made unique, with every index of its place, left to right (`fixed_receiver`, `held_operand`): in `place` (list and map elements), `map_set`, `map_remove`, `sb_append` and a `var self` method's arguments (`direct_call`). `push` already staged its value first. The audit of the `Inst.Cow` sites: `place` (two), `push_elem` (value staged first; its holder's place goes through `place`), `pop_elem` (no argument), `map_set`, `map_remove`, `sb_append`: all covered.
- **M3**: `__eq_list_<E>`'s same-cell shortcut only where `reflexive_eq(E)`: integers, `char`, `bool`, strings, and lists and tuples of such.
- **M2**: an arithmetic operator on a struct or enum goes through `method_instance`, as `==`, `<` and format holes did.
- **M15**: an environment owning a capture that may hold a function value (`CodeGen.reaches_func`) releases through a guarded `_env_drop`, a kind of `__drop_drain`'s (MYLA-389); every deep copy of a cell or an environment makes its members deep in a guarded routine of its own (`deep_members_ir`, `env_deep_members_ir`, `<name>_m`), whose deferred cell keeps its link in its count word, set back to 1 when it runs.
- **H5**: `call_target` refuses an instance whose type arguments are more than 64 types deep or have more than 4,096 parts, as a type error at the call (as a refused `become` is, MYLA-272); a lambda's refusal reached `take_ir` as an internal error before.
- **D183**: `list index 7 out of bounds (len 3)`, `string index 9 out of bounds (len 3)`, `string range 2..9 out of bounds (len 5)` through IR routines `__trap_lindex`, `__trap_sindex`, `__trap_range` that each backend's bounds check calls with the values it compared (the index extended from its type's width); `map key 'b' not found` and `invalid char: 55296 is not a Unicode scalar value` built in the IR on a cold path. std.rt words them (`list_index_text`, `str_index_text`, `range_text`, `char_text`, `key_text`, `key_bool_text`, `key_str_text`).
- **Z3**: `CodeGen.generate` refuses a program without its entry (`type error: no entry point: define '#main' or a function named 'main'`, exit 1, every target, `-g`, `--checked`); `sig_of` of a name no function has is an internal error. Four `#test` cases relied on the fallback.

No staging commit: the lowering calls std.rt's new functions only where the program has them (`has_func`), so the bootstrap builds against the old seed; until the integrator's seed commit the tools' built-in library lacks them and its programs keep the old texts.

## Evidence

Each reproducer of `review1/repro/native/` became a test that failed before (the compiler of 57fa3ef, `build/myla` before the change) and passes after, on x86-64, aarch64 (qemu) and wasm32 (Node):

| Item | Test | Before | After |
| --- | --- | --- | --- |
| H2 | parity `actors_store_every_heap_type` (str, list, map, builder, struct, tuple, option, enum, recursive enum, closure, nested list; temporaries and the caller's values changed after) | segfault (x86-64, aarch64) | the interpreter's output, three targets |
| H3 | parity `recursive_enums_across_tasks` (shared, returned, in a struct, an option, `task.all`, an actor) | segfault | same as the interpreter, three targets; 100,000 rounds of child tasks and actor calls: 11.3 MB max RSS at 10,000 and at 100,000 |
| H4 | parity `keys_that_change_their_container` (bug1 to bug4b, and a nested `g[h.bump()][h.bump()]`, `sb.append(s, a(), b())`, a `var self` method on a list and on a list element, the same in a match arm's expression) | wrong copies, `index out of bounds`, a segfault | same as the interpreter, three targets |
| M3 | parity `list_equal_to_itself` | `true` four times where the interpreter says `false`; `eq` not called | same |
| M2 | parity `arithmetic_operators_of_generic_impls` | `undefined reference to 'myla_Box.add'` | links, three targets |
| M15 | parity `values_nested_through_closures` (50,000 levels: closures, lists of closures, structs and enums holding them, a partial, a box and closures to a child) | `stack overflow` on aarch64 and wasm32 | same as the interpreter, three targets; a `Box { kids: [Box] }` a million deep to a child on x86-64 (0.5 s), 300,000 under qemu |
| H5 | `test_polymorphic_recursion_is_refused_where_it_is_built` (direct, doubling tuples through two functions, through a lambda; three targets) | the build never ended | a type error at the call in 0.08 s |
| D183 | `test_runtime_errors_carry_the_interpreters_values` (19 errors, interpreter against native; run with `MYLA_TEST_TARGET` aarch64-linux and wasm32-wasi too) | the texts without values | the interpreter's first two lines |
| Z3 | `test_a_file_without_main_is_a_clean_error_for_build` | exit 0, a program doing nothing | exit 1 with the message, five flag sets |

- Instruction counts (callgrind, each benchmark's `profile_size`, the same binary before and after): all thirteen identical after H2 to M15. The H4 evaluation order changes no benchmark's code (their assembly is byte-identical to 57fa3ef's), and of the 37 examples one call differs (`c.add(c.bump_get())` in `methods.my`, one store and load). D183 adds 0.07 % to word_freq and 0.05 % to map_remove (the key is kept across the map's lookup for the cold path); the other eleven are unchanged.
- `scripts/bootstrap.sh`: byte-identical fixed point after each commit.
- `build/myla test` of `selfhost/lower.my` (139), `codegen.my` (356), `ir_x86.my`, `ir_a64.my`, `ir_wasm.my`, `lib/std/rt.my`: all pass.
- Suites: `test_compiler_parity` and `test_concurrency_stress` (242 tests, OK), `test_native_runtime`, `test_error_corpus` (the seven corpus files whose `//~ native:` changed are pinned with `.stderr`), `test_slices`, `test_selfhost_codegen`, `test_time`: OK.
- `scripts/test-target.py aarch64-linux` and `wasm32-wasi` with `test_compiler_parity` and `test_native_runtime`: 2 of 2 suites pass on each.
- `scripts/test.sh fast`: 779 tests; it found the H4 bug in a match arm (std.yaml, fixed in 252e073), and otherwise only `test_embedded_std`, expected until the seed commit.
- `scripts/test.sh` (full, at 252e073): 1,410 tests, 336 skipped; failures: `test_embedded_std` (expected) and `test_wasm.test_one_worker_makes_no_deep_copies`, which needed the M15 routines among an environment's record routines (fixed in the next commit, then OK alone). `test_children_run_in_parallel` failed once under load and passes alone.

## Decisions this package leaves open (proposals)

1. **The native text of a missing struct, enum or list key.** Built: such keys give `map key not found` natively (the interpreter writes the key). Alternatives: per-type IR routines writing the interpreter's `py_repr` (structs `P { x: 1 }`, enums `E.V(…)`, lists), as the harness does in Myla source; or the key's hash. I recommend the routines when someone needs them ([[MYLA-441]]).
2. **The instantiation limits**, 64 types deep and 4,096 parts. Alternatives: Rust's recursion limit of 128 with a crate attribute to raise it; a flag. No program needs either; a flag can come with the first that does.
3. **`myla build` of a library says `type error: no entry point …`**, the interpreter's message under the kind every refused build uses. Alternative: a kind of its own (`error:`), which the driver would print.
4. **H4 computes only unsettled operands first.** The alternative, every key and index first into a local, is simpler to state but costs a store and a load (and a retain for a string key) on every write into a container.

## The owner's decision (2026-11-11)

Proposals 1, 2 and 4 stand as built (D189). Proposal 3 is decided otherwise (D188): `myla build` of a file without an entry point is `error: no entry point …`, an error of its own kind, not a type error; once Myla has an FFI it builds a library ([[MYLA-505]]). Changed with the decision: `CodeGen.generate`'s message and `loader.kind_of`.

## Review 2026-11-12

Reopened ([[Project/Review-2026-11-12]]): H3 isn't closed for one shape, which the pre-round-5 compiler shares and the parity program `recursive_enums_across_tasks` never builds. Everything else holds on five runners: 35 value shapes through about 60 hand-overs each at up to 3,000 rounds and 8 threads, 10^6 levels of nesting, 5,400 generated write statements.

- [ ] **A closure held in a variable that captures a recursive enum segfaults when it is copied to a child task, an actor or a channel** (exit 139 on x86-64, `--checked` and aarch64; the interpreter and wasm32 print 3). Also a partial `add(cap, _)`, a struct holding the closure, nested closures, `[f, f]` to `task.all`, `ch.send(f)`. A temporary closure works. Unverified: `Lower.deep_member` loads a boxed capture as a box, where an environment holds the enum's contents inline. Reproducer `repro-r5/native/segv_closure_captures_recursive_enum_to_task.my`:

  ```myla
  enum Lst { Nil, Cons(int, Lst) }

  fun total(l: Lst) -> int {
      return match l {
          Cons(n, rest) => n + total(rest)
          Nil => 0
      }
  }

  async fun run(f: () -> int) -> int { return f() }

  #main
  async fun main() {
      let cap = Lst.Cons(1, Lst.Cons(2, Lst.Nil))
      let f = () => total(cap)
      async let a = run(f)
      print(await a)
  }
  ```
- [ ] Closures, partials and structs holding a closure that capture a recursive enum, in the parity program
