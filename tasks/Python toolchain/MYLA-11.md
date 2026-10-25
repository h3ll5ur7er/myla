---
id: MYLA-11
title: "#test attributes in imported modules can't name module-level declarations"
type: bug
status: backlog
priority: medium
labels: [loader, testing]
---
The loader renames every module's top-level names to `module$name`, but it never rewrites expressions inside attributes ([[src/myla/loader.py#L262-L274]] skips `fn.attributes`). The checker validates every module's `#test` cases, so an imported module whose `#test` mentions one of its own consts, structs or enums can't be used.

## Steps to reproduce

`lib.my`:
```myla
pub const LIMIT: int = 10

#test(LIMIT)[20]
pub fun double(x: int) -> int {
    return x * 2
}
```
`main.my`:
```myla
from .lib import double
fun main() { print(double(4)) }
```

## Actual

`type error: unknown name 'LIMIT'`, reported at `main.my:3:7` (see [[MYLA-10]]).

## Done when

- [ ] `_Renamer` rewrites `#test` arguments and outputs like other expressions
- [ ] Loader unit test
