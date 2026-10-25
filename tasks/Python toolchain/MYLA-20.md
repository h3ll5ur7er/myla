---
id: MYLA-20
title: Code hygiene in the Python toolchain
type: chore
status: backlog
priority: low
labels: [cleanup]
---
- [ ] `Lambda.captures` and `Lambda.lifted_name` are dataclass fields, so they take part in AST equality and `format_ast`; make them plain attributes like `resolved_type` ([[src/myla/ast.py#L215-L231]])
- [ ] Remove the stray `""` after `ImportDecl` ([[src/myla/ast.py#L580]])
- [ ] `Cast`'s docstring cites D43; casts are D26
- [ ] `myla/__init__.py` still lists `ast.py` … `compiler/` as "(planned)"
- [ ] `Checker._collect_globals` says imports are "not supported yet (the loader arrives in v0.5.1b)"; reword for the case it actually catches (checking a file without the loader)
- [ ] The `lsp` ImportError guard in `cli.py` never fires (see [[MYLA-50]])
- [ ] Docstrings in `src/` and `tests/` still point at `docs/grammar.md`, `docs/self-hosting.md` and other moved pages; point them at the wiki ([[MYLA-56]])
