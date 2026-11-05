---
id: MYLA-282
title: "aarch64, wasm32: a function value of a function taking a value by copy"
type: bug
status: backlog
priority: medium
labels: [platforms, aarch64, wasm, codegen]
---
Found by the per-target suites ([[MYLA-268]]). A plain `fun` used as a function value goes through an adapter (`myla_<fn>__fnval`, [[MYLA-126]]) that gives each owned parameter a reference of its own. When the function takes a struct, tuple or enum by copy (D88, as `become` hands one over), the x86-64 adapter copies its words; the aarch64 one stops the compiler with "internal error: aarch64: a function value of a function taking a value by copy (not yet, MYLA-163)" (`emit_fnval_thunk_a64` in [[selfhost/ir_a64.my]]), and the wasm32 one with "internal error: wasm: a function value of a function taking a value by copy (not yet, MYLA-158)" ([[selfhost/ir_wasm.my]]).

So the parity program `become_passes_aggregates_by_value` doesn't build for either target: `tests/burn/_targets.py` excuses `test_compiler_parity.TestCompilerParity.test_become_passes_aggregates_by_value`, `test_selfhost_codegen.SelfHostedCodegenParity.test_become_passes_aggregates_by_value`, and the program in `test_become_runs_a_million_deep`'s loop.

- [ ] aarch64: the adapter copies the words of a parameter passed by copy (as `gen_partial_function_a64` already does for a partial application)
- [ ] wasm32: the same
- [ ] The three exceptions out of `_targets.py`
