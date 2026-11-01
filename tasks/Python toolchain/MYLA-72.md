---
id: MYLA-72
title: "`?` in a lambda is checked against the enclosing function's return type"
type: bug
status: done
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

## Fix

Block-bodied lambdas already checked `?` and `return` against the lambda's expected result type; expression-bodied ones forgot to set it, so `?` saw the enclosing function's ([[src/myla/types.py]] `_infer_lambda`, [[selfhost/checker.my]] `infer_lambda`). When the lambda's result type isn't known (nothing expected, no annotation), `?` now says so instead of blaming the enclosing function, and the messages name the enclosing lambda when inside one. A `?` can't infer the lambda's type on its own: the carrier is only known from the context.

- [x] The checker checks `?` inside a lambda against the lambda's result type (the expected one; an unknown one is reported as such)
- [x] The example above runs in the interpreter and natively: unit tests `TestTryInLambdas` (all four failed before), the parity program `try_in_lambdas_checks_against_the_lambda`, the error-corpus case `examples/errors/type_try_in_untyped_lambda.my`
- [x] The self-hosted checker agrees: the parity program runs through the self-hosted compiler (failed before), and the error case gives the same position
