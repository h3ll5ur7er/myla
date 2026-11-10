---
id: MYLA-440
title: "Interpreter: a uint64 map key's text in `map key … not found` is signed"
type: bug
status: todo
priority: low
labels: [interpreter, round-5]
---
Found by [[MYLA-415]] (D183). The interpreter writes a missing map key with `py_repr` of its value, which for a `uint64` stored as the int64 of its bits is signed; native code (since MYLA-415) writes it unsigned, as the type says, so the two runners' texts differ for keys of 2^63 or more:

```myla
fun main() {
    let m: [uint64: int] = [1: 2]
    let k: uint64 = 18446744073709551615
    print(m[k])
}
```

`myla run`: `runtime error: map key -1 not found`; native: `runtime error: map key 18446744073709551615 not found`.

- [ ] `index_error` writes the key by its type (`typed_repr`, as the test reports do, MYLA-361), so both runners print `18446744073709551615`
- [ ] A case in `test_runtime_errors_carry_the_interpreters_values` ([[tests/burn/test_compiler_parity.py]])
