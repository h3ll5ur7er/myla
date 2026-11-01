---
id: MYLA-102
title: A local closure shadows a top-level function of the same name
type: bug
status: done
priority: high
labels: [interpreter, codegen, selfhost]
---
A local binding named like a top-level function shadows it, in calls too: the checkers of both toolchains type `fail("x")` as a call of the local `fail`. The self-hosted interpreter and backend called the top-level function anyway:

```
fun fail(m: str) -> int32 { print("the function"); return 1 }
fun g() -> int32 { let fail = (m: str) => len(m); return fail("the closure") }
```

`g()` gives 11 in the Python interpreter and binary, but printed "the function" and gave 1 in the self-hosted interpreter (`build/myla run`) and binary (`build/myla build`). With other parameter types it would run a function with values of the wrong type. Found by the parity tests of [[MYLA-93]], where a `fail` closure in `selfhost/project.my` called a driver's `fun fail` and crashed.

- [x] A parity program in `tests/burn/test_compiler_parity.py`'s corpus, and the same in the self-hosted interpreter and codegen gates, failing first
- [x] `selfhost/interp.my`: `eval_name_call` looks for a local before a function
- [x] `selfhost/codegen.my`: the call dispatch and `call_is_indirect` treat a name the checker typed as a value (a local in scope) as an indirect call, and the frame layout reserves no slot for a called name

## How

- **Interpreter:** `eval_name_call` looked the name up as a function (`func_idx`) before the scopes; now a binding in scope wins, then the function.
- **Code generator:** the checker types a call through a name as an indirect call exactly when a local is in scope (`infer_call`'s shadowing branch, `infer_indirect_call`), and only that path records the callee's type. `called_as_value(callee)` reads that decision from `resolved`, so the frame layout, which runs without scopes, and the generation agree: `call_is_indirect` and the call dispatch take the indirect path for a function name the checker typed as a value.
- **A second bug that the first one hid:** the layout visited the callee of an indirect call, and a callee named like a function got a 16-byte slot for materializing the function as a value, which was then released after the call without ever being written: `apply(twice: (int32) -> int32, …)` dropped garbage and crashed. A called name never needs a slot (a function is called directly, a local through its own slot), so the layout no longer visits it.

## Evidence

The parity program `local_closure_shadows_a_function` (a closure in an inner block, a function-typed parameter, the function called again outside the block) prints `11 101 the function 1 10 9` in the Python interpreter and binary. Before the fix:

- self-hosted interpreter: `the function 1 2 the function 1 10 20`;
- self-hosted binary: crashed with SIGSEGV after `… 10`, once the dispatch was fixed but the slot was still there; the gate failed for both.

After the fix both gates pass (`SelfHostedCodegenParity` and `SelfHostedInterpParity`, `test_parity_programs_match_the_oracle`), and `apply`'s assembly has no `__func_drop`.

## Leftover

A local closure named like a *builtin* (`build`, `len`) still calls the builtin in the self-hosted interpreter and lowering: [[MYLA-152]].
