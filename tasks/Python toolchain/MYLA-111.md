---
id: MYLA-111
title: "#test arguments and expected values are not type-checked"
type: bug
status: todo
priority: low
labels: [checker, attributes]
---
`#test(args)[expected]` checks the number of arguments, but not their types or the expected value's: both checkers infer each with the parameter's (or the result's) type as a hint (`_expect_value` in `_check_test_attr`, `expect_value` in `check_test_attr`) and never compare the result with it. Found while working on [[MYLA-65]].

## Steps to reproduce

```myla
#test("s")[1]
fun k(a: int) -> int {
    return a
}
fun main() {}
```

`myla check` prints `ok` (Python CLI and `build/myla`); `myla test` then fails at run time with `FAIL  k #1: expected 1, got 's'`. `#test(2)[true]` is accepted the same way.

## Expected

A type error at the argument (or the expected value), like a call with a wrong argument type: `_expect_type` / a `type_eq` check with the parameter type, in both checkers, with snippets in the checker gate and a file in `examples/errors/`.

- [ ] Python checker
- [ ] Self-hosted checker
- [ ] Gate snippets and corpus file
