---
id: MYLA-581
title: The myla skill read against the code, with reference files
type: chore
status: in-progress
priority: medium
labels: [docs, agents]
---
The `myla` agent skill (`.claude/skills/myla/`, mirrored in `.agents/skills/myla/`) was written from the wiki and grew row by row. Before the next language features, read the actual code of the compiler (`selfhost/`) and the standard library (`lib/std/`) and bring the skill in step with it, as the lookup for agents and the owner.

Done means: every claim in `SKILL.md` checked against the code (and, where unsure, with `build/myla check`/`run`), wrong or stale ones corrected, and reference files beside it for what is too long for the core page. Both copies identical; every `myla` block in them checks.

- [ ] Front end read (lexer, tokens, parser, AST, grammar): `reference/syntax.md`
- [ ] Checker and loader read (types, traits, generics, modules, implicit modules, builtins): `reference/builtins.md`
- [ ] Interpreter, CLI, project tool, test runner, REPL read: `reference/toolchain.md`
- [ ] Back end read (lowering, IR, passes, backends, runtimes, bootstrap): `reference/compiler.md`, with where a new feature is wired in
- [ ] Standard library read: `reference/stdlib.md`, one entry per module
- [ ] `SKILL.md` corrected and pointing to the reference files
- [ ] Every `myla` block in the skill checked; both copies identical
