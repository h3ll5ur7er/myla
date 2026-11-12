---
id: MYLA-514
title: "`map key … not found` names an imported type with the loader's module id (`lib$Q { … }`)"
type: bug
status: todo
priority: low
labels: [interpreter, lowering, round-5]
---
Found by [[MYLA-441]]'s lane. A missing map key of a struct or enum type declared in another module is written with the name the loader gave the type, its module id in front: `map key lib$Shape.Pair(lib$Q { a: 1, s: "it's" }, [1, 2]) not found`. Both runners agree (the interpreter's `py_repr` writes the value's name; natively `__krepr_<T>` writes the type's, the same since [[MYLA-441]]), but the test report and `f"{v}"` take the ids off (`without_module_ids`), so the error is the one place a program sees them.

`lib.my`:

```myla fragment
#derive(Eq, Hash)
pub struct Q { a: int }
```

`main.my`:

```myla fragment
from .lib import Q
fun main() {
    let m = [Q { a: 0 }: 1]
    print(m[Q { a: 1 }])
}
```

`myla run main.my` and the binary: `runtime error: map key lib$Q { a: 1 } not found`; expected `map key Q { a: 1 } not found`.

- [ ] The interpreter writes the key's type names without module ids (not by `without_module_ids` on the whole text, which would also cut a string key's `$`), and `key_repr_ir` the same (the type name after its last `$`)
- [ ] A case in `test_runtime_errors_carry_the_interpreters_values` with a key of an imported type
