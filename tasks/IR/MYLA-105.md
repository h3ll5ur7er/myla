---
id: MYLA-105
title: IR: heap values, ownership and the verifier
type: feature
status: in-progress
priority: high
labels: [ir, codegen, selfhost]
---
Step 3 of [[MYLA-67]] ([[Architecture/IR]]): strings, lists, maps and builders through the IR, with every ownership rule of [[Architecture/Native-backend#heap-and-reference-counting]] as explicit `retain`/`drop`/`cow`.

- [x] Part 1: strings and aggregates holding them (literals, consts, concatenation, `==`/`!=`, `len`, `print`, fields and payloads, string patterns); owners, owned temporaries, `return`/`break`/`continue` drops, staged assignments, match copies; `retain`/`drop`/`rt`/`init`
- [x] The verifier, run on every function the gates compile; a test with deliberately broken IR for each rule
- [x] A string stress program (some 50 MB of churn) with `--ir`
- [ ] Part 2: lists: literals, indexing (with the string's byte index) and its bounds trap, `push`/`pop`/`len`/`contains`, staged stores into elements and copy-on-write, `for` over a list
- [ ] Part 3: maps, builders, `chars`, `format` and f-strings, the remaining builtins
- [ ] The list and map stress tests with `--ir`

## How (part 1)

- **IR:** `rt` (runtime helpers in the calling registers), `retain T %v` and `retain T [%p]`, `drop T $slot` and `drop T [%p]`, `init $slot`; `Slot.owns`. Retains and member drops use the old path's walks (`retain` through `%r8`, `walk_member` through `%rbx`), so the helpers called are the same.
- **Lowering:** an owner stack parallel to the scopes and a temporary stack per statement or condition (`begin_temps`/`end_temps`). `return` drops every temporary and owner, `break`/`continue` those of the scopes the loop opened. `owned_value` puts a new reference into an owning temporary slot. Every rule is listed on [[Architecture/IR#lowering-ownership]].
- **Verifier:** `verify` in `selfhost/ir.my`, a forward dataflow over owning slots (live or not) on the reachable blocks. `gen_any_function` runs it; a rejection falls back with `IR verifier: …`, and the IR gate asserts none occurs on the corpus.

## Evidence (part 1)

- **Parity:** the `strings_through_the_ir` parity program and `STRESS_STR_OWNERSHIP_SRC` (both in the corpus of both backends and both self-hosted gates) give the interpreter's output through the IR, with the same peak memory as the old path (11 MB). The gates pass with `--ir`.
- **Verifier:** its tests cover a leak at `ret`, a double drop, a drop of a slot that owns nothing, a store over a live value, and paths that disagree.
- **Mutation:** an `end_temps` that doesn't drop makes the IR gate fail (`main: IR verifier: L14: $1 (__enum) still holds a value at ret`).
- **Coverage:** examples 94 → 122 of 227, the compiler 18 → 64 of 1,072. No function of the examples or the compiler is rejected by the verifier.
