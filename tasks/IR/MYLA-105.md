---
id: MYLA-105
title: IR: heap values, ownership and the verifier
type: feature
status: review
priority: high
labels: [ir, codegen, selfhost]
---
Step 3 of [[MYLA-67]] ([[Architecture/IR]]): strings, lists, maps and builders through the IR, with every ownership rule of [[Architecture/Native-backend#heap-and-reference-counting]] as explicit `retain`/`drop`/`cow`.

- [x] Part 1: strings and aggregates holding them (literals, consts, concatenation, `==`/`!=`, `len`, `print`, fields and payloads, string patterns); owners, owned temporaries, `return`/`break`/`continue` drops, staged assignments, match copies; `retain`/`drop`/`rt`/`init`
- [x] The verifier, run on every function the gates compile; a test with deliberately broken IR for each rule
- [x] A string stress program (some 50 MB of churn) with `--ir`
- [x] Part 2: lists: literals, indexing (with the string's byte index) and its bounds trap, `push`/`pop`/`len`, staged stores into elements and copy-on-write, `for` over a list
- [x] Part 3: maps, builders, `chars`, `format` and f-strings, the remaining builtins
- [x] The list and map stress tests with `--ir`
- [x] Part 4: recursive enums (boxed members)

## How (part 1)

- **IR:** `rt` (runtime helpers in the calling registers), `retain T %v` and `retain T [%p]`, `drop T $slot` and `drop T [%p]`, `init $slot`; `Slot.owns`. Retains and member drops use the old path's walks (`retain` through `%r8`, `walk_member` through `%rbx`), so the helpers called are the same.
- **Lowering:** an owner stack parallel to the scopes and a temporary stack per statement or condition (`begin_temps`/`end_temps`). `return` drops every temporary and owner, `break`/`continue` those of the scopes the loop opened. `owned_value` puts a new reference into an owning temporary slot. Every rule is listed on [[Architecture/IR#lowering-ownership]].
- **Verifier:** `verify` in `selfhost/ir.my`, a forward dataflow over owning slots (live or not) on the reachable blocks. `gen_any_function` runs it; a rejection falls back with `IR verifier: …`, and the IR gate asserts none occurs on the corpus.

## Evidence (part 1)

- **Parity:** the `strings_through_the_ir` parity program and `STRESS_STR_OWNERSHIP_SRC` (both in the corpus of both backends and both self-hosted gates) give the interpreter's output through the IR, with the same peak memory as the old path (11 MB). The gates pass with `--ir`.
- **Verifier:** its tests cover a leak at `ret`, a double drop, a drop of a slot that owns nothing, a store over a live value, and paths that disagree.
- **Mutation:** an `end_temps` that doesn't drop makes the IR gate fail (`main: IR verifier: L14: $1 (__enum) still holds a value at ret`).
- **Coverage:** examples 94 → 122 of 227, the compiler 18 → 64 of 1,072. No function of the examples or the compiler is rejected by the verifier.

## How (part 2)

- **IR:** `elem` (an element's or byte's address, bounds-checked; split out of the old path's `gen_elem_addr` as `emit_elem_addr`, which both use), `load8`, `cow` (the old `cow_unique`), `append` and `pop` (the middle of the old `gen_push` and `gen_pop`).
- **Lowering:**
  - list literals: a `__alloc`'d cell, elements stored with retains;
  - element reads, borrowed;
  - element places for writes: copy-on-write of every list on the path, the index after the `cow`, as the old path;
  - `push` (value staged first), `pop` (the element moved out to the statement), `len`;
  - `for` over a list (a loop reference registered as an owner, so `return` drops it and `break` doesn't).
- **Place types:** `place_type` knows list elements.
- **Member addresses:** `offset` always makes a temporary of its own, even at offset 0, so a copy into a member isn't read as a store into the whole slot. The verifier found this in `Lexer.emit` and `cv_equal`, where a struct literal's first member is an aggregate.

## Evidence (part 2)

- **Parity:** the `lists_through_the_ir` parity program (push/pop through `var self` and into nested lists, writes at any depth, copies that must not see later writes, an early return from a `for`, string bytes): all 5 functions through the IR, the interpreter's output, peak 11 MB as the old path. The gates pass with `--ir`, the list stress program included.
- **Mutation:** element writes without `cow` fail the IR gate on `lists_through_the_ir`.
- **Coverage:** examples 122 → 145 of 227, the compiler 64 → 178 of 1,079; the verifier rejects none.

## How (part 3)

- **IR:** `rt` with two results (`__map_set_slot`'s slot and "the key was there" flag), `check` (a trap when a value is 0), `sbappend` (with and without a checked range), `sbappendbyte`, `sbbuild`, `mapremove`, `global`, `exit`, and the `panic` terminator. Map removal, the builder's range check and `build` were split out of the old path as `emit_map_remove`, `emit_sb_range` and `emit_sb_build`; its assembly stays byte-identical.
- **Lowering:**
  - map literals, reads (`check … key`), inserts and overwrites (releasing the replaced value), places inside values (`m[k].f = v`, `push(m[k], x)`), `contains`, `remove`, `keys`, `len`, and `for` over a map's keys;
  - `StringBuilder`, `append` (with a range), `append_byte`, `build`, `chars`, `format` and f-strings;
  - `assert`, `panic`, `unreachable` and the I/O intrinsics;
  - a partial application falls back.
- **Place types:** `place_type` knows map values.

## Evidence (part 3)

- **Parity:**
  - the `maps_and_builders_through_the_ir` parity program covers every map and builder operation, copies that must not see later writes, and f-strings of each printable type: all 5 functions (`get`'s instance too) go through the IR and print the interpreter's output;
  - the `io_through_the_ir` module project uses std.fs, std.process and std.io, and no function falls back for a builtin;
  - every runtime-error program goes through the IR entirely and still reports the interpreter's position.
- **Stress:** every stress program gives the same output with `--ir`, at the old path's peak (11 MB). The map, map-remove, map-overwrite and builder programs now run entirely through the IR.
- **Mutation:** a `map_put` that doesn't release the replaced value fails the overwrite stress program (305 MB, the limit is 30).
- **Old path:** byte-identical on `selfhost/gen_main.my` and `examples/methods.my`.
- **Self-compile:** the compiler built with `--ir` emits the same assembly for itself as the normal build (10,111,730 bytes).
- **Coverage:** examples go from 145 to 184 of 227 functions, the compiler from 178 to 273 of 1,099. The verifier rejects none.

## How (part 4)

- **Lowering:**
  - boxed members: `unbox` (load the box's pointer) where a member of a recursive enum is read as an aggregate (fields, tuple elements, list elements, map values) and in sub-patterns;
  - `box` (a new cell holding a retained copy) where one is stored: member stores, list literals, `push`, map inserts, and assignments to a member, which release the old box;
  - `pop` copies the value out of the box with its own references, then releases the box; a `for` over such a list copies each value out of its box.
- **Lowerable types:** `lowerable` is now a shallow check against `CodeGen.ir_blocked`, the structs and enums whose declarations hold a function value, worked out once per program (`blocked_types`). The recursive walk it replaced made `--ir` on the compiler take 61 s instead of 1.8 s.

## Evidence (part 4)

- **Parity:** the `recursive_enums_through_the_ir` program prints the interpreter's output with all 5 functions through the IR. It covers recursion over a tree, nested patterns through boxes, member, element and map-value writes, `push`/`pop`/`for`, copies that keep their trees, and `Option<Tree>`.
- **Stress:** `STRESS_BOXED_MEMBERS_SRC` replaces trees in a field, a list element and a map value, and pushes and pops them, 30,000 times. It runs in both backends' suites and the gates: 11 MB with `--ir`, as on the old path. `STRESS_SRC` (354 million recursive-enum allocations) now goes entirely through the IR, also at 11 MB.
- **Mutation:** a member assignment that doesn't release the old box takes the boxed stress program to 215 MB (the limit is 30).
- **Old path:** byte-identical on `selfhost/gen_main.my` and `examples/methods.my`.
- **Self-compile:** with 1,007 of its 1,108 functions through the IR, the compiler built with `--ir` emits the same assembly as the normal build, both with `--ir` and without.
- **Coverage:** examples go from 184 to 198 of 227 functions, the compiler from 273 to 1,007 of 1,108. The verifier rejects none.
