---
id: MYLA-278
title: "The unit type `()` (D138), and std's \"succeeds or fails\" results as `Result<(), E>`"
type: feature
status: review
priority: medium
labels: [language, types, stdlib]
---
Decided by D138 (2026-11-05; changes D35). `()` is a type with one value, also written `()`.

```myla
fun save(path: str, text: str) -> Result<(), IoError> {
    write_to_file(path, text)?
    return Ok(())
}
```

- [x] [[Language/Types]], [[Language/Lexical-structure]] (the literal `()`, kept apart from a parenthesised expression and a 1-tuple `(x,)`) and [[Language/Grammar]]
- [x] Checker: `()` as a type argument and a value; `Ok(())`, `match` on it, `==` (always true); a function without a return type still returns nothing (no change)
- [x] Layout: zero words (a `Result<(), E>`'s `Ok` has no payload), through the lowering and every backend
- [x] Std: `write_to_file`, `make_dir`, the `remove_*` functions and `rename` return `Result<(), IoError>` ([[MYLA-190]]); the callers in `selfhost/` and `tools/` updated
- [x] `#test(...)[()]` and the harvester
- [x] Tests: parity programs, the error corpus, the interpreter

## How it is built

`()` is the 0-tuple, `Type.TTuple([])`: the tuple machinery gives it its layout (no bytes), its copies and its instance names, so the parser (the type, the value, the pattern and the binding `()`), the checker (`==`, `#derive(Eq)`) and the lowering (`==` is a constant once both sides ran; a list literal stores nothing for an element without size, which also fixes `[U {}]` for an empty struct `U`) are what changed. [[tests/burn/test_unit_type.py]] runs it in the interpreter and natively, and the same program on aarch64 and wasm32 (`PROGRAMS["unit"]`).

The std functions changed in a second commit, once the seed parsed `()`: `make_dir_all` with `make_dir`, which also held an always-0 `Ok`. `write_to_file`'s `Ok` held the number of bytes, which is always `contents.len()`, the caller's own number. Selfhost's own always-0 results (`fetch`, `check_out`, the checker's `Result<int32, CheckErr>` passes) are left as they are: they are internal, and changing them is a sweep of its own.

Left open for the owner: a function without a result type is still not a function returning `()` (D138), so its type still can't be written (`(int) -> ()` is the type of a function that returns the unit value). Swift makes the two the same (`Void` is `()`); here that would be a decision of its own.
