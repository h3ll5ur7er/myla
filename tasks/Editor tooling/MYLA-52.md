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
- [ ] A smoke test that starts the server when pygls is installed
- [ ] Make pygls an optional test dependency so CI can run them
