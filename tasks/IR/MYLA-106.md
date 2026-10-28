---
id: MYLA-106
title: IR: closures, function values and the rest
type: feature
status: review
priority: medium
labels: [ir, codegen, selfhost]
---
Step 4 of [[MYLA-67]] ([[Architecture/IR]]): what is left.

- [x] Lambdas and their environments, function values, partial application, composition
- [x] Lambda bodies through the IR (the partial-application and function-value thunks stay fixed adapters)
- [x] `for` over lists and maps, `?`, every remaining builtin and I/O primitive (the loops and builtins came with [[MYLA-105]]); destructuring declarations
- [x] `-g` through the IR: `bind` → variables and lexical blocks; `test_debug_info.py` with `--ir`

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

## How (part 2: function values)

- **IR:**
  - `label sym`, a code address;
  - `call [%fv](%args)` and `… sret %r`, a call through a function value. The arguments are pushed, then the environment, then the result's address, as in `store_call_words`; the verifier counts the `sret` form as a store into the result's slot.
- **Lowering:**
  - function types are lowerable, so `blocked_types` blocks only declarations that use `Self`;
  - a call whose callee isn't a function (a local, a field, a list element, a call's result) goes through `indirect_call`, which evaluates the callee first;
  - `fat_value` builds a function value in a slot owned by the statement: a lambda (captures from the lowering's own scopes, copied and retained at the old path's offsets), a partial application (the old `gen_partial`'s environment layout), a composition, or a named function (its thunk with a null environment).
- **Requests:** `lower_function` now returns `Lowered`, the IR plus the lambda bodies, partial thunks and function-value thunks to emit. `gen_any_function` queues them as the old path does, only when the function goes through the IR.

## Evidence (part 2)

- **Parity:** the `function_values_through_the_ir` program covers lambdas capturing strings and lists, named functions and methods as values, partials of functions, methods and function values, composition, and calls through locals, fields, list elements and call results, with scalar and aggregate results. All 8 functions go through the IR and print the interpreter's output.
- **Corpus:** every function of the 92 corpus sources (examples, parity programs and stress programs), the runtime-error programs and the I/O project goes through the IR. The gate now asserts exactly that, which replaces the per-program assertions.
- **Stress:** every stress program runs entirely through the IR, at 11 MB.
- **Mutation:** captures stored without their retains change the parity program's output.
- **Old path:** byte-identical on `selfhost/gen_main.my` and `examples/methods.my`.
- **Self-compile:** all 1,119 functions of the compiler go through the IR, and the compiler built that way emits the same assembly as the normal build (10,454,359 bytes).

## How (part 3: lambda bodies, `-g`)

- **Lambda bodies:** `lower_lambda` lowers a lifted lambda the way `lower_function` lowers a function. The environment is the argument word after the result's address; each capture is copied out of it into a non-owning slot at entry (bound for the debugger); an expression body returns like `return` (`ret_value`, now shared with `return`).
- **The code generator:** `gen_any_lambda` puts lambda jobs through the IR, under the defining function's substitution, then emits the environment's release function as before. `take_ir` holds what `gen_any_function` and `gen_any_lambda` share: the verifier, the queued requests, `--ir-stats` and `--emit-ir`. `emit_ir_at` emits a function from a declaration id and position, which a lambda has without a `FunData`.
- **`-g`:** `emit_ir` already produced the old path's DWARF variables and scopes from `bind` and `scope`. `test_debug_info.py` now runs its self-hosted line-table and gdb classes again with `--ir`.

## Evidence (part 3)

- **Coverage:** with its lambdas, the compiler has 1,124 functions through the IR and none by the old path; the CLI has 1,459 and the language server 949. The parity, stress and example corpus stays entirely in the IR (the gate's assertion).
- **Debugging:** the 48 debug-information tests pass, the `--ir` classes included: gdb shows arguments, locals, scopes, strings, lists and aggregates, and `set var` works.
- **Self-compile:** the compiler built with `--ir` emits the same assembly as the normal build (10,526,729 bytes).
- **Old path:** byte-identical on `selfhost/gen_main.my` and `examples/methods.my`; every stress program at 11 MB.
