---
id: MYLA-50
title: Dead code in the language server adapter and CLI
type: bug
status: done
priority: low
labels: [lsp, cleanup]
---
- [ ] `compiler_adapter.definition_at` calls the undefined `_definition_at`; the `NameError` is swallowed, so it always returns `None`. The server uses `definition.definition_at`; delete the adapter's copy (superseded by [[MYLA-80]]: the Python language server went, [[MYLA-83]])
- [ ] The `ImportError` guard in `myla lsp` (`src/myla/cli.py#L150-L166` (removed with the Python toolchain, D101)) never fires, because `myla.lsp` imports the server lazily: without pygls you get a `ModuleNotFoundError: lsprotocol` traceback instead of the "uv sync --extra lsp" hint (superseded by [[MYLA-80]]: the Python language server went, [[MYLA-83]])
- [ ] `lsp/__init__.py` lists 4 of the 12 modules; `server.py` still says "Phase 1 scope: diagnostics" (superseded by [[MYLA-80]]: the Python language server went, [[MYLA-83]])

## Superseded

Closed without a fix: superseded by [[MYLA-80]] (the Python language server and its adapter will be replaced by one written in Myla, see [[Project/Roadmap]]).
