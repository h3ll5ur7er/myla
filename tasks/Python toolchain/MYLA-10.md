---
id: MYLA-10
title: Errors from imported modules are shown against the entry file
type: bug
status: review
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

## Fix

- `MylaError.path` names the file the position refers to. `errors.in_file(path)` stamps it on an error leaving a block, unless an inner block already did, so the innermost attribution wins.
- [[src/myla/loader.py]] stamps lex, parse and import errors with the module being loaded, binding and renaming errors with their module, and records `source_path` on every declaration, method and lambda (it was functions only, for [[MYLA-71]]).
- [[src/myla/types.py]] wraps each declaration loop of the checker, plus the two places it recurses into other declarations (const folding, alias expansion), in `in_file`.
- [[src/myla/interpreter.py]] stamps runtime errors with the function's or the lambda's file (a lambda written in one module and called from another is attributed to where it was written).
- [[src/myla/cli.py]] renders against that file (`_report`); the language server publishes the diagnostic for that file's URI and clears it once the importing document's next check no longer finds it ([[src/myla/lsp/compiler_adapter.py]], [[src/myla/lsp/server.py]]).

- [x] Errors carry the path of the module they come from
- [x] The CLI renders against that file; the language server publishes the diagnostic for that file's URI ([[Architecture/Editor-tooling]])
- [x] Tests first, seen failing: `tests/unit/test_loader.py::TestErrorPaths` (lex, parse, type errors in a function and in a declaration, module, runtime, a lambda called from another module, the entry file, and the CLI output); `tests/unit/test_lsp_adapter.py`; `tests/integration/test_lsp_diagnostics.py`, which drives the real server over stdio (failed with "no message from the language server" before)
- [x] CI installs pygls so the language server test runs there

Found on the way: a `?` in an expression-bodied lambda escaped the lambda in the interpreter and returned from its caller (now fixed; parity test `try_in_an_expression_lambda_returns_from_the_lambda`), and the checker validates such a `?` against the wrong function ([[MYLA-72]]).
