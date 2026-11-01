---
id: MYLA-74
title: Self-hosted interpreter copies containers on every update
type: improvement
status: done
priority: low
labels: [selfhost, interpreter, performance]
---
Split out of [[MYLA-32]]. [[selfhost/interp.my]] represents lists, maps, structs and scopes as immutable `Value`s, so every update rebuilds the container (`set_index`, `list_push`, `write_steps`) and each scope lookup copies a frame: an assignment or `push` costs O(n), and a loop that grows a list is quadratic.

## Measurement

Appending `n` integers with `push` in a loop (`myla run`, Python interpreter vs the natively built self-hosted interpreter):

| n | Python | self-hosted |
| --- | --- | --- |
| 5,000 | 0.15 s | 0.23 s |
| 10,000 | 0.16 s | 3.8 s |
| 20,000 | 0.18 s | 5.7 s |

## Ideas

- Keep containers in a store indexed by handle (a list of cells the interpreter owns), so a value holds a handle and an update writes the cell in place; copy-on-write by reference count where value semantics require a copy.
- Or wait for an IR-based backend ([[MYLA-67]]) and interpret that.

## Done when

- [x] `push` and element assignment are amortised O(1)
- [x] The interpreter gate still passes, and the table above is measured again

## How

Neither idea was needed: the native copy-on-write already gives the interpreter in-place updates once it holds the only reference to a container. Two things stood in the way.

**The interpreter kept extra references.** An update read the value (`read_place`), built a changed copy and assigned it back, so the old value was still alive while the new one was made, and a `var self` call kept the receiver in a local while the method ran. Now:

- `update_place(p, op)` moves the variable's value into an interpreter field (`cell`), leaving unit behind; `update_cell` walks the path, taking each container apart (its parts held only there) and moving the child into the cell, applies a `PlaceOp` (`OSet`, `OPush`, `OPop`, `ORemove`, `OAppend`, `OAppendByte`) and puts everything back. Myla forbids `self = …`, hence the field instead of a `var self` method on `Value`.
- A `var self` call pushes the receiver onto `receivers`, evaluates the arguments, releases the place (if its path is still valid) and moves the receiver into the method's `self` (`call_with_receiver`).
- `assign_name`, `write_steps`, `set_index`, `set_field`, `map_set`, `list_push`/`list_last`/`list_drop_last` and the builder helpers are gone; bounds checks moved into `index_error`, shared by `check_index` and the quiet `place_valid`.

**Both native backends leaked references**, so counts never dropped back to 1 and every write copied (and the copies leaked, which is why 20,000 pushes ran out of memory). Each leak is fixed in `codegen_x86.py` and `selfhost/codegen.my`, with a reclaim stress program that exhausts the arena (Python backend) or the 30 MB peak bound (self-hosted) without the fix:

- A `match` expression's value is retained into its result slot but was never released (`STRESS_MATCH_RESULT_SRC`).
- An arm that leaves early (`return`, `break`, `continue`, a failing `?`) skipped the drop of the scrutinee's temporaries, e.g. the `Option` in `match lookup(n) { Some(v) => { return v } … }`; the match now registers them with its drop scope (`STRESS_MATCH_EARLY_EXIT_SRC`).
- Temporaries of `if`/`while` conditions, match guards and range bounds were never released; `_eval_scalar`/`eval_scalar` drops them once the value is computed. Each `&&`/`||` operand does the same, because the right one may not run, so the statement's end must not drop its slot (that crashed the first attempt at bootstrap stage 2) (`STRESS_CONDITION_TEMPS_SRC`).
- `pop` on a list of a recursive enum handed out the box pointer as if it were the value (the Python backend's binary trapped, the self-hosted one printed zeros); it now copies the value out and releases the box (parity program `pop_a_boxed_enum`).

The docs: [[Architecture/Native-backend]] (ownership rules), [[Architecture/Self-hosted-compiler]].

## Evidence

The table again (same machine, best of one run each; "before" is the interpreter built from the previous commit):

| n | Python | self-hosted before | self-hosted now |
| --- | --- | --- | --- |
| 5,000 | 0.20 s | 0.35 s | 0.02 s |
| 10,000 | 0.23 s | 2.38 s | 0.04 s |
| 20,000 | 0.36 s | 7.30 s (out of memory) | 0.12 s |
| 100,000 | 1.20 s | | 0.45 s |
| 1,000,000 | 9.70 s | | 3.97 s |

- New test `test_updates_are_amortised_constant` (interpreter gate): `push`, `xs[i] = …`, a `push` in a `var self` method and one into `grid[0]`, 20,000 and 80,000 iterations; it failed (out of memory) before and passes in 1.8 s.
- The three stress programs and `pop_a_boxed_enum` fail without their fixes and pass with them.
- The compiler compiling itself: peak 243 MB → 211 MB at the same speed (2.2–2.3 s, stage 3).
- Bootstrap fixed point: 6,260,616 bytes. Unit 466, integration 4, burn 389: all pass.
