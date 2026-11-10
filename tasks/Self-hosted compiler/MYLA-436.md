---
id: MYLA-436
title: "Interpreter: an `eq` or `hash` written for a generic type, called for a list's `==` or a map key, binds no type parameter"
type: bug
status: todo
priority: low
labels: [interpreter, generics, parity]
---
Found by [[MYLA-414]]'s lane. Since MYLA-414 every generic call, operator and format binds the callee's type parameters in its frame (H1). The interpreter's own calls of a written `eq` or `hash` don't: `values_equal` comparing a list's or a struct's elements, and `key_hash`/`key_place` hashing and comparing a map's keys, call the method with no type to bind, so inside it `T` is unbound and an operation typed by `T` falls back to erasure (a `uint64` compares signed, an `int8` doesn't trap).

```myla fragment
struct W<T> {
    v: T,
}

impl<T: Ord> Eq for W<T> {
    fun eq(self, other: W<T>) -> bool {
        return !(self.v < other.v)
    }
}

fun main() {
    let x = W { v: 0u64 }
    let y = W { v: 18446744073709551615u64 }
    print(x == y)       // false on both runners: the operator binds T
    print([x] == [y])   // natively false, interpreted true: 0 < MAX read signed
}
```

- [ ] `values_equal` and the map's key functions take the static type where it is known (the operator's operand, the map's or list's element type) and bind the method's frame by it (`bind_next(fi, -1, t)`), as `eval_op_overload` does; where none is known (a map's key without a type), say so here
- [ ] A parity program with the reproduction
