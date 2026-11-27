---
id: MYLA-514
title: "`map key … not found` names an imported type with the loader's module id (`lib$Q { … }`)"
type: bug
status: done
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

- [x] The interpreter writes the key's type names without module ids (not by `without_module_ids` on the whole text, which would also cut a string key's `$`), and `key_repr_ir` the same (the type name after its last `$`)
- [x] A case in `test_runtime_errors_carry_the_interpreters_values` with a key of an imported type

## What was built

- **The name a program's messages give the type**, as the lead's brief for this batch asks (`lib.Q`, as the checker's messages write a module's names since [[MYLA-383]]): `written_type_name` ([[selfhost/util.my]]) writes the loader's `lib$Q` as `lib.Q`, `std$fs$IoError` as `fs.IoError` (the module's last segment and the name), an entry module's own name as it is. Both runners use it:
  - the interpreter ([[selfhost/interp.my]]): `check_index` writes the missing key with `typed_repr` of `as_written(k)`, the key with each struct's and enum's name rewritten, member by member (a tuple's, a list's, a payload's, a field's); a string key's `$` stays, as no text is rewritten. `py_repr` and `typed_repr` themselves are unchanged, so the test report and `f"{v}"`, which take the ids off the whole text (`Q { a: 1 }`), stay as they were;
  - native code ([[selfhost/lower.my]]): `key_repr_ir` writes a struct's and an enum's name in its `__krepr_<T>` through `written_type_name`.
- `map key lib$Shape.Pair(lib$Q { a: 1, s: "it's" }, [1, 2]) not found` is now `map key lib.Shape.Pair(lib.Q { a: 1, s: "it's" }, [1, 2]) not found` on both runners and all three targets.

**Decision (proposal).** The task asked for `Q { a: 1 }` (the type's name alone, as the test report and `f"{v}"` write it); the batch's brief asked for `lib.Q`, as messages write it, which is what is built: a runtime error is a message, and `lib.Q` names the type wherever it was imported from (two modules may both have a `Q`). The alternatives: `Q` alone (as `f"{v}"`, `without_module_ids` applied name by name), or the name as the program's own source imports it (`Q` after `from .lib import Q`, `lib.Q` after `import .lib as lib`), which neither runner knows at the error.

## Evidence

- Test first: `test_runtime_errors_name_imported_key_types_as_written` ([[tests/burn/test_compiler_parity.py]]) has a key of an imported struct, unit variant, variant with an imported struct and a list in its payload, a struct of the program's own holding an imported struct and a tuple with an imported variant, a list of an imported struct, an `Option` of an imported enum, and a string key `"lib$Q"`; each checks the interpreter's first line and that the binary's stderr is the interpreter's (D183). Before: 6 of 7 failed (`map key lib$Q { a: 1, s: "it's" } not found`, the string key passed); after: all pass on x86-64, aarch64 (`MYLA_TEST_TARGET=aarch64-linux`) and wasm32 (`MYLA_TEST_TARGET=wasm32-wasi`).
- `#test` cases: `written_type_name` (3), `as_written` (2).
- **Suites** (both tasks together, at the lane's tip): `scripts/test.sh fast` 855 tests OK (3 skipped); `tests.burn.test_compiler_parity`, `test_selfhost_interp`, `test_selfhost_cases`, `test_map_remove`, `test_overflow` 317 OK; on aarch64 and wasm32 (`scripts/test-target.py`) `test_compiler_parity`, `test_error_corpus`, `test_overflow`, `test_map_remove`, `test_selfhost_codegen` all pass; `scripts/test.sh` (all) 1,533 tests, one failure, `test_a_counting_loop_below_a_length_indexes_unchecked`, which counted three element addresses for `bs[i].x += bs[i].v` where [[MYLA-506]]'s single lookup leaves two (both still unchecked): its expectation updated, it passes. `scripts/bootstrap.sh`: byte-identical fixed point (23,758,785 bytes); `selfhost/embedded_std.my` unchanged (no `lib/` change).

## Review 2026-11-12

Signed off in [[Project/Review-2026-11-12]].
