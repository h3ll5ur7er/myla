---
id: MYLA-52
title: Language server has no tests
type: chore
status: backlog
priority: medium
labels: [lsp, tests]
---
There are no tests for `src/myla/lsp/`. The pure modules (positions, lookup, symbols, definition, references, completion, compiler adapter) can be tested without pygls.

- [ ] Unit tests for UTF-16 position conversion (astral characters, CRLF), symbol ranges ([[MYLA-48]]), definition, references, completion
- [x] A smoke test that starts the server when pygls is installed: `tests/integration/test_lsp_diagnostics.py` (diagnostics, with [[MYLA-10]]); `tests/unit/test_lsp_adapter.py` covers the compiler adapter
- [x] Make pygls an optional test dependency so CI can run them: the CI `unit` job installs it
