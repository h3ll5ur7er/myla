---
id: MYLA-11
title: "#test attributes in imported modules can't name module-level declarations"
type: bug
status: review
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

- [x] `_Renamer` rewrites `#test` arguments and outputs like other expressions
- [x] Loader unit test

## How

- Python: `_Renamer._function` rewrites the arguments and outputs of each `#test` attribute with no locals in scope, before the parameters become locals ([[src/myla/loader.py]]).
- The self-hosted loader had the same gap (the self-hosted interpreter and compiler both failed with `unknown name 'LIMIT'` at `lib.my:7:7`): `Renamer.attributes` in [[selfhost/loader.my]] does the same.

## Evidence

- `test_test_attributes_name_their_modules_declarations` in [[tests/unit/test_loader.py]] (a const, a struct literal, an enum constructor and a private function in `#test` cases): before, `TypeCheckError: unknown name 'LIMIT'`; after, the program runs and `run_tests` passes both cases of `lib$double`.
- The same project in the self-hosted `MODULE_PROJECTS` ([[tests/burn/test_selfhost_codegen.py]], also run by the interpreter gate).
- Bootstrap fixed point holds (6,087,364 bytes); unit, integration and burn suites pass.
