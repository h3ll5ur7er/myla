---
id: MYLA-10
title: Errors from imported modules are shown against the entry file
type: bug
status: todo
priority: medium
labels: [diagnostics, loader, cli, lsp]
---
`MylaError` carries a line and column but no file ([[src/myla/errors.py#L31-L46]]). The CLI renders every error against the entry file's source ([[src/myla/cli.py#L75-L85]]), and the language server puts it on the open document.

## Steps to reproduce

`main.my`:
```myla
from .bad import f
fun main() { print(f()) }
```
`bad.my`:
```myla
// line 1
// line 2
pub fun f() -> int {
    return "oops"
}
```

## Expected

`type error: return type mismatch …  --> bad.my:4:5`, with `bad.my`'s line 4 under it.

## Actual

`--> main.my:4:5` and an empty source line (main.my has no line 4).

## Done when

- [ ] Errors carry the path of the module they come from (the loader can stamp AST nodes, or the checker can map node → module)
- [ ] The CLI renders against that file; the language server publishes the diagnostic for that file's URI ([[Architecture/Editor-tooling]])
- [ ] A test for each stage: lex, parse and type errors in an imported module
