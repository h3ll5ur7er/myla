---
id: MYLA-104
title: IR: aggregates
type: feature
status: review
priority: high
labels: [ir, codegen, selfhost]
---
Step 2 of [[MYLA-67]] ([[Architecture/IR]]): structs, tuples and enums without heap values through the IR.

- [x] Struct and tuple literals, field and tuple-index reads and writes, aggregate locals in slots
- [x] Enum construction, `match` with patterns, guards and bindings (no heap values yet)
- [x] Aggregate parameters by address and results through sret, copies
- [x] The gates with `--ir`; `--ir-stats` up

## How

- **IR additions** (`selfhost/ir.my`, `selfhost/ir_x86.my`):
  - slot sizes;
  - `addr`, `%t = %p + off`, `load`/`store` at `[%p + off]`, `copy`;
  - `call … sret %r`;
  - the `trap` terminator (a match no arm matched);
  - the generic instances a function calls (`IrFunc.instances`), which `gen_any_function` requests once the function is lowered, since the lowering only reads the code generator.
- **Lowering** (`selfhost/lower.my`): "plain" values (no heap memory, no boxed members) are lowered:
  - aggregates through a temporary holding their address;
  - parameters as argument words holding the caller's address (`var self` writes reach the caller);
  - results through the first word (sret);
  - struct, tuple and enum literals and constructors in slots of their own;
  - fields and elements at offsets, assignments to fields at any depth;
  - method calls and overloaded `==`, `!=`, orderings and arithmetic;
  - generic calls;
  - `match` with every pattern kind, guards, block arms with a value, the result in a slot and the trap.
- **Place types:** the checker leaves assignment targets untyped, so the lowering derives a place's type from its own slots. The first run of the gate found this: `Box<T>.set` wrote at offset 8, because the old path's `place_type` reads bindings the IR path doesn't make.

## Evidence

- **The `plain_aggregates` parity program** (structs, an enum with payloads, nested fields, `var self`, sret, `+` and derived `==`, generic instances, guards, or-patterns, block arms): all 9 functions go through the IR, and it prints the interpreter's 20 values. It is in the parity corpus of both backends and both self-hosted gates.
- **`SelfHostedCodegenParityThroughIR`** (corpus, runtime errors, modules, stress, parity) passes, and so does the old-path class.
- **Coverage on the examples:** 50 → 94 of 227 functions. The compiler stays at 18 of 1,021, since nearly all of its functions own heap memory (MYLA-105).
- **The bug the gate caught:** `examples/methods.my` printed 41 for 42 and `evaluation_order_is_left_to_right` gave 3256 for 3400, both from the place type above; both pass now.
