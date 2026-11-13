---
id: MYLA-584
title: "A program's own std/ directory gets the standard library's privileges in the checker"
type: bug
status: review
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

- [x] The checker takes the library's functions from the loader, by root (the loader's `std_impls` records every function of a module under the stdlib root's `std/`, or a set of their ids), not by the `std$` prefix of a name
- [x] A test: `tests/burn/test_raw_memory.py` with a program's own `std/` directory, for the type error and the warning

## What changed

- **The loader** ([[selfhost/loader.my]], `load_linked`) records every function of a module under the stdlib root's `std/` (`in_std_root`, by the file's root) in `Loaded.std_impls`, std.rt's included, which it left out as its bodies don't wait (`lazy: may_wait` now, where every recorded function had `lazy: true`); the impls were recorded already.
- **The checker** (`Checker.in_std`, [[selfhost/checker.my]]) asks only whether the declaration being checked is one of them (`std_impls.contains(cur_decl)`), no longer whether its name starts `std$`. A file of `std` checked on its own keeps its privileges through `primitives` (`in_stdlib`), as before, and its functions' origins (`entry_std`).
- Docs: [[Architecture/Module-loader]] (Merge: the functions recorded and the privileges they give), [[Language/Standard-library]] (what the standard library is, for D100 and D152), [[Project/Known-issues]].

## Evidence

- **Test first**: `test_raw_memory.test_a_programs_own_std_directory_is_the_programs`: a program with its own `std/raw.my` (`__addr_of`, `__load64`) and `std/helper.my` (`__write`), and the same under `other/`. At `aef0b21` the `std` case failed (`myla check` exit 0, no error); after, both directories give `type error: '__addr_of' reads or writes raw memory: only the standard library may call it` at `raw.my:2:13`, and `warning[primitive]: '__write' is a primitive of the standard library, not meant to be called from a program` at `helper.my:2:13`. `tests.burn.test_raw_memory`: 4 of 4 pass (the library's own files still may call them).
- No new warning anywhere: `myla check --stdlib lib` of the 37 examples and a std.http server prints `ok`; the bootstrap builds the toolchain (std.rt's raw memory) with a byte-identical fixed point; `scripts/test.sh fast` passes (898 tests).

