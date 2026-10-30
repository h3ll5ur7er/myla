---
id: MYLA-132
title: The self-hosted backend can't lower an explicit call of a derived `eq`
type: bug
status: todo
priority: low
labels: [codegen, selfhost]
---
Found while making [[MYLA-131]]. A derived `Eq` (`#derive(Eq)`) gives a type an `eq` method, which `==` calls through the code generator's own routine (`emit_derived_eq`). Called by name, `a.eq(b)` (or `become a.eq(b)`) is not a function the lowering knows (`has_func` is false), so `call` takes it for a call through a function value, and the function falls back with "can't be lowered to the IR: a call through a value of that type". The interpreters and the Python backend run it.

```myla
#derive(Eq)
struct P { x: int, s: str }
fun same(a: P, b: P) -> bool {
    return a.eq(b)
}
fun main() {
    print(same(P { x: 1, s: "k" }, P { x: 1, s: "k" }))
}
```

- [ ] A parity program calling a derived `eq` of a struct and of an enum by name
- [ ] The lowering calls the derived routine (with the operands' addresses; by value where a `become` hands one over, D88, which the routine would then need to accept)
