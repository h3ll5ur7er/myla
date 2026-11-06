---
id: MYLA-282
title: "aarch64, wasm32: a function value of a function taking a value by copy"
type: bug
status: done
priority: medium
labels: [platforms, aarch64, wasm, codegen]
---
Found by the per-target suites ([[MYLA-268]]). A plain `fun` used as a function value goes through an adapter (`myla_<fn>__fnval`, [[MYLA-126]]) that gives each owned parameter a reference of its own. When the function takes a struct, tuple or enum by copy (D88, as `become` hands one over), the x86-64 adapter copies its words; the aarch64 one stops the compiler with "internal error: aarch64: a function value of a function taking a value by copy (not yet, MYLA-163)" (`emit_fnval_thunk_a64` in [[selfhost/ir_a64.my]]), and the wasm32 one with "internal error: wasm: a function value of a function taking a value by copy (not yet, MYLA-158)" ([[selfhost/ir_wasm.my]]).

So the parity program `become_passes_aggregates_by_value` doesn't build for either target: `tests/burn/_targets.py` excuses `test_compiler_parity.TestCompilerParity.test_become_passes_aggregates_by_value`, `test_selfhost_codegen.SelfHostedCodegenParity.test_become_passes_aggregates_by_value`, and the program in `test_become_runs_a_million_deep`'s loop.

- [x] aarch64: the adapter copies the words of a parameter passed by copy (as `gen_partial_function_a64` already does for a partial application)
- [x] wasm32: the same
- [x] The three exceptions out of `_targets.py`

## Evidence (2026-11-06)

- The adapter of a function with a parameter passed by copy is a partial application with every argument a hole (`emit_fnval_thunk_a64` and `emit_fnval_thunk_wasm` build a `PartialJob` and use `gen_partial_function_a64` and `gen_partial_function_wasm`): each such argument arrives as an address, its words are copied with references of their own, a parameter passed owned gets a reference of its own, and the function is jumped to (on aarch64 when every word is in a register) or `return_call`ed. An async function's adapter still makes its frame.
- Test first: `test_aarch64`'s `function_value_taking_a_copy` (a `become` handing a struct over, the function used as a value, 100000 deep), which `test_wasm` runs too: both stopped with the internal error before, both give the x86-64 binary's output after.
- `scripts/test-target.py <target> test_compiler_parity test_selfhost_codegen`: both pass on aarch64 and wasm32 without the three exceptions (`become_passes_aggregates_by_value` as a test of each and as a program of `test_become_runs_a_million_deep`).
