---
id: MYLA-48
title: Language server selects the wrong range for short declaration names
type: bug
status: done
priority: medium
labels: [lsp]
---
`symbols.py` finds a declaration's name by searching for its text from the declaration's column, which is the start of the keyword (`src/myla/lsp/symbols.py#L209-L222`). Short names match inside the keyword: `fun un` selects the `un` of `fun`, `const t` the `t` of `const`.

This breaks go-to-definition targets and `includeDeclaration: false` in references (the declaration token isn't removed).

## Done when

- [x] The name is located from the token stream (the IDENT after the keyword and any `<…>`)
- [x] Unit tests for `fun un`, `const t`, `struct S`, generic declarations

## How

`document_symbols` keeps the token list it parsed (`_Doc`, with sorted positions for `bisect`). `_name_range` takes the first token whose whole lexeme is the name, from the declaration's start (its keyword, or a field's or variant's own position) to the end of the header (`{` or the end of the line); a NEWLINE token carries the next line's position, so the one ending the previous line is skipped. Whole tokens can't match inside a keyword, and type names such as `int32` (their own token kinds) are found too. An `impl` selects the last mention of its target, so `impl G<int32> for int32` selects the type after `for` (`src/myla/lsp/symbols.py`).

## Evidence

- `TestSymbolRanges` in `tests/unit/test_lsp_features.py`: `fun un`, `const t`, `struct S` with a field `s`, an enum with a variant of its own name, generic functions/structs/traits/impls, `#test` and `pub` before the keyword, names after astral characters, `impl G<int32> for int32`. Before: `fun un` selected (0,1)-(0,3), `const t` the whole line, `pub fun f(f: int)` the `f` of `fun`. After: all pass.
- `test_references_without_the_declaration`: before, the declaration token stayed in the list; after, it is dropped.
- Every symbol of `selfhost/*.my`, `examples/*.my` and `src/myla/std/*.my` selects exactly its name (a script comparing the selected text); the outline of `selfhost/codegen.my` (401 symbols) takes 0.64 s against 0.56 s before, nearly all of it lexing and parsing.

## Resolution

Superseded (closed in the review triage of 2026-10-31): [[MYLA-80]] replaced the Python language server with the Myla one and [[MYLA-83]] removed it; the same cases (`fun un`, `const t`, `struct S`, generic impls) run against the Myla server in `tests/burn/_lsp_scenarios.py` (`tools/lsp/symbols.my`).
