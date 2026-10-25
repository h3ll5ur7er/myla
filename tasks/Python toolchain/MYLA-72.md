---
id: MYLA-72
title: "`?` in a lambda is checked against the enclosing function's return type"
type: bug
status: todo
priority: medium
labels: [checker, closures]
---
Found while fixing [[MYLA-10]]. At run time a `?` inside a lambda returns from the lambda (native code, block-bodied lambdas, and since MYLA-10 expression-bodied lambdas in the interpreter too), but the checker validates it against the *enclosing function's* return type:

```myla
fun half(x: int) -> Option<int> {
    if x % 2 == 1 { return None }
    return Some(x / 2)
}
fun main() {
    let g: (int) -> Option<int> = (x: int) => Some(half(x)? + 100)
    print(match g(4) { Some(v) => v, None => -1 })
}
```

## Expected

Accepted: the lambda returns an `Option`, so `?` on an `Option` is fine inside it. Prints `102`.

## Actual

`type error: '?' on an Option requires the enclosing function to return an Option` (main returns nothing). Making `main` return an `Option` silences it, although `main`'s return type has nothing to do with the lambda.

## Done when

- [ ] The checker checks `?` (and `return`) inside a lambda against the lambda's result type, inferred or expected
- [ ] The example above runs in the interpreter and natively; a parity test
- [ ] The self-hosted checker agrees ([[selfhost/checker.my]])
