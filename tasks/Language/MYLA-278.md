---
id: MYLA-278
title: "The unit type `()` (D138), and std's \"succeeds or fails\" results as `Result<(), E>`"
type: feature
status: backlog
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

- [ ] [[Language/Types]], [[Language/Lexical-structure]] (the literal `()`, kept apart from a parenthesised expression and a 1-tuple `(x,)`) and [[Language/Grammar]]
- [ ] Checker: `()` as a type argument and a value; `Ok(())`, `match` on it, `==` (always true); a function without a return type still returns nothing (no change)
- [ ] Layout: zero words (a `Result<(), E>`'s `Ok` has no payload), through the lowering and every backend
- [ ] Std: `write_to_file`, `make_dir`, the `remove_*` functions and `rename` return `Result<(), IoError>` ([[MYLA-190]]); the callers in `selfhost/` and `tools/` updated
- [ ] `#test(...)[()]` and the harvester
- [ ] Tests: parity programs, the error corpus, the interpreter
