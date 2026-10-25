---
id: MYLA-8
title: Native code evaluates operands and arguments right to left
type: bug
status: backlog
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

- [ ] Native code evaluates left to right (evaluate into temporaries, then push), in both backends
- [ ] The byte-identical bootstrap fixpoint still holds
- [ ] Parity tests for operators, calls, method calls, struct/list/tuple literals
- [ ] Evaluation order written down on [[Language/Expressions-and-operators]]
