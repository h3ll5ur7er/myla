---
id: MYLA-75
title: "Partial application evaluates its filled arguments at every call"
type: bug
status: done
priority: medium
labels: [interpreter, native-backend, selfhost, parity, spec]
---
Found while fixing the evaluation order ([[MYLA-8]]). D51 and [[Language/Expressions-and-operators]] say that in `f(a, _)` "the other arguments (and a method's receiver) are captured by value". The Python toolchain instead rewrites the call into `(h) => f(a, h)`, so `a` is evaluated again at every call of the partial, and not at all if it is never called. The self-hosted interpreter evaluates `a` once, when the partial is created.

## Steps to reproduce

```myla
fun f(x: int) -> int {
    print(x)
    return x
}
fun g(a: int, b: int) -> int { return a + b }
fun main() {
    let part = g(f(1), _)
    print(part(f(2)))
    print(part(f(3)))
}
```

## Actual

- Python interpreter and both native backends: `2 1 3 3 1 4` (`f(1)` runs at each call, after the hole's argument).
- Self-hosted interpreter: `1 2 3 3 4`.

## Expected

Decide, and record it on [[Project/Decisions]]. Evaluating the filled arguments once, left to right, when the partial is created matches "captured by value" and the self-hosted interpreter; it needs the rewrite to bind them to temporaries first (`{ let t = f(1); (h) => g(t, h) }`).

## Done when

- [x] The semantics decided and written down (D51 refined if needed)
- [x] The Python interpreter, both native backends and the self-hosted interpreter agree
- [x] A parity program with side effects in the filled arguments and the receiver

## How

D60 (refining D51): the receiver and the filled arguments are evaluated once, left to right, when the partial is made, which is what "captured by value" says and what the self-hosted interpreter and code generator already did.

The Python checker's desugaring (`_infer_partial` in [[src/myla/types.py]]) now binds them as the parameters of an outer lambda applied on the spot: `g(f(1), _)` becomes `((__arg0: int) => (__hole0: int) => g(__arg0, __hole0))(f(1))`, and `c(5).add(f(6), _)` binds `__recv` as well. Literals stay inline, and a partial without anything to bind keeps the plain lambda. The interpreter and the native backend run the desugared form, so both changed together; the self-hosted toolchain needed no change. `_is_literal_expr` is shared with the code generator's MYLA-8 shortcut.

Calling partial application on an arbitrary expression (`pick(9)(_, 1)`) is still rejected by both checkers ("requires a function, method, or function value"); a function value has to be bound to a name first.

## Evidence

- `TestPartialApplication` in [[tests/unit/test_interpreter.py]]: before, `0 3 1 2 132 1 2 142 …` (the arguments ran at every call, after the hole's); after, `1 2 0 3 132 142 5 6 0 18 19 103`.
- Parity program `partial_application_evaluates_its_arguments_once` (filled arguments, receiver, a function value, a variable changed after the partial is made, literals) in [[tests/burn/test_compiler_parity.py]] and the self-hosted `PARITY_PROGRAMS`: the Python native backend, the self-hosted compiler and the self-hosted interpreter all match the interpreter. The partial reference-counting stress test still reclaims its heap.
- Bootstrap fixed point holds (6,091,753 bytes); unit, integration and burn suites pass.
