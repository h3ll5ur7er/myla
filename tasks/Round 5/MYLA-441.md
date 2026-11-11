---
id: MYLA-441
title: "Native `map key … not found` for struct, enum and list keys"
type: improvement
status: backlog
priority: low
labels: [lowering, runtime, round-5]
---
Found by [[MYLA-415]] (D183). Natively a missing key of an integer, `char`, `bool` or string type, or a tuple of such, is written as the interpreter writes it (`map key (3, 'b') not found`); a key of a struct, an enum or a list type, or a tuple holding one, still gives `map key not found` (`Lower.key_text_of` returns -1), where the interpreter says `map key P { x: 1 } not found`, `map key Color.Red not found` or `map key [1, 2] not found`. So such an error can't be expected with its text on both runners (D183).

```myla
#derive(Eq, Hash)
struct P { x: int }
fun main() {
    let m = [P { x: 0 }: 1]
    print(m[P { x: 1 }])
}
```

- [ ] Per-type routines writing the interpreter's `py_repr` of a struct, an enum (with its payloads) and a list, built as IR like `__eq_T` (or in Myla source, as the native harness writes its reprs), called on the cold path only
- [ ] Cases in `test_runtime_errors_carry_the_interpreters_values`
