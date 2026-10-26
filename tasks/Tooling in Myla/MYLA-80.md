---
id: MYLA-80
title: Language server written in Myla
type: feature
status: backlog
priority: medium
labels: [lsp, selfhost, editor]
---
Part of the "everything in Myla" direction ([[Project/Roadmap]]). Supersedes [[MYLA-49]], [[MYLA-50]] and [[MYLA-51]], whose findings are requirements here. Needs [[MYLA-78]] and [[MYLA-79]].

The self-hosted front end (lexer, parser, checker, loader, diagnostics in [[selfhost/diag.my]]) already exists; the server is a native program built from it.

- [ ] JSON-RPC over stdin/stdout with `Content-Length` framing; initialize/shutdown/exit; a document store with unsaved text passed to the loader for every open buffer (not just the current one, [[MYLA-49]])
- [ ] Diagnostics published for the file the error is in ([[MYLA-10]]); debounce in the main loop (no threads)
- [ ] Positions in UTF-16 (the rules of [[src/myla/lsp/positions.py]])
- [ ] Document symbols, definition, references, hover, completion: port [[src/myla/lsp/]] and use its tests ([[tests/unit/test_lsp_features.py]], [[tests/integration/test_lsp_diagnostics.py]]) as parity tests against the Myla server
- [ ] From [[MYLA-51]]: keep the last good parse when the buffer doesn't lex or parse; resolve names through scopes and imports (the checker) instead of by name across the workspace; member completion triggered by `.`; refresh the workspace index on `didChangeWatchedFiles`
- [ ] Semantic tokens from the compiler's own lexer, so editors highlight exactly what the compiler sees
- [ ] The VS Code extension starts the Myla server ([[MYLA-53]]), and registers its `**/*.my` file watcher again once the server handles `didChangeWatchedFiles` (removed in [[MYLA-53]] because the Python server ignores it)
