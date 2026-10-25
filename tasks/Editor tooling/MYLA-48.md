---
id: MYLA-48
title: Language server selects the wrong range for short declaration names
type: bug
status: backlog
priority: medium
labels: [lsp]
---
`symbols.py` finds a declaration's name by searching for its text from the declaration's column, which is the start of the keyword ([[src/myla/lsp/symbols.py#L209-L222]]). Short names match inside the keyword: `fun un` selects the `un` of `fun`, `const t` the `t` of `const`.

This breaks go-to-definition targets and `includeDeclaration: false` in references (the declaration token isn't removed).

## Done when

- [ ] The name is located from the token stream (the IDENT after the keyword and any `<…>`)
- [ ] Unit tests for `fun un`, `const t`, `struct S`, generic declarations
