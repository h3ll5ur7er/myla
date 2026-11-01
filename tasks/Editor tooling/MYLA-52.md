---
id: MYLA-52
title: Language server has no tests
type: chore
status: done
priority: medium
labels: [lsp, tests]
---
There are no tests for `src/myla/lsp/`. The pure modules (positions, lookup, symbols, definition, references, completion, compiler adapter) can be tested without pygls.

- [x] Unit tests for UTF-16 position conversion (astral characters, CRLF), symbol ranges ([[MYLA-48]]), definition, references, completion
- [x] A smoke test that starts the server when pygls is installed: `tests/integration/test_lsp_diagnostics.py` (diagnostics, with [[MYLA-10]]); `tests/unit/test_lsp_adapter.py` covers the compiler adapter
- [x] Make pygls an optional test dependency so CI can run them: the CI `unit` job installs it

## How and evidence

`tests/unit/test_lsp_features.py`, 21 tests without pygls:

- positions: UTF-16 columns with astral and BMP characters, clamping, CRLF lines, `identifier_end_column`, and the new `from_lsp_character` (UTF-16 offset to string index);
- symbols: the ranges of [[MYLA-48]], the outline's structure, a parse error;
- definition (in the file, the workspace fallback, off an identifier), references (comments and strings skipped, `include_declaration`, workspace merging without duplicates);
- completion: members after `.`, keywords and declarations otherwise.

Two bugs found by the tests, fixed: `completion._is_member_access` sliced the line with a UTF-16 offset as if it were a string index (a cursor after a 😀 looked one character further), and the keyword list lacked `char`, `float`, `float32` and `float64`. With pygls installed, `tests/integration` also runs the diagnostics smoke test (4 tests, none skipped). Unit suite: 442 tests pass.

## Resolution

Superseded (closed in the review triage of 2026-10-31): [[MYLA-83]] removed the Python language server it was to test; the Myla server ([[MYLA-80]]) is tested by `tests/burn/test_lsp.py` over the scenarios in `tests/burn/_lsp_scenarios.py` (140 tests).
