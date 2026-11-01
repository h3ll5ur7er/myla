---
id: MYLA-56
title: Docs inside code point at moved or stale pages
type: chore
status: done
priority: low
labels: [docs]
---
The wiki replaced `docs/*.md` (now in [[Archive]]). What still points at the old places or says stale things:

- [x] Docstrings in `src/myla/` and `tests/` cite `docs/grammar.md`, `docs/architecture.md`, `docs/self-hosting.md`, `docs/v0.5-…` (several were already broken before the move)
- [x] `scripts/bootstrap.sh`, `selfhost/gen_main.my` and `selfhost/codegen.my` cite `docs/roadmap.md` / `docs/known_issues.md`
- [x] `tests/burn/test_selfhost_codegen.py` says `gen_main` has no module loader
- [x] `vscode-extension/myla/LSP_DESCRIPTION.md` is a generic brief that describes actors, `async` and a `myla check --json` mode that don't exist; turn it into documentation of the actual server or drop it: dropped with [[MYLA-53]]
- [x] `rust/docs/*` claims checked in [[MYLA-44]] and [[MYLA-46]]: obsolete, `rust/` was removed ([[MYLA-70]])

## How

Every reference to a moved page in `src/`, `selfhost/`, `scripts/` and `tests/` now names its wiki page: `docs/grammar.md` → [[Language/Lexical-structure]] or [[Language/Grammar]], `docs/architecture.md §n` → the matching [[Architecture]] page, `docs/self-hosting.md` → [[Development/Testing]] (the gates) or [[Architecture/Self-hosted-compiler]], `docs/v0.5-modules-and-runtime.md` → [[Architecture/Module-loader]], `docs/roadmap.md` → [[Project/Roadmap]] (25 files). The codegen gate's docstring was already right since [[MYLA-30]] (`check_main` still has no loader, and its gate says so correctly). `LSP_DESCRIPTION.md` was dropped with [[MYLA-53]].
