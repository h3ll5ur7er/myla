---
id: MYLA-8
title: Native code evaluates operands and arguments right to left
type: bug
status: review
priority: medium
labels: [native-backend, selfhost, parity, spec]
---
The interpreter evaluates left to right, as the original spec says ("Subexpressions evaluate left-to-right"). Native code evaluates the right operand of a binary operator first, and pushes call arguments last-to-first, so side effects come out in the other order.

## Steps to reproduce

```myla
fun f(x: int) -> int {
    print(x)
    return x
}
fun g(a: int, b: int) -> int { return a + b }
fun main() {
    let y = f(1) - f(2)
    let z = g(f(3), f(4))
}
```

## Expected

`1 2 3 4` (the interpreter).

## Actual

`2 1 4 3` natively. Both [[src/myla/compiler/codegen_x86.py#L3316-L3320]] and the call path ([[src/myla/compiler/codegen_x86.py#L3773-L3782]]) evaluate in reverse; [[selfhost/codegen.my]] copied the same order.

## Done when

- [x] Native code evaluates left to right (evaluate into temporaries, then push), in both backends
- [x] The byte-identical bootstrap fixpoint still holds
- [x] Parity tests for operators, calls, method calls, struct/list/tuple literals
- [x] Evaluation order written down on [[Language/Expressions-and-operators]]

## How

- Binary operators: `_eval_operands` / `eval_operands` evaluate the left operand, push it, evaluate the right, and leave left in `%rax`, right in `%rcx` (int, float and `str` paths). The self-hosted `gen_scalar_method2` (derived `==` and `cmp` on aggregates) stores both addresses in order.
- Calls (direct, generic, methods with the receiver as the first argument, calls through function values): `_store_call_words` / `store_call_words` reserve the argument words and store each in source order; the stack layout and calling convention are unchanged.
- `__write`, `__write_file` and `__run` evaluate their arguments in order.
- Map literals evaluated each value before its key everywhere, including the Python interpreter (`d[k()] = v()` in Python runs `v()` first). Now key, then value, in the interpreter and both backends; the self-hosted interpreter already did this.
- Assignments keep the interpreter's order (value, then place), which native code already followed.
- Cost: left to right costs one more instruction per operator and a `subq` per call. When the order can't be observed, the old sequences stay: a binary operator with a literal operand, and a call where at most one argument isn't a literal (most calls: `fib(n - 1)`, `n < 2`).

A side finding, partial application evaluating its filled arguments at every call (and differently in the self-hosted interpreter), is [[MYLA-75]].

## Evidence

- Parity program `evaluation_order_is_left_to_right` (operators on int, float, `str` and structs with `#derive(Eq)` and `Add`; direct, generic, method and closure calls; `var self` methods; struct, list, tuple, map and enum literals; indexing; `format`/`f"…"`; pipeline; assignments; builtins) in [[tests/burn/test_compiler_parity.py]] and the self-hosted `PARITY_PROGRAMS`. Before: native printed `2 1 6 5 4 3 …` against the interpreter's `1 2 3 4 5 6 …`, receivers last, and a different total (3401 vs 3400) from two `bump` calls. After: Python native, self-hosted native and the self-hosted interpreter all match the interpreter.
- Bootstrap fixed point holds: 6,078,345 bytes of assembly (5,936,708 before, +2.4%; 6,204,738 without the literal shortcuts).
- Speed: fib(40) 1.22–1.40 s against 1.12–1.59 s before (noise); self-compilation 2.07–2.37 s against 2.13–2.42 s. Without the shortcuts fib(40) was about 25% slower.
- Unit, integration and burn suites pass.
