---
id: MYLA-710
title: "A builtin call named like a field of the file isn't resolved, and test_lsp fails on it"
type: bug
status: review
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

- [x] A field (and a method) is not a global definition in `--resolve`'s output, or the test tells a builtin call from a use of the file's names; the f-strings in `target.my` may go back to `format` after

## What changed

- **The cause** ([[tools/lsp/resolve.my]]'s `kind_name`): `--resolve` printed every declaration of the file as `global`, a type's members too. The resolution itself was right (a call `format(…)` is the builtin's, which nothing of the file's resolves), but the output said the file had a global `format`, which the corpus test then expected the call to resolve to. A member is now printed as what it is: `field`, `method`, `variant`; the rest as before (`global`, `local`, `param`, `typeparam`, `module`). The server's requests (definition, hover, references, semantic tokens) never read these words, and change in nothing.
- **The test** ([[tests/burn/test_lsp.py]], `TestResolutionCorpus`): the corpus check is a helper, `_resolves`, which holds a member's name to resolve where it is used bare except where it is called, as no member can be (a field is used bare only in a struct's literal or pattern, a method nowhere: there is no implicit `self`); a use of a member, as of a global, may be in another file or before its declaration. `test_a_member_is_no_global` resolves a file with a field and a method named `format` and a call of the builtin `format`, a struct literal's field and a pattern's variant.
- **The workaround is no longer needed**: [[selfhost/target.my]]'s two f-strings are `format(…)` again (its `Target` has a field `format`). The rule "in a std file that declares a `format` method, call the builtin through an f-string" ([[MYLA-376]]; round 6's lane rules) can go: a field's or a method's name beside a builtin call of it resolves now. std.xml's and std.yaml's f-strings stay as written (either form is right).
- **Docs**: [[Architecture/Editor-tooling]] (`--resolve`'s kinds, the corpus test's rule).

## Proposals

None that needs a decision. The alternative: resolving a builtin's call to a pseudo-global, as [[MYLA-372]] resolves the prelude's `get` (`<prelude>`), which would give hover a signature for `format`, but leaves `--resolve` calling a field a global, and the test would still read a builtin `len` or `push` beside a field of that name as an unresolved use.

## Evidence

- **Test first**: `test_a_member_is_no_global` before the fix fails on the kinds (`'def 0:11-17 global format'` where `field` is wanted, `def 5:8-14 global format` for the method, `def 9:4-5 global A` for the variant); `test_the_corpus_resolves` with `target.my`'s `format(…)` back, before the fix: `format at 143:12 is not resolved` (selfhost/target.my).
- **After**: `TestResolutionCorpus` 5 tests OK (the corpus, the new test, members 98 of 99 as before, both builds agree); tools/lsp/resolve.my's cases 9/9 (`kind_name`'s 5 new).

