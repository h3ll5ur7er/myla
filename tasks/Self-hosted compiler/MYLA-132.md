---
id: MYLA-132
title: The self-hosted backend can't lower an explicit call of a derived `eq`
type: bug
status: done
priority: low
labels: [codegen, selfhost]
---
Found while making [[MYLA-131]]. A derived `Eq` (`#derive(Eq)`) gives a type an `eq` method, which `==` calls through the code generator's own routine (`emit_derived_eq`). Called by name, `a.eq(b)` (or `become a.eq(b)`) is not a function the lowering knows (`has_func` is false), so `call` takes it for a call through a function value, and the function falls back with "can't be lowered to the IR: a call through a value of that type". The self-hosted interpreter fails the same way: it runs the synthesized `eq`, which has no body. The Python interpreter and the Python backend run it.

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

- [x] A parity program calling a derived `eq` of a struct and of an enum by name (`derived_eq_called_by_name`)
- [x] The lowering calls the derived routine with the operands' addresses (`derived_eq`); `become` makes it an ordinary call and returns its result, since the routine calls nothing that comes back to user code
- [x] The self-hosted interpreter compares structurally, as `==` does (`derived_eq`, also for `become`)

## Evidence

- `derived_eq_called_by_name` printed `ERR: VUnit` for every line in the self-hosted interpreter and didn't compile with the self-hosted backend ("a call through a value of that type"); now all four implementations print `true false true false true true false`.
