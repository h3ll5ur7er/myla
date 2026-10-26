---
id: MYLA-20
title: Code hygiene in the Python toolchain
type: chore
status: review
priority: low
labels: [cleanup]
---
- [x] `Lambda.captures` and `Lambda.lifted_name` are dataclass fields, so they take part in AST equality and `format_ast`; make them plain attributes like `resolved_type` ([[src/myla/ast.py#L215-L231]])
- [x] Remove the stray `""` after `ImportDecl` ([[src/myla/ast.py#L580]])
- [x] `Cast`'s docstring cites D43; casts are D26
- [x] `myla/__init__.py` still lists `ast.py` … `compiler/` as "(planned)"
- [x] `Checker._collect_globals` says imports are "not supported yet (the loader arrives in v0.5.1b)"; reword for the case it actually catches (checking a file without the loader)
- [x] The `lsp` ImportError guard in `cli.py` never fires (see [[MYLA-50]])
- [x] Docstrings in `src/` and `tests/` still point at `docs/grammar.md`, `docs/self-hosting.md` and other moved pages; point them at the wiki ([[MYLA-56]])

## How

- `Lambda.captures` and `lifted_name` are plain class attributes now (the checker sets them per instance), so they take no part in AST equality or dumps ([[src/myla/ast.py]]).
- The stray `""` after `ImportDecl` is gone; `Cast` cites D26.
- [[src/myla/__init__.py]] describes the actual package (no "(planned)").
- An import that reaches the checker now says what happened: `imports need the module loader: this file was type-checked on its own (use 'myla check' or 'myla run')`, in both checkers ([[selfhost/checker.my]] gives the same message for the checker gate).
- `myla lsp` imports `myla.lsp.server` inside its guard, so a missing `pygls`/`lsprotocol` prints the `uv sync --extra lsp` hint. Checked by hiding the modules: before, `ModuleNotFoundError: … lsprotocol` traceback; after, the hint and exit 1.
- Docstrings point at the wiki: [[MYLA-56]].
