---
id: MYLA-33
title: Latent issues in the self-hosted compiler
type: chore
status: backlog
priority: low
labels: [selfhost, codegen, checker]
---
Not reachable today, but each will bite:

- [ ] `mono_token` maps every function type to `X`, so instantiations that differ only in a function-typed argument share a mangled name ([[selfhost/codegen.my]], around line 6079; compare [[MYLA-9]])
- [ ] `checker.my` creates `Expr{id: 0}` (around line 3565), which collides with node 0 in the `resolved` table; harmless only while node 0 is a type expression
- [ ] `is_builtin_call_name` (around line 5981) omits `__write_file` and `__run*`, so they're classified as indirect calls and get unused frame slots
- [ ] `store_into_elem`'s aggregate drop walks through `%rcx`, which the called drop helpers clobber (around line 2336); `gen_assign` uses `%rbx` for exactly this reason
- [ ] `gen_for_in_map` copies 8 bytes per key, wrong for aggregate keys (the checker only allows primitive keys today; known issue §2 in [[Archive/known_issues]])
