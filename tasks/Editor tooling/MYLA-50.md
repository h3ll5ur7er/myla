---
id: MYLA-50
title: Dead code in the language server adapter and CLI
type: bug
status: backlog
priority: low
labels: [lsp, cleanup]
---
- [ ] `compiler_adapter.definition_at` calls the undefined `_definition_at`; the `NameError` is swallowed, so it always returns `None`. The server uses `definition.definition_at`; delete the adapter's copy
- [ ] The `ImportError` guard in `myla lsp` ([[src/myla/cli.py#L150-L166]]) never fires, because `myla.lsp` imports the server lazily: without pygls you get a `ModuleNotFoundError: lsprotocol` traceback instead of the "uv sync --extra lsp" hint
- [ ] `lsp/__init__.py` lists 4 of the 12 modules; `server.py` still says "Phase 1 scope: diagnostics"
