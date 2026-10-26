---
id: MYLA-56
title: Docs inside code point at moved or stale pages
type: chore
status: backlog
priority: low
labels: [docs]
---
The wiki replaced `docs/*.md` (now in [[Archive]]). What still points at the old places or says stale things:

- [ ] Docstrings in `src/myla/` and `tests/` cite `docs/grammar.md`, `docs/architecture.md`, `docs/self-hosting.md`, `docs/v0.5-…` (several were already broken before the move)
- [ ] `scripts/bootstrap.sh`, `selfhost/gen_main.my` and `selfhost/codegen.my` cite `docs/roadmap.md` / `docs/known_issues.md`
- [ ] `tests/burn/test_selfhost_codegen.py` says `gen_main` has no module loader
- [x] `vscode-extension/myla/LSP_DESCRIPTION.md` is a generic brief that describes actors, `async` and a `myla check --json` mode that don't exist; turn it into documentation of the actual server or drop it: dropped with [[MYLA-53]]
- [x] `rust/docs/*` claims checked in [[MYLA-44]] and [[MYLA-46]]: obsolete, `rust/` was removed ([[MYLA-70]])
