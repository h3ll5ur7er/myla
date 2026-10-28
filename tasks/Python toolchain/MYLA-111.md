---
id: MYLA-111
title: "#test arguments and expected values are not type-checked"
type: bug
status: review
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

- [x] Python checker
- [x] Self-hosted checker
- [x] Gate snippets and corpus file

## How

Both checkers compare the type each `#test` argument and the expected value infer to (with the parameter's, or the result's, type as the hint) with that type, as a call's arguments are compared. A mismatch is a type error at the argument or the expected value, in the style of the call messages: `'#test' argument type mismatch: expected 'int32', found 'str'` and `'#test' expected value type mismatch: expected 'int32', found 'bool'` (`_check_test_attr` in `types.py`, `check_test_attr` in `selfhost/checker.my`).

## Evidence

- `examples/errors/type_test_attr_arg_type.my` and `type_test_attr_expected_type.my`, with their message and span. Both failed before the change; the error corpus, the checker gate (which runs the corpus through the self-hosted checker: same position, range and message) and the codegen gate's diagnostics comparison pass.
- Every example, compiler, tool and library source with `#test` cases still checks.
