---
id: MYLA-372
title: "Language server: a call of the prelude's get isn't resolved"
type: bug
status: done
priority: low
labels: [lsp, resolution]
---
Found by the formats lane ([[MYLA-332]]). The language server never resolves a call of the prelude function `get(m, k)`. `test_lsp`'s resolution corpus only checks names the file declares, so it notices only when the file also declares a `get`:

```myla fragment
struct S { m: [str: str] }
impl S {
    fun get(self, k: str) -> Option<str> { return get(self.m, k) }
}
```

reports `get at 3:52 is not resolved`. `std.ini` avoids `get(…)` inside its `Ini.get` for now.

- [x] The resolver resolves a call of the prelude's `get` (a global of the pseudo-path `<prelude>`, with its signature for hover; go-to-definition gives none). `Option`, `Result` and `Format` can't be declared by a file, so the corpus test can't miss them; resolving them is left out
- [x] The corpus has it now: `lib/std/args.my` and `lib/std/regex.my` call `get(…)` inside an impl with a `get` method, which `test_lsp`'s `test_the_corpus_resolves` failed on before and passes after

## Review 2026-11-09

Signed off in [[Project/Review-2026-11-09]].
