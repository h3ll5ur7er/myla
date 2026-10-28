---
id: MYLA-106
title: IR: closures, function values and the rest
type: feature
status: in-progress
priority: medium
labels: [ir, codegen, selfhost]
---
Step 4 of [[MYLA-67]] ([[Architecture/IR]]): what is left.

- [ ] Lambdas and their environments, function values, partial application, composition
- [x] `for` over lists and maps, `?`, every remaining builtin and I/O primitive (the loops and builtins came with [[MYLA-105]]); destructuring declarations
- [ ] `-g` through the IR: `bind` → variables and lexical blocks; `test_debug_info.py` with `--ir`

## How (part 1: `?`)

- **IR:** `moved $slot`: an owning slot's value went into a container. It emits no code; the verifier now counts the slot as empty, and rejects a move out of an empty or non-owning slot.
- **Staged values:** `stage` keeps a value bound for a container or member in an owning slot registered with the statement, and `store_staged` moves it in (boxing a recursive enum there) and removes the slot from the statement's temporaries. Assignments to members, `push`, map inserts and map literals use it. A `?` in the place, index or key after the value then releases it, as the old path's staged drops do.
- **`?`:** `try_expr` follows the old `gen_try`. The success payload is borrowed from the operand (unboxed for a recursive enum). On failure, the tag and the failure's payload are copied into the result's storage and retained with the result's type; temporaries and owners are dropped as for `return`.
- **Destructuring:** a retained copy per name, nested tuples included.
- **Diverging arms:** an arm whose body ends in `panic(…)` or `unreachable()` stores no value.

## Evidence (part 1)

- **Parity:**
  - the `try_through_the_ir` program covers `?` on Result and Option with scalar, string, struct and recursive-enum payloads, in conditions and in loops that own a list, plus a panicking arm: all 11 functions go through the IR and print the interpreter's output;
  - `destructure_boxed_enum_and_list_leaves` goes through the IR entirely.
- **Stress:** `STRESS_TRY_SRC` and `STRESS_TRY_AFTER_STAGED_VALUE_SRC` now run entirely through the IR at 11 MB, as do all stress programs except the two about closures.
- **Mutation:** a scalar staged value not registered with the statement takes the staged-value stress program to 3,890 MB.
- **Verifier:** tests for a move after a store, a drop after a move, and a move out of an empty slot.
- **Old path:** byte-identical on `selfhost/gen_main.my` and `examples/methods.my`.
- **Self-compile:** the compiler built with `--ir` emits the same assembly as the normal build (10,215,310 bytes).
- **Coverage:** examples go from 198 to 207 of 227 functions, the compiler from 1,007 to 1,084 of 1,111.
