---
id: MYLA-710
title: "A builtin call named like a field of the file isn't resolved, and test_lsp fails on it"
type: bug
status: todo
priority: low
labels: [lsp]
---
Found by [[MYLA-700]] (2026-11-14): `selfhost/target.my`'s `Target` has a field `format`, and its `format(...)` calls made `tests.burn.test_lsp`'s `test_the_corpus_resolves` fail (`format at 137:12 is not resolved`). The language server's `--resolve` lists a struct's fields as `global` definitions, so the test takes the builtin `format` for a use of the file's own name, which nothing resolves. The same quirk as a `format` method's ([[MYLA-376]], the `myla` skill's rules: write an f-string); [[MYLA-372]] fixed it for `get` inside an impl.

Reproduction (`build/myla-lsp --stdlib lib --resolve a.my`):

```myla fragment
struct T { format: int }

fun f(n: int) -> str {
    return format("{}", n)
}
```

prints `def 0:11-17 global format` and no `use` for the call; the test then fails. `target.my` writes f-strings for now.

- [ ] A field (and a method) is not a global definition in `--resolve`'s output, or the test tells a builtin call from a use of the file's names; the f-strings in `target.my` may go back to `format` after
