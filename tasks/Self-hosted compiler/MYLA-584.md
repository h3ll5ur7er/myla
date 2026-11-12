---
id: MYLA-584
title: "A program's own std/ directory gets the standard library's privileges in the checker"
type: bug
status: todo
priority: medium
labels: [checker, loader, round-6]
---
Found by [[MYLA-413]] (round 6, wave 2). Its fix makes the loader decide what is the standard library by the file's root (`Loader.in_std_root`), so a program's own `std/helper.my` is read whole and its impls aren't counted as the library's. The checker still decides by the function's name: `Checker.in_std` (`selfhost/checker.my`) takes any function whose qualified name starts `std$` for the library's, and a program's own `std/raw.my` is named `std$raw`. So such a module calls a raw-memory primitive with no type error (D152) and a `__` primitive with no warning (D100), where the same file under `other/` gets both.

```
std/raw.my:
pub fun peek(s: str) -> int64 {
    let p = __addr_of(s)
    return __load64(p)
}

main.my:
from .std.raw import peek
fun main() {
    print(peek("abcdefgh") != 0)
}
```

`myla run main.my`: `runtime error: '__addr_of' reads and writes raw memory, which only native code does` (it passed the checker; natively it would read the string's bytes). With the directory named `other/` (and the import `.other.raw`): `type error: '__addr_of' reads or writes raw memory: only the standard library may call it`. Likewise `__write(1, …)` from `std/helper.my` gets no `warning[primitive]`, from `other/helper.my` it does. Base `07445ab` with [[MYLA-413]]'s fix.

- [ ] The checker takes the library's functions from the loader, by root (the loader's `std_impls` records every function of a module under the stdlib root's `std/`, or a set of their ids), not by the `std$` prefix of a name
- [ ] A test: `tests/burn/test_raw_memory.py` with a program's own `std/` directory, for the type error and the warning
