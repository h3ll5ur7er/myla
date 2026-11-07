---
id: MYLA-372
title: "Language server: a call of the prelude's get isn't resolved"
type: bug
status: todo
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

- [ ] The resolver knows the prelude's declarations (`Option`, `Result`, `get`, `Format`), with go-to-definition into the prelude's text or none, and hover
- [ ] The reproduction in the resolution corpus
