---
id: MYLA-75
title: "Partial application evaluates its filled arguments at every call"
type: bug
status: backlog
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

- [ ] The semantics decided and written down (D51 refined if needed)
- [ ] The Python interpreter, both native backends and the self-hosted interpreter agree
- [ ] A parity program with side effects in the filled arguments and the receiver
